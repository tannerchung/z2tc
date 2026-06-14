"""Command-line entry point for the Strava athlete-profile scraper and z2tc orchestration.

Usage:
    python main.py login                       # one-time manual login (headed)
    python main.py scrape 12345 67890          # scrape one or more athlete IDs
    python main.py ingest-style                # harvest club workbook style (Sheets API)
    python main.py build-plan <id> --survey …  # baseline → plan artifact in SQLite
    python main.py replan <id>                 # fold events → new plan artifact
    python main.py monitor <id> --training …  # Strava weekly totals → monitor events
    python main.py publish-sheet <id>          # latest plan → Google Sheet tab
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from feeds.strava.athlete import scrape_athlete
from feeds.strava.session import (
    DEFAULT_STATE_PATH,
    ensure_login,
    session_status,
    strava_session,
)
from feeds.strava.training import scrape_training_history
from engine.analyze import (
    build_calendar,
    build_marathon_report,
    load_weeks,
    summarize,
)
from engine.monitor import monitor_block
from engine.plan import build_plan
from engine.plan.replan import replan
from llm.boundary import StyleSpec
from render.sheets import render_plan
from render.style import (
    default_club_spreadsheet_id,
    derive_style_spec,
    harvest_workbook_style,
)
from store.db import Store, default_db_path, fingerprint_athlete_inputs
from store.events import EventRecord, event_type_name
from store.models import Athlete, SurveyInputs

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "athletes.jsonl"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _cmd_login(args: argparse.Namespace) -> int:
    ok = ensure_login(state_path=args.state_path)
    return 0 if ok else 1


def _cmd_check(args: argparse.Namespace) -> int:
    logged_in, who = session_status(state_path=args.state_path)
    if logged_in:
        suffix = f" as {who}" if who else ""
        print(f"Logged in{suffix}. Session is ready to scrape.")
        return 0
    print(
        "Not logged in. Run `python main.py login` and complete the login "
        "in the browser window."
    )
    return 1


def _cmd_scrape(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    debug_dir = PROJECT_ROOT / "output" / "debug" if args.debug else None

    results, errors = [], 0
    with strava_session(
        headless=not args.headed,
        state_path=args.state_path,
        slow_mo_ms=args.slow_mo,
    ) as page:
        for athlete_id in args.athlete_ids:
            try:
                profile = scrape_athlete(
                    page,
                    athlete_id,
                    max_workouts=args.max_workouts,
                    debug_dump_dir=debug_dir,
                )
                results.append(profile.to_dict())
                print(
                    f"[ok] {athlete_id}: {profile.name or '?'} "
                    f"(followers={profile.followers}, following={profile.following}, "
                    f"workouts={len(profile.workouts)})"
                )
                if args.delay:
                    page.wait_for_timeout(int(args.delay * 1_000))
            except Exception as exc:  # keep going on a single bad profile
                errors += 1
                print(f"[error] {athlete_id}: {exc}", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as fh:
        for record in results:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(results)} record(s) to {out_path}")
    return 1 if errors and not results else 0


def _cmd_training(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with strava_session(
        headless=not args.headed, state_path=args.state_path
    ) as page:
        weeks = scrape_training_history(
            page, args.athlete_id, args.start, args.end, delay_s=args.delay
        )

    total_workouts = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for week in weeks:
            fh.write(json.dumps(week.to_dict(), ensure_ascii=False) + "\n")
            total_workouts += len(week.workouts)
            runs = [w for w in week.workouts if (w.sport_type or "") == "Run"]
            label = week.date_label or f"{week.iso_year}-W{week.iso_week:02d}"
            print(
                f"{label}: dist={week.total_distance or '-'} "
                f"time={week.total_time or '-'} "
                f"({len(week.workouts)} activities, {len(runs)} runs)"
            )
            for w in week.workouts:
                stat = w.stats.get("Distance") or w.stats.get("Time") or ""
                pace = f" @ {w.stats['Pace']}" if "Pace" in w.stats else ""
                print(f"    - {w.sport_type or '?':10} {stat}{pace}  {w.name or ''}")

    print(
        f"\nWrote {len(weeks)} weeks ({total_workouts} activities) to {out_path}"
    )
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    in_path = Path(args.infile)
    if not in_path.exists():
        print(f"No training file at {in_path}. Run `training` first.", file=sys.stderr)
        return 1
    weeks = load_weeks(in_path)
    calendar = build_calendar(weeks)
    summary = summarize(weeks)

    if not args.no_calendar:
        print("=== Per-day calendar ===")
        for day, acts in calendar.items():
            print(day)
            for a in acts:
                dist = a.get("distance") or a.get("time") or ""
                pace = f" @ {a['pace']}" if a.get("pace") else ""
                print(f"    {a.get('type') or '?':12} {dist}{pace}  {a.get('name') or ''}")

    print("\n=== Weekly run mileage ===")
    for week_start, miles in summary.weekly_run_miles.items():
        bar = "#" * int(miles / 2)
        print(f"  {week_start}  {miles:5.1f} mi  {bar}")

    print("\n=== Races detected (from title/notes) ===")
    if summary.races:
        for r in summary.races:
            dist = f"{r['distance_mi']:.2f} mi" if r.get("distance_mi") else "?"
            print(
                f"  {r['date']}  {r['category']:14} {r['time']:>8}  "
                f"({r['pace'] or '-'}, {dist})  {r['name'] or ''}"
            )
    else:
        print("  (none)")

    print("\n=== Best race times (by title/notes) ===")
    for name in ("5K", "10K", "Half Marathon", "Marathon"):
        b = summary.best_races.get(name)
        if b:
            print(
                f"  {name:14} {b['time']:>8}  ({b['pace'] or '-'}, "
                f"{b['distance_mi']:.2f} mi)  {b['date']}  {b['name'] or ''}"
            )
        else:
            print(f"  {name:14} {'—':>8}  (no race detected)")

    print("\n=== Stats ===")
    lr = summary.longest_run
    if lr:
        print(
            f"  Longest run:    {lr['miles']:.2f} mi in {lr['time']} "
            f"({lr['pace'] or '-'})  {lr['date']}  {lr['name'] or ''}"
        )
    print("  Fastest logged run near each distance (not necessarily a race):")
    for name in ("5K", "10K", "Half Marathon", "Marathon"):
        b = summary.bests.get(name)
        if b:
            print(
                f"    {name:14} {b['time']:>8}  ({b['pace'] or '-'}, "
                f"{b['distance_mi']:.2f} mi)  {b['date']}  {b['name'] or ''}"
            )
        else:
            print(f"    {name:14} {'—':>8}  (no logged run near this distance)")
    print(
        f"\n  Totals: {summary.total_run_miles:.1f} run mi over "
        f"{summary.total_runs} runs / {summary.total_activities} activities, "
        f"{summary.weeks} weeks"
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"summary": summary.to_dict(), "calendar": calendar},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote summary + calendar to {out_path}")
    return 0


def _cmd_marathon_report(args: argparse.Namespace) -> int:
    """Wide scan per athlete: auto-detect the latest marathon, isolate the training
    block, scan post-marathon races, and compute paces + VDOT for a plan."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict] = []

    with strava_session(headless=not args.headed, state_path=args.state_path) as page:
        for athlete_id in args.athlete_ids:
            try:
                name = scrape_athlete(page, athlete_id, max_workouts=1).name
            except Exception:
                name = None

            weeks = scrape_training_history(
                page, athlete_id, args.scan_start, args.end, delay_s=args.delay
            )
            week_dicts = [w.to_dict() for w in weeks]
            (out_dir / f"training_{athlete_id}.jsonl").write_text(
                "\n".join(json.dumps(w, ensure_ascii=False) for w in week_dicts) + "\n",
                encoding="utf-8",
            )

            report = build_marathon_report(
                week_dicts,
                name=name,
                athlete_id=athlete_id,
                today=args.end,
                block_weeks=args.block_weeks,
            )
            (out_dir / f"report_{athlete_id}.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            reports.append(report)
            _print_report_brief(report)

    (out_dir / "marathon_reports.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {len(reports)} report(s) to {out_dir}")
    return 0


def _print_report_brief(report: dict) -> None:
    print(f"\n=== {report.get('name') or '?'} ({report['athlete_id']}) ===")
    marathons = report.get("all_marathons_detected") or []
    print(f"  Marathons detected: {len(marathons)}")
    for m in marathons:
        print(f"    {m['date']}  {m['time']:>8}  ({m.get('pace') or '-'})  {m['name']}")
    latest = report.get("latest_marathon")
    if not latest:
        print("  No marathon detected in range.")
    tb = report.get("training_block")
    if tb:
        print(
            f"  Block: {tb['start']} -> {tb['end']} ({tb['weeks']} wks, "
            f"{tb['total_run_miles']} mi, peak wk {tb['peak_week']}, "
            f"median {tb['median_pace']})"
        )
    pm = report.get("post_marathon") or {}
    pm_races = pm.get("races") or []
    print(f"  Post-marathon races: {len(pm_races)}")
    for r in pm_races:
        print(f"    {r['date']}  {r['category']:14} {r['time']:>8}  {r['name'] or ''}")
    vd = report.get("recommended_vdot")
    if vd:
        src = vd["source_race"]
        print(
            f"  VDOT {vd['vdot']} (from {src['category']} {src['time']}, {src['date']})"
        )
        print(f"    paces: {vd['training_paces']}")


def _open_store(args: argparse.Namespace) -> Store:
    raw = getattr(args, "db", None)
    return Store(Path(raw) if raw else None)


def _cmd_ingest_style(args: argparse.Namespace) -> int:
    dump = harvest_workbook_style(args.spreadsheet_id)
    spec = derive_style_spec(dump, use_llm_assist=args.llm_assist)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "spreadsheet_id": dump.get("spreadsheet_id") or args.spreadsheet_id,
        "workbook_title": dump.get("workbook_title"),
        "style_spec": spec.model_dump(mode="json"),
    }
    if args.include_harvest:
        body["harvest"] = dump
    out_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote style bundle to {out_path}")
    return 0


def _cmd_build_plan(args: argparse.Namespace) -> int:
    survey_path = Path(args.survey)
    if not survey_path.exists():
        print(f"No survey file at {survey_path}", file=sys.stderr)
        return 1
    try:
        survey = SurveyInputs.model_validate_json(survey_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid survey JSON: {exc}", file=sys.stderr)
        return 1
    store = _open_store(args)
    athlete_id = args.athlete_id
    athlete = Athlete(
        id=athlete_id,
        name=survey.name,
        strava_athlete_id=args.strava_id,
    )
    store.upsert_athlete(athlete)
    store.save_survey_baseline(athlete_id, survey)
    inputs = survey.to_athlete_inputs()
    fp = fingerprint_athlete_inputs(inputs)
    plan = build_plan(inputs)
    pid = store.save_plan_artifact(athlete_id, plan, fp)
    print(f"Saved plan artifact {pid} for athlete {athlete_id}")
    return 0


def _cmd_replan(args: argparse.Namespace) -> int:
    store = _open_store(args)
    survey = store.load_survey_baseline(args.athlete_id)
    if not survey:
        print("No survey baseline for athlete; run build-plan first.", file=sys.stderr)
        return 1
    baseline = survey.to_athlete_inputs()
    plan = replan(baseline, store, args.athlete_id)
    nevents = len(store.list_events(args.athlete_id))
    fp = fingerprint_athlete_inputs(baseline) + f"_e{nevents}"
    pid = store.save_plan_artifact(args.athlete_id, plan, fp)
    print(f"Saved replan artifact {pid} (events={nevents})")
    return 0


def _cmd_monitor(args: argparse.Namespace) -> int:
    store = _open_store(args)
    art = store.load_latest_plan(args.athlete_id)
    if not art:
        print("No plan artifact; run build-plan or replan first.", file=sys.stderr)
        return 1
    tpath = Path(args.training)
    if not tpath.exists():
        print(f"No training file at {tpath}", file=sys.stderr)
        return 1
    plan = store.plan_from_artifact(art)
    weeks = load_weeks(tpath)
    summary = summarize(weeks)
    payloads = monitor_block(plan, summary.weekly_run_miles)
    logged = 0
    for p in payloads:
        ev = EventRecord(
            athlete_id=args.athlete_id,
            source="strava",
            status="applied",
            payload=p,
        )
        store.append_event_record(ev)
        print(event_type_name(p), json.dumps(p.model_dump(mode="json")))
        logged += 1
    print(f"Logged {logged} monitor event(s) for athlete {args.athlete_id}")
    return 0


def _cmd_publish_sheet(args: argparse.Namespace) -> int:
    bundle_path = Path(args.style_bundle)
    if not bundle_path.exists():
        print(
            f"No style bundle at {bundle_path}. Run `python main.py ingest-style` first.",
            file=sys.stderr,
        )
        return 1
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read style bundle: {exc}", file=sys.stderr)
        return 1
    spec = StyleSpec(**bundle["style_spec"])
    store = _open_store(args)
    art = store.load_latest_plan(args.athlete_id)
    if not art:
        print("No plan artifact; run build-plan or replan first.", file=sys.stderr)
        return 1
    plan = store.plan_from_artifact(art)
    ss_id = str(bundle.get("spreadsheet_id") or default_club_spreadsheet_id())
    meta = render_plan(
        plan,
        spec,
        spreadsheet_id=ss_id,
        sheet_title=args.sheet_title,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Saved Playwright storage-state file (holds your login session).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="One-time manual login (opens a browser).")
    p_login.set_defaults(func=_cmd_login)

    p_check = sub.add_parser("check", help="Verify the saved session is logged in.")
    p_check.set_defaults(func=_cmd_check)

    p_scrape = sub.add_parser("scrape", help="Scrape one or more athlete profiles.")
    p_scrape.add_argument("athlete_ids", nargs="+", help="Strava athlete IDs.")
    p_scrape.add_argument(
        "--out", default=str(DEFAULT_OUTPUT), help="Output JSONL path."
    )
    p_scrape.add_argument(
        "--max-workouts",
        type=int,
        default=20,
        help="Max workout posts to extract per athlete (default 20).",
    )
    p_scrape.add_argument(
        "--headed", action="store_true", help="Show the browser window."
    )
    p_scrape.add_argument(
        "--debug", action="store_true", help="Dump HTML + screenshots per profile."
    )
    p_scrape.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to pause between profiles (be polite; default 2.0).",
    )
    p_scrape.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Milliseconds to slow each Playwright action (debugging).",
    )
    p_scrape.set_defaults(func=_cmd_scrape)

    p_train = sub.add_parser(
        "training",
        help="Reconstruct week-by-week training history over a date range.",
    )
    p_train.add_argument("athlete_id", help="Strava athlete ID.")
    p_train.add_argument(
        "--start", type=_parse_date, required=True, help="Start date (YYYY-MM-DD)."
    )
    p_train.add_argument(
        "--end", type=_parse_date, required=True, help="End date (YYYY-MM-DD)."
    )
    p_train.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "output" / "training.jsonl"),
        help="Output JSONL path (one ISO week per line).",
    )
    p_train.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between weekly requests (be polite; default 1.0).",
    )
    p_train.add_argument(
        "--headed", action="store_true", help="Show the browser window."
    )
    p_train.set_defaults(func=_cmd_training)

    p_an = sub.add_parser(
        "analyze",
        help="Per-day calendar, weekly mileage, and best-distance stats from a "
        "training.jsonl file.",
    )
    p_an.add_argument(
        "--in",
        dest="infile",
        default=str(PROJECT_ROOT / "output" / "training.jsonl"),
        help="Training JSONL produced by the `training` command.",
    )
    p_an.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "output" / "training_summary.json"),
        help="Where to write the summary + calendar JSON.",
    )
    p_an.add_argument(
        "--no-calendar", action="store_true", help="Skip printing the day calendar."
    )
    p_an.set_defaults(func=_cmd_analyze)

    p_mr = sub.add_parser(
        "marathon-report",
        help="Wide scan: auto-detect each athlete's latest marathon, isolate the "
        "training block, scan post-marathon races, and compute paces + VDOT.",
    )
    p_mr.add_argument("athlete_ids", nargs="+", help="Strava athlete IDs.")
    p_mr.add_argument(
        "--scan-start",
        dest="scan_start",
        type=_parse_date,
        default=date(2025, 1, 1),
        help="Earliest week to scan when hunting for the latest marathon "
        "(default 2025-01-01).",
    )
    p_mr.add_argument(
        "--end",
        type=_parse_date,
        default=date.today(),
        help="Latest week to scan (default today).",
    )
    p_mr.add_argument(
        "--block-weeks",
        dest="block_weeks",
        type=int,
        default=20,
        help="Length of the training block before the marathon (default 20).",
    )
    p_mr.add_argument(
        "--out-dir",
        dest="out_dir",
        default=str(PROJECT_ROOT / "output" / "marathon"),
        help="Directory for per-athlete reports + raw training data.",
    )
    p_mr.add_argument(
        "--delay",
        type=float,
        default=0.6,
        help="Seconds between weekly requests (default 0.6).",
    )
    p_mr.add_argument(
        "--headed", action="store_true", help="Show the browser window."
    )
    p_mr.set_defaults(func=_cmd_marathon_report)

    p_style = sub.add_parser(
        "ingest-style",
        help="Harvest sampled cell formats from the club spreadsheet and cache a StyleSpec.",
    )
    p_style.add_argument(
        "--spreadsheet-id",
        default=default_club_spreadsheet_id(),
        help="Spreadsheet id (default club workbook or Z2TC_CLUB_SPREADSHEET_ID).",
    )
    p_style.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "output" / "club_workbook_style.json"),
        help="JSON bundle path (style_spec + spreadsheet_id).",
    )
    p_style.add_argument(
        "--include-harvest",
        action="store_true",
        help="Embed full harvest payload (large) for debugging.",
    )
    p_style.add_argument(
        "--llm-assist",
        action="store_true",
        help="Forwarded to derive_style_spec (reserved; no live LLM in-repo).",
    )
    p_style.set_defaults(func=_cmd_ingest_style)

    p_bp = sub.add_parser(
        "build-plan",
        help="Persist survey baseline, run build_plan, save PlanArtifact to SQLite.",
    )
    p_bp.add_argument(
        "athlete_id",
        help="Store primary key for the athlete (often the Strava id).",
    )
    p_bp.add_argument(
        "--survey",
        required=True,
        help="Path to SurveyInputs JSON (see docs/cheatsheets/08).",
    )
    p_bp.add_argument(
        "--strava-id",
        default=None,
        help="Optional Strava athlete id stored on the Athlete row.",
    )
    p_bp.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_bp.set_defaults(func=_cmd_build_plan)

    p_rp = sub.add_parser(
        "replan",
        help="Fold applied/approved events on the baseline; save a new PlanArtifact.",
    )
    p_rp.add_argument("athlete_id")
    p_rp.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_rp.set_defaults(func=_cmd_replan)

    p_mon = sub.add_parser(
        "monitor",
        help="Compare latest plan vs training.jsonl; append Strava-sourced monitor events.",
    )
    p_mon.add_argument("athlete_id")
    p_mon.add_argument(
        "--training",
        required=True,
        help="Path to training JSONL (ISO week lines, e.g. output/marathon/training_*.jsonl).",
    )
    p_mon.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_mon.set_defaults(func=_cmd_monitor)

    p_pub = sub.add_parser(
        "publish-sheet",
        help="Render the athlete's latest plan into a Google Sheet tab.",
    )
    p_pub.add_argument("athlete_id")
    p_pub.add_argument(
        "--style-bundle",
        default=str(PROJECT_ROOT / "output" / "club_workbook_style.json"),
        help="JSON from ingest-style (style_spec + spreadsheet_id).",
    )
    p_pub.add_argument(
        "--sheet-title",
        default=None,
        help="Tab title (default Z2TC_<athlete prefix>).",
    )
    p_pub.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_pub.set_defaults(func=_cmd_publish_sheet)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
