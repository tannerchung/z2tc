"""Command-line entry point for the Strava athlete-profile scraper and z2tc orchestration.

Usage:
    python main.py login                       # one-time manual login (headed)
    python main.py scrape 12345 67890          # scrape one or more athlete IDs
    python main.py ingest-style                # harvest club workbook style (Sheets API)
    python main.py pull-intake --defaults …    # club Intake tab → SurveyInputs JSON
    python main.py nyrr-races --search "…"     # NYRR chip times (results.nyrr.org API)
    python main.py build-plan <id> --survey …  # baseline → plan artifact in SQLite
    python main.py replan <id>                 # fold events → new plan artifact
    python main.py monitor <id> --training …  # Strava weekly totals → monitor events
    python main.py propose-notes <id> --text "…"  # coach note + LLM proposed events
    python main.py interpret-activities <id> --training PATH  # Strava text → proposed events
    python main.py review <id>               # approve/reject proposed events; optional replan
    python main.py publish-sheet <id>          # latest plan → Google Sheet tab
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
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
from engine.plan import apply_club_policy, build_club_plan
from engine.plan.replan import replan, resolve_inputs
from llm.boundary import StyleSpec, date_window, extract_events, payload_out_of_window_fields
from render.sheets import render_long_runs, render_plan, render_read_me, render_workout_dictionary
from render.style import (
    default_club_spreadsheet_id,
    derive_style_spec,
    harvest_workbook_style,
)
from store.db import STYLE_BUNDLE_KEY, Store, default_db_path, fingerprint_athlete_inputs
from store.events import (
    CoachNotePayload,
    DataExcludePayload,
    EffortQualityPayload,
    EventRecord,
    FitnessAnchorPayload,
    ManualOverridePayload,
    RaceEstimatePayload,
    TuneUpResultPayload,
    event_type_name,
    parse_event_payload,
)
from store.models import Athlete, Season, SurveyInputs, TrainingBlock

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "athletes.jsonl"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_hms(value: str) -> int:
    """Parse 'H:MM:SS' or 'MM:SS' into seconds."""
    parts = [int(p) for p in value.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        raise argparse.ArgumentTypeError(f"expected H:MM:SS or MM:SS, got {value!r}")
    return h * 3600 + m * 60 + s


def _parse_pace_mi(value: str) -> int:
    """Parse 'M:SS' per-mile pace into seconds per mile."""
    parts = [int(p) for p in value.split(":")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"expected M:SS pace per mile, got {value!r}")
    return parts[0] * 60 + parts[1]


def _fmt_hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_pace_mi(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}/mi"


_DISTANCE_CHOICES = {"5k": "5K", "10k": "10K", "half": "Half Marathon", "marathon": "Marathon"}


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


def training_block_from_report(
    store: Store, report: dict, weeks: list[dict], strava_id: str
) -> TrainingBlock | None:
    """Build a durable :class:`TrainingBlock` snapshot from a marathon report + raw weeks.

    Links to the store ``athlete_id`` when an athlete row carries this Strava id (else keys by the
    Strava id so a pre-import scrape isn't lost). Returns ``None`` if no marathon block was found.
    """
    tb = report.get("training_block")
    if not tb:
        return None
    latest = report.get("latest_marathon") or {}
    m_date = latest.get("date")
    start, end = tb.get("start"), tb.get("end")
    if start and end:
        block_weeks = [w for w in weeks if start <= (w.get("week_start") or "") <= end]
    else:
        block_weeks = weeks
    ath = store.get_athlete_by_strava(str(strava_id))
    athlete_id = ath.id if ath else str(strava_id)
    return TrainingBlock(
        id=Store.training_block_id(athlete_id, m_date),
        athlete_id=athlete_id,
        strava_athlete_id=str(strava_id),
        marathon_date=m_date,
        marathon_name=latest.get("name"),
        marathon_time_s=latest.get("duration_s"),
        block_start=start,
        block_end=end,
        weeks=block_weeks,
        report=report,
        profile=report.get("capacity_profile") or {},
    )


def _cmd_marathon_report(args: argparse.Namespace) -> int:
    """Wide scan per athlete: auto-detect the latest marathon, isolate the training
    block, scan post-marathon races, and compute paces + VDOT for a plan."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict] = []
    store = None if args.no_store else _open_store(args)

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

            if store is not None:
                block = training_block_from_report(store, report, week_dicts, athlete_id)
                if block is not None:
                    store.save_training_block(block)
                    print(f"  stored training block ({block.athlete_id}, marathon {block.marathon_date})")

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
    body: dict = {
        "spreadsheet_id": dump.get("spreadsheet_id") or args.spreadsheet_id,
        "workbook_title": dump.get("workbook_title"),
        "style_spec": spec.model_dump(mode="json"),
    }
    if args.include_harvest:
        body["harvest"] = dump

    # Source of truth: the store's config kv (publish reads it). The harvest payload is debugging-only
    # and stays out of the persisted bundle so the row stays small.
    store = _open_store(args)
    store.set_config(STYLE_BUNDLE_KEY, {k: v for k, v in body.items() if k != "harvest"})
    print("Cached style bundle in the store.")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
    inputs = apply_club_policy(survey.to_athlete_inputs())
    fp = fingerprint_athlete_inputs(inputs)
    plan = build_club_plan(inputs)  # idempotent club policy + tune-up placement
    pid = store.save_plan_artifact(athlete_id, plan, fp, resolved_inputs=inputs)
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
    resolved = resolve_inputs(baseline, store, args.athlete_id)
    nevents = len(store.list_events(args.athlete_id))
    fp = fingerprint_athlete_inputs(baseline) + f"_e{nevents}"
    pid = store.save_plan_artifact(args.athlete_id, plan, fp, resolved_inputs=resolved)
    print(f"Saved replan artifact {pid} (events={nevents})")
    return 0


def _cmd_list_seasons(args: argparse.Namespace) -> int:
    store = _open_store(args)
    seasons = store.list_seasons(args.athlete_id)
    if not seasons:
        print(f"No seasons for {args.athlete_id}.")
        return 0
    for s in seasons:
        flag = "* " if s.status == "active" else "  "
        print(f"{flag}{s.id}  [{s.status:8}] {s.label}  race={s.race_date or '-'}")
    return 0


def _cmd_start_season(args: argparse.Namespace) -> int:
    """Carry an athlete forward into a new marathon block: seed a fresh baseline from the
    active season's ending state + race history, archive the old season, build the plan."""
    from store.carryforward import build_next_season_survey

    store = _open_store(args)
    prior = store.get_active_season(args.athlete_id)
    if prior is None:
        print(f"No active season for {args.athlete_id}; run build-plan first.", file=sys.stderr)
        return 1
    survey = store.load_survey_baseline(args.athlete_id, season_id=prior.id)
    if survey is None:
        print("Active season has no survey baseline.", file=sys.stderr)
        return 1
    baseline = survey.to_athlete_inputs()
    resolved = resolve_inputs(baseline, store, args.athlete_id, season_id=prior.id)
    art = store.load_latest_plan(args.athlete_id, season_id=prior.id)
    if art is None:
        print("Active season has no plan artifact to carry volume from.", file=sys.stderr)
        return 1
    prior_plan = store.plan_from_artifact(art)

    races: list[dict] | None = None
    if args.report:
        report_path = Path(args.report)
        if not report_path.exists():
            print(f"No report at {report_path}", file=sys.stderr)
            return 1
        report = json.loads(report_path.read_text(encoding="utf-8"))
        races = report.get("all_races_detected") or None

    new_survey, provenance = build_next_season_survey(
        survey,
        resolved,
        prior_plan,
        label=args.label,
        race_name=args.race_name,
        race_date=args.race_date.isoformat(),
        goal_marathon_s=_parse_hms(args.goal),
        block_weeks=args.block_weeks,
        completed_marathon_time_s=_parse_hms(args.completed_time) if args.completed_time else None,
        races=races,
        break_days=args.break_days,
        cross_trained=args.cross_trained,
    )

    new_season = Season(
        athlete_id=args.athlete_id,
        label=args.label,
        race_date=args.race_date.isoformat(),
        status="active",
        meta={"carry_forward": provenance},
    )
    sid = store.create_season(new_season, make_active=True)
    store.save_survey_baseline(args.athlete_id, new_survey, season_id=sid)

    print(f"Started season {sid} ({args.label}); archived prior season {prior.id}.")
    for note in provenance["notes"]:
        print(f"  - {note}")

    if not args.no_build:
        inputs = apply_club_policy(new_survey.to_athlete_inputs())
        plan = build_club_plan(inputs)  # idempotent club policy + tune-up placement
        fp = fingerprint_athlete_inputs(inputs)
        pid = store.save_plan_artifact(args.athlete_id, plan, fp, season_id=sid, resolved_inputs=inputs)
        print(f"Built plan artifact {pid} for new season ({plan.method}, VDOT {plan.vdot}).")
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
    # Persist the weekly actuals so execution scoring stays replayable from the store (the canonical
    # source), not just this feed file. Best-effort — never fail the monitor on the side write.
    try:
        store.upsert_weekly_actuals(args.athlete_id, summary.weekly_run_miles)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not persist weekly actuals: {exc}", file=sys.stderr)
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


def _cmd_coach_note(args: argparse.Namespace) -> int:
    """Append a coach observation, or an effort-corrected race estimate, to the event log.

    A plain ``--text`` note is provenance only. A race estimate (``--race-name`` +
    ``--estimated-time``) computes the trained-peak VDOT the effort really showed and detrains
    it to today (Daniels Table 15.1) so the next ``replan`` folds it into the athlete's VDOT.
    """
    from engine import readiness as rd
    from engine.vdot import RACE_METERS, vdot_from_race

    store = _open_store(args)

    if args.race_name:
        if not args.distance or not args.estimated_time:
            print("Race estimate needs --distance and --estimated-time.", file=sys.stderr)
            return 1
        dist_m = RACE_METERS[_DISTANCE_CHOICES[args.distance]]
        est_vdot = vdot_from_race(dist_m, args.estimated_time)
        if est_vdot is None:
            print("Could not compute VDOT for that distance/time.", file=sys.stderr)
            return 1

        break_days = args.break_days
        if break_days is None:
            baseline = store.load_survey_baseline(args.athlete_id)
            break_days = int(getattr(baseline, "recent_break_days", None) or 0) if baseline else 0
        eff_vdot = rd.adjusted_vdot(est_vdot, break_days, args.cross_trained)

        payload = RaceEstimatePayload(
            race_name=args.race_name,
            race_date=args.race_date.isoformat() if args.race_date else "",
            distance_m=dist_m,
            actual_time_s=args.actual_time,
            estimated_time_s=args.estimated_time,
            estimated_vdot=est_vdot,
            effective_vdot=eff_vdot,
            break_days=break_days,
            note=args.text or "",
        )
        store.append_event_record(
            EventRecord(athlete_id=args.athlete_id, source="coach", status="applied", payload=payload)
        )
        print(
            f"Recorded race-estimate for {args.athlete_id}: {args.race_name} "
            f"@ {args.estimated_time}s → trained VDOT {est_vdot}, "
            f"detrained {break_days}d → effective VDOT {eff_vdot}.\n"
            f"Run `python main.py replan {args.athlete_id}` to apply it."
        )
        return 0

    if not args.text:
        print("Provide --text, or a race estimate (--race-name --distance --estimated-time).", file=sys.stderr)
        return 1
    store.append_event_record(
        EventRecord(
            athlete_id=args.athlete_id,
            source="coach",
            status="applied",
            payload=CoachNotePayload(text=args.text, tags=args.tag or []),
        )
    )
    print(f"Recorded coach note for {args.athlete_id}.")
    return 0


def _cmd_propose_notes(args: argparse.Namespace) -> int:
    """Append raw coach text as an applied CoachNote, then NL-extract proposed events."""
    store = _open_store(args)
    text = (args.text or "").strip()
    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"No file at {fp}", file=sys.stderr)
            return 1
        try:
            text = fp.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"Could not read file: {exc}", file=sys.stderr)
            return 1
    if not text:
        print("Provide --text or --file with non-empty content.", file=sys.stderr)
        return 1

    baseline = store.load_survey_baseline(args.athlete_id)
    break_days = int(getattr(baseline, "recent_break_days", None) or 0) if baseline else 0
    cross = bool(getattr(baseline, "cross_trained_during_break", False)) if baseline else False

    tags = list(args.tag or [])
    note_ev = EventRecord(
        athlete_id=args.athlete_id,
        source="coach",
        status="applied",
        payload=CoachNotePayload(text=text, tags=tags),
    )
    store.append_event_record(note_ev)
    proposed = extract_events(
        text,
        athlete_id=args.athlete_id,
        break_days=break_days,
        cross_trained=cross,
        race_date=getattr(baseline, "race_date", None) if baseline else None,
        block_weeks=getattr(baseline, "block_weeks", None) if baseline else None,
    )
    for ev in proposed:
        store.append_event_record(ev)
        print(f"  proposed {event_type_name(ev.payload)}: {ev.payload.model_dump_json()}")
    print(
        f"Recorded coach note {note_ev.id} + {len(proposed)} proposed event(s) for "
        f"{args.athlete_id}. Run `python main.py review {args.athlete_id}` to approve."
    )
    return 0


def _cmd_interpret_activities(args: argparse.Namespace) -> int:
    """Scan training.jsonl for activities with substantive titles/descriptions; propose events."""
    store = _open_store(args)
    tpath = Path(args.training)
    if not tpath.exists():
        print(f"No training file at {tpath}", file=sys.stderr)
        return 1
    try:
        weeks = load_weeks(tpath)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load training JSONL: {exc}", file=sys.stderr)
        return 1

    baseline = store.load_survey_baseline(args.athlete_id)
    break_days = int(getattr(baseline, "recent_break_days", None) or 0) if baseline else 0
    cross = bool(getattr(baseline, "cross_trained_during_break", False)) if baseline else False

    weeks_sorted = sorted(weeks, key=lambda w: str(w.get("week_start") or ""))
    n_weeks = max(1, int(args.weeks))
    picked = weeks_sorted[-n_weeks:] if weeks_sorted else []
    min_chars = max(1, int(args.min_chars))

    n_notes = 0
    n_props = 0
    for week in picked:
        for w in week.get("workouts") or []:
            name = str(w.get("name") or "").strip()
            desc = str(w.get("description") or "").strip()
            blob = f"{name}\n{desc}".strip()
            if len(blob) < min_chars:
                continue
            day = (w.get("start_date") or "")[:10]
            aid = str(w.get("activity_id") or "")
            url = str(w.get("url") or "")
            body = f"[Strava activity {day}] id={aid}\n{name}\n{desc}\n{url}".strip()
            tags = ["strava_activity"]
            if aid:
                tags.append(f"activity_id:{aid}")
            note_ev = EventRecord(
                athlete_id=args.athlete_id,
                source="strava",
                status="applied",
                payload=CoachNotePayload(text=body, tags=tags),
            )
            store.append_event_record(note_ev)
            n_notes += 1
            proposed = extract_events(
                body,
                athlete_id=args.athlete_id,
                break_days=break_days,
                cross_trained=cross,
                race_date=getattr(baseline, "race_date", None) if baseline else None,
                block_weeks=getattr(baseline, "block_weeks", None) if baseline else None,
            )
            for ev in proposed:
                store.append_event_record(ev)
                print(f"  proposed {event_type_name(ev.payload)}: {ev.payload.model_dump_json()}")
                n_props += 1
    print(
        f"Recorded {n_notes} activity note(s) + {n_props} proposed event(s) for "
        f"{args.athlete_id}. Run `python main.py review {args.athlete_id}` to approve."
    )
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    """Interactive approval for proposed events; optional replan after any approval."""
    store = _open_store(args)
    rows = store.list_events(args.athlete_id, status="proposed")
    if not rows:
        print(f"No proposed events for {args.athlete_id}.")
        return 0

    survey = store.load_survey_baseline(args.athlete_id)
    today_utc = datetime.now(timezone.utc).date()
    window: tuple[date, date] | None = None
    if survey is not None:
        window = date_window(
            today_utc,
            getattr(survey, "race_date", None),
            getattr(survey, "block_weeks", None),
        )

    auto = (os.environ.get("Z2TC_REVIEW_AUTO") or "").strip().lower() == "all"
    approved_any = False
    for row in rows:
        eid = row["id"]
        try:
            payload = parse_event_payload(json.loads(row["payload_json"]))
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[skip bad payload] {eid}: {exc}", file=sys.stderr)
            continue
        print(f"\n--- Proposed {eid} ({row['event_type']}) ---")
        print(payload.model_dump_json(indent=2))
        if window is not None:
            lo, hi = window
            for field_name, raw in payload_out_of_window_fields(payload, window):
                print(
                    f"  !! date warning: {field_name}={raw} is outside the plausible block window "
                    f"{lo.isoformat()}..{hi.isoformat()} - verify before approving."
                )
        if args.yes_all or auto:
            choice = "a"
        else:
            choice = (input("[A]pprove, [R]eject, [S]kip? ").strip() or "s").lower()[:1]
        if choice == "a":
            store.update_event_status(eid, "approved")
            approved_any = True
            print("  -> approved")
        elif choice == "r":
            store.update_event_status(eid, "rejected")
            print("  -> rejected")
        else:
            print("  -> skipped (still proposed)")

    if approved_any and not args.no_replan:
        if not survey:
            print("No survey baseline; cannot replan.", file=sys.stderr)
            return 1
        baseline = survey.to_athlete_inputs()
        plan = replan(baseline, store, args.athlete_id)
        resolved = resolve_inputs(baseline, store, args.athlete_id)
        nevents = len(store.list_events(args.athlete_id))
        fp = fingerprint_athlete_inputs(baseline) + f"_e{nevents}"
        pid = store.save_plan_artifact(args.athlete_id, plan, fp, resolved_inputs=resolved)
        print(f"Saved replan artifact {pid} after approvals.")
    return 0


def _cmd_mark_race(args: argparse.Namespace) -> int:
    """Tag a race's effort quality and/or exclude it from fitness/volume reads (directives)."""
    store = _open_store(args)
    if not args.quality and not args.exclude:
        print("Provide --quality and/or --exclude.", file=sys.stderr)
        return 1
    if args.quality:
        store.append_event_record(EventRecord(
            athlete_id=args.athlete_id, source="coach", status="applied",
            payload=EffortQualityPayload(race_date=args.race_date.isoformat(), quality=args.quality, note=args.note or ""),
        ))
        print(f"Tagged {args.race_date} effort={args.quality} for {args.athlete_id}.")
    if args.exclude:
        store.append_event_record(EventRecord(
            athlete_id=args.athlete_id, source="coach", status="applied",
            payload=DataExcludePayload(race_date=args.race_date.isoformat(), reason=args.note or ""),
        ))
        print(f"Excluded {args.race_date} from reads for {args.athlete_id}.")
    return 0


def _cmd_fitness_select(args: argparse.Namespace) -> int:
    """Resolve which race sets fitness from candidate races + recorded directives, detrain it,
    and (``--apply``) write a FitnessAnchor the next ``replan`` folds into ``vdot``."""
    from engine import readiness as rd
    from store.events import parse_event_payload

    store = _open_store(args)

    report_path = Path(args.report) if args.report else None
    if report_path is None:
        ath = store.get_athlete(args.athlete_id)
        sid = args.strava_id or (ath.strava_athlete_id if ath else None)
        if not sid:
            print("No --report and no Strava id on file; pass --report PATH.", file=sys.stderr)
            return 1
        report_path = PROJECT_ROOT / "output" / "marathon" / f"report_{sid}.json"
    if not report_path.exists():
        print(f"No report at {report_path}", file=sys.stderr)
        return 1
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read report: {exc}", file=sys.stderr)
        return 1
    races = report.get("all_races_detected") or []

    excluded: set[str] = set()
    effort: dict[str, str] = {}
    overrides: dict[str, int] = {}
    anchor = args.anchor_date.isoformat() if args.anchor_date else None
    for row in store.list_events(args.athlete_id):
        if row["status"] in ("proposed", "rejected"):
            continue
        try:
            p = parse_event_payload(json.loads(row["payload_json"]))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(p, DataExcludePayload):
            excluded.add(p.race_date)
        elif isinstance(p, EffortQualityPayload):
            effort[p.race_date] = p.quality
        elif isinstance(p, RaceEstimatePayload):
            overrides[p.race_date] = p.estimated_time_s
        elif isinstance(p, FitnessAnchorPayload) and anchor is None and p.race_date:
            anchor = p.race_date

    baseline = store.load_survey_baseline(args.athlete_id)
    break_days = args.break_days
    if break_days is None:
        break_days = int(getattr(baseline, "recent_break_days", None) or 0) if baseline else 0
    cross = bool(getattr(baseline, "cross_trained_during_break", False)) if baseline else False

    sel = rd.select_fitness_vdot(
        races, excluded_dates=excluded, effort_quality=effort, time_overrides=overrides,
        anchor_date=anchor, break_days=break_days, cross_trained=cross,
    )
    print(f"Considered: {', '.join(sel.considered) or '(none)'}")
    for d in sel.dropped:
        print(f"  dropped: {d}")
    for n in sel.notes:
        print(f"  note: {n}")
    if sel.effective_vdot is None:
        print("No eligible race — record a RaceEstimate or relax a directive.", file=sys.stderr)
        return 1
    print(f"→ {sel.source}: race VDOT {sel.race_vdot} → effective VDOT {sel.effective_vdot}")

    if args.apply:
        store.append_event_record(EventRecord(
            athlete_id=args.athlete_id, source="coach", status="applied",
            payload=FitnessAnchorPayload(
                race_date=sel.chosen_date, vdot=sel.effective_vdot, source=sel.source,
                note="resolved by fitness-select",
            ),
        ))
        print(f"Applied FitnessAnchor (VDOT {sel.effective_vdot}). Run `python main.py replan {args.athlete_id}`.")
    return 0


def _load_style_bundle(store: Store, bundle_path: str | None):
    """Resolve the club style bundle into ``(StyleSpec, spreadsheet_id)``. Precedence: an explicit
    ``--style-bundle`` file when it exists (override), then the store's cached bundle (`ingest-style`
    folds it into the `config` kv). Returns None (after printing why) when neither is available."""
    bundle = None
    if bundle_path:
        p = Path(bundle_path)
        if p.exists():
            try:
                bundle = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Could not read style bundle {p}: {exc}", file=sys.stderr)
                return None
    if bundle is None:
        bundle = store.get_config(STYLE_BUNDLE_KEY)
    if bundle is None:
        print("No style bundle (file or store). Run `python main.py ingest-style` first.", file=sys.stderr)
        return None
    try:
        spec = StyleSpec(**bundle["style_spec"])
    except (KeyError, TypeError, ValidationError) as exc:
        print(f"Malformed style bundle: {exc}", file=sys.stderr)
        return None
    return spec, str(bundle.get("spreadsheet_id") or default_club_spreadsheet_id())


def _tab_title_for_athlete(store, plan) -> str | None:
    """Tab label: the athlete's first name, dropping the last name unless another athlete in the
    store shares that first name (then keep the full name to disambiguate). Returns ``None`` when the
    plan has no athlete name (render falls back to its own default)."""
    full = (plan.athlete or "").strip()
    if not full:
        return None
    first = full.split()[0]
    try:
        names = [a.name for a in store.list_athletes() if a.name]
    except Exception:  # noqa: BLE001 — roster lookup must not break a publish
        names = []
    shared = sum(1 for n in names if n.split() and n.split()[0].lower() == first.lower())
    return full if shared > 1 else first


def _cmd_publish_sheet(args: argparse.Namespace) -> int:
    store = _open_store(args)
    resolved = _load_style_bundle(store, args.style_bundle)
    if resolved is None:
        return 1
    spec, ss_id = resolved
    art = store.load_latest_plan(args.athlete_id)
    if not art:
        print("No plan artifact; run build-plan or replan first.", file=sys.stderr)
        return 1
    plan = store.plan_from_artifact(art)
    folded_inputs = None
    survey = store.load_survey_baseline(args.athlete_id)
    if survey is not None:
        from engine.plan.replan import fold_events_to_inputs

        folded_inputs, _ = fold_events_to_inputs(survey.to_athlete_inputs(), store, args.athlete_id)
    history = None
    block = store.latest_training_block(args.athlete_id)
    if block is not None and block.profile:
        history = {
            "profile": block.profile,
            "marathon_name": block.marathon_name,
            "marathon_time_s": block.marathon_time_s,
        }
    # Landed tune-up results (chronological) drive the on-track/behind indicator on the sheet.
    # Monitor + weekly-evaluation events feed the execution-aware narrative (weekly whys + notes).
    from engine.execution import summarize_execution
    from store.events import parse_event_payload

    tune_up_results: list[tuple[float, int, float]] = []
    exec_payloads: list = []
    for ev in store.list_events(args.athlete_id):
        et = ev["event_type"]
        if et == "TuneUpResult":
            try:
                payload = json.loads(ev["payload_json"])
                tune_up_results.append(
                    (float(payload["distance_m"]), int(payload["time_s"]), float(payload["new_vdot"]))
                )
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                continue
        elif et in ("AdherenceFlag", "MissedQuality", "WeeklyEvaluation") and ev["status"] not in ("proposed", "rejected"):
            try:
                exec_payloads.append(parse_event_payload(json.loads(ev["payload_json"])))
            except (ValueError, json.JSONDecodeError):
                continue

    # Prefer scoring *every* elapsed week from a current-block feed (--training): on-plan weeks get
    # earned positive reinforcement, not just the absence of a monitor flag. Fall back to the
    # shortfall-only events path when no feed is supplied.
    weekly_actuals: dict[str, float] | None = None
    feed_arg = getattr(args, "training", None)
    if feed_arg:
        feed_path = Path(feed_arg)
        if feed_path.exists():
            from engine.analyze import load_weeks, summarize

            try:
                weekly_actuals = summarize(load_weeks(feed_path)).weekly_run_miles
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Could not read training feed {feed_path}: {exc}", file=sys.stderr)
            if weekly_actuals:
                # Persist so later runs (and other commands) can score execution from the store
                # without this file. Best-effort — never fail a publish on the side write.
                try:
                    n = store.upsert_weekly_actuals(args.athlete_id, weekly_actuals)
                    print(f"Persisted {n} week(s) of actuals to the store.", file=sys.stderr)
                except Exception as exc:  # noqa: BLE001
                    print(f"Could not persist weekly actuals: {exc}", file=sys.stderr)
        else:
            print(f"No training feed at {feed_path}; using stored actuals if present.", file=sys.stderr)
    if not weekly_actuals:
        # No usable feed this run → replay the actuals already persisted for the season.
        stored = store.load_weekly_actuals(args.athlete_id)
        if stored:
            weekly_actuals = stored
    if weekly_actuals:
        from engine.execution import execution_from_actuals

        execution = execution_from_actuals(plan, weekly_actuals, payloads=exec_payloads)
    else:
        execution = summarize_execution(exec_payloads) if exec_payloads else None

    dossier = _load_dossier(store, args.athlete_id)
    _capture_dossier_snapshot(
        store, args.athlete_id, dossier, inputs_fingerprint=art.inputs_hash,
    )

    capture: list = []
    meta = render_plan(
        plan,
        spec,
        spreadsheet_id=ss_id,
        sheet_title=args.sheet_title or _tab_title_for_athlete(store, plan),
        hidden=bool(args.hidden),
        inputs=folded_inputs,
        history=history,
        tune_up_results=tune_up_results or None,
        dossier=dossier,
        execution=execution,
        llm_narrative=bool(getattr(args, "llm_narrative", False)),
        capture=capture,
    )
    # Append-only narrative observability log (deterministic vs final per surface) for the
    # distillation analysis (`narrative-log`). Each render is linked to the plan artifact it
    # described. Best-effort: never fail a publish on logging.
    logged = 0
    for rec in capture:
        rec.athlete_id = args.athlete_id
        rec.plan_artifact_id = art.id
        try:
            store.append_narrative_render(rec)
            logged += 1
        except Exception as exc:  # noqa: BLE001
            print(f"Narrative capture skipped ({rec.surface}): {exc}", file=sys.stderr)
    if logged:
        print(f"Captured {logged} narrative render(s) for analysis.", file=sys.stderr)

    # Lineage: record that this plan artifact was published to this sheet, with the engine /
    # narrative versions in force. Best-effort — a logging failure must not fail the publish.
    try:
        store.record_publication(_publication_from_render(args.athlete_id, art, meta, ss_id, capture))
    except Exception as exc:  # noqa: BLE001
        print(f"Publication record skipped: {exc}", file=sys.stderr)

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def _cmd_tune_up_plan(args: argparse.Namespace) -> int:
    """Forward-looking tune-up race checkpoints: when to race, the time that keeps the A-goal
    alive, and the realistic mark below which the goal should be re-anchored."""
    from dataclasses import asdict

    from engine.readiness import _fmt_clock, tune_up_ladder

    store = _open_store(args)
    art = store.load_latest_plan(args.athlete_id)
    if not art:
        print("No plan artifact; run build-plan or replan first.", file=sys.stderr)
        return 1
    plan = store.plan_from_artifact(art)
    goal_s = plan.goal.get("goal_time_s")
    if not goal_s:
        print("Plan has no goal time to size tune-ups against.", file=sys.stderr)
        return 1
    build_weeks = sum(1 for w in plan.weeks if w.phase != "Taper") or 15
    taper_weeks = sum(1 for w in plan.weeks if w.phase == "Taper")
    survey = store.load_survey_baseline(args.athlete_id)
    race_date = survey.race_date if survey is not None else None

    ladder = tune_up_ladder(
        plan.vdot, goal_s, build_weeks=build_weeks, taper_weeks=taper_weeks, race_date=race_date
    )
    if args.json:
        print(json.dumps(asdict(ladder), ensure_ascii=False, indent=2))
        return 0

    print(f"Tune-up plan — {plan.athlete or args.athlete_id}  [{ladder.verdict}]")
    req = f"VDOT {ladder.required_vdot}" if ladder.required_vdot else "VDOT n/a"
    print(
        f"Goal {_fmt_clock(goal_s)} needs {req} · current VDOT {ladder.current_vdot} · "
        f"projected ~{ladder.projected_vdot} · realistic ~{_fmt_clock(ladder.realistic_time_s)}\n"
    )
    print(f"  {'Wk':>3}  {'When':<11}  {'Race':<14}  {'On-track (goal)':<16}  {'Realistic':<10}")
    for c in ladder.checkpoints:
        when = c.date or f"~{c.weeks_before_race} wk out"
        on_track = "\u2264 " + _fmt_clock(c.on_track_time_s)
        print(f"  {c.week:>3}  {when:<11}  {c.label:<14}  {on_track:<16}  {_fmt_clock(c.projected_time_s):<10}")
    if ladder.notes:
        print()
        for n in ladder.notes:
            print(f"  • {n}")
    return 0


def _cmd_record_tune_up(args: argparse.Namespace) -> int:
    """Record an *actual* tune-up race result: compute the VDOT it showed, log a TuneUpResult event
    (folded into the athlete's VDOT on the next replan), and report whether the marathon goal is on
    track or should be re-anchored. Assumes a genuine race effort — that's what makes the VDOT real."""
    from engine import readiness as rd
    from engine.vdot import RACE_METERS, predict_race_time, vdot_from_race

    store = _open_store(args)
    dist_label = _DISTANCE_CHOICES[args.distance]
    dist_m = RACE_METERS[dist_label]
    measured = vdot_from_race(dist_m, args.time)
    if measured is None:
        print("Could not compute VDOT for that distance/time.", file=sys.stderr)
        return 1

    race_date_str = getattr(args, "race_date", None) or date.today().isoformat()
    store.append_event_record(
        EventRecord(
            athlete_id=args.athlete_id, source="coach", status="applied",
            payload=TuneUpResultPayload(
                distance_m=dist_m, time_s=args.time, new_vdot=measured, race_date=race_date_str,
            ),
        )
    )

    # Re-anchor read: project the measured fitness over the weeks left to the race and see where it
    # leaves the marathon goal (same advisory heuristic as `tune-up-plan`).
    survey = store.load_survey_baseline(args.athlete_id)
    goal_s = survey.goal_marathon_s if survey else None
    race_date = survey.race_date if survey else None
    weeks_left: int | None = None
    if race_date:
        try:
            weeks_left = max(1, (date.fromisoformat(race_date) - date.today()).days // 7)
        except ValueError:
            weeks_left = None

    marathon_equiv = predict_race_time(measured, RACE_METERS["Marathon"])
    ga = rd.goal_feasibility(measured, goal_s, build_weeks=weeks_left or 8) if goal_s else None

    if args.json:
        print(json.dumps(
            {
                "athlete_id": args.athlete_id, "distance": dist_label, "time_s": args.time,
                "measured_vdot": measured, "marathon_equivalent_s": marathon_equiv,
                "goal_s": goal_s, "weeks_left": weeks_left,
                "required_vdot": ga.required_vdot if ga else None,
                "verdict": ga.verdict if ga else None,
                "realistic_time_s": ga.realistic_time_s if ga else None,
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    print(f"Recorded tune-up for {args.athlete_id}: {dist_label} {_fmt_hms(args.time)} \u2192 VDOT {measured}.")
    if marathon_equiv:
        print(f"  Marathon-equivalent at this fitness: ~{_fmt_hms(marathon_equiv)}.")
    if ga:
        horizon = f" over the ~{weeks_left} wk left" if weeks_left else ""
        gap = f"{ga.gap_vdot:+g} vs measured" if ga.gap_vdot is not None else "n/a"
        print(f"  Goal {_fmt_hms(goal_s)} needs VDOT {ga.required_vdot} ({gap}){horizon} \u2014 verdict: {ga.verdict}.")
        if ga.verdict in ("within_current", "in_reach"):
            print("  On track \u2014 hold the goal.")
        elif ga.realistic_time_s:
            print(f"  Re-anchor recommendation: aim near ~{_fmt_hms(ga.realistic_time_s)} (projected-fitness equivalent).")
    print(f"  Run `python main.py replan {args.athlete_id}` to fold the new VDOT into the plan.")
    return 0


def _parse_total_distance(s: object) -> float:
    try:
        return float(str(s).split("mi")[0].strip())
    except (ValueError, AttributeError):
        return 0.0


def _weekly_volumes(rows: list[dict]) -> list:
    """Parse scraped/feed week dicts (``week_start`` + ``total_distance``) into ``WeeklyVolume`` rows."""
    from engine import athlete_profile as ap

    return [
        ap.WeeklyVolume(
            week_start=str(w.get("week_start") or ""),
            miles=_parse_total_distance(w.get("total_distance")),
        )
        for w in rows
    ]


def _resolve_report_data(override, block, default_path):
    """Marathon-report dict for the dossier. Source precedence: an explicit ``--report`` file, then
    the durable training block in the store (``training_blocks.report_json``), then the
    ``output/marathon/`` default file as a last resort (e.g. a ``--no-store`` scrape)."""
    if override is not None:
        if not override.exists():
            return None
        try:
            return json.loads(override.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    if block is not None and block.report:
        return block.report
    if default_path is not None and default_path.exists():
        try:
            return json.loads(default_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _resolve_feed_weeks(override, block, default_path):
    """Weekly-volume feed (trailing-volume context per race). Same precedence as the report: an
    explicit ``--training`` file, then the stored block's weeks (``training_blocks.weeks_json``),
    then the ``output/marathon/`` default feed. ``None`` when nothing is available."""
    from engine.analyze import load_weeks

    if override is not None:
        return _weekly_volumes(load_weeks(override)) if override.exists() else None
    if block is not None and block.weeks:
        return _weekly_volumes(block.weeks)
    if default_path is not None and default_path.exists():
        return _weekly_volumes(load_weeks(default_path))
    return None


def _publication_from_render(athlete_id, art, meta, spreadsheet_id, capture):
    """Assemble a `Publication` lineage row from a finished publish: the plan artifact, the sheet
    `meta`, and the per-surface narrative captures (for the version + source provenance)."""
    from store.models import Publication

    template_version = next((c.template_version for c in capture), None)
    prompt_version = next((c.prompt_version for c in capture if c.prompt_version), None)
    llm_model = next((c.llm_model for c in capture if c.llm_model), None)
    sources = {c.source for c in capture}
    if not sources:
        narrative_source = None
    elif sources == {"llm"}:
        narrative_source = "llm"
    elif "llm" in sources:
        narrative_source = "mixed"
    else:
        narrative_source = "deterministic"
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit" if spreadsheet_id else None
    return Publication(
        athlete_id=athlete_id,
        plan_artifact_id=art.id,
        season_id=art.season_id,
        spreadsheet_id=spreadsheet_id,
        sheet_title=meta.get("sheet_title"),
        url=url,
        engine_version=art.engine_version,
        template_version=template_version,
        prompt_version=prompt_version,
        llm_model=llm_model,
        narrative_source=narrative_source,
        rows_written=meta.get("rows_written"),
        meta={k: meta.get(k) for k in ("layout", "weeks", "hidden") if k in meta},
    )


# Coach-marked pronouns by athlete (normalized first name). The per-athlete `SurveyInputs.pronouns`
# baseline field wins when set; this roster covers athletes the coach has marked but not yet built.
# Edit here to mark someone; unmarked athletes read gender-neutral in the dossier.
_CLUB_PRONOUNS: dict[str, str] = {
    "cindy": "she/her",
    "kelly": "she/her",
    "michelle": "she/her",
    "emily": "she/her",
    "tamara": "she/her",
    "gaurav": "he/him",
    "tanner": "he/him",
    "rohan": "he/him",
}


def _resolve_pronoun_spec(name: str | None, baseline: SurveyInputs | None) -> str | None:
    """Per-athlete `SurveyInputs.pronouns` override, else the coach roster keyed by first name."""
    spec = getattr(baseline, "pronouns", None)
    if spec:
        return spec
    first = (name or "").strip().split(" ")[0].lower()
    return _CLUB_PRONOUNS.get(first)


def _load_dossier(
    store: Store, athlete_id: str, *,
    strava_id: str | None = None, report: str | None = None,
    training: str | None = None, marathon_dir: str | None = None,
):
    """Assemble the read-only `AthleteDossier` from the store baseline + latest plan + the
    output/marathon/ artifacts. Shared by `athlete-report` and `publish-sheet`. None when there is no
    survey baseline. Pure-data assembly: the dossier math itself lives in `engine.athlete_profile`."""
    from engine import athlete_profile as ap

    baseline = store.load_survey_baseline(athlete_id)
    if baseline is None:
        return None

    # Prefer the latest plan's (folded) VDOT + opener — that's what's actually driving paces.
    art = store.load_latest_plan(athlete_id)
    plan = store.plan_from_artifact(art) if art else None
    current_vdot = plan.vdot if plan else baseline.vdot
    current_opener = round(plan.weeks[0].planned_miles, 1) if plan and plan.weeks else None
    if plan:
        build_weeks = sum(1 for w in plan.weeks if w.phase != "Taper") or len(plan.weeks)
    else:
        build_weeks = max(1, (baseline.block_weeks or 18) - 3)

    # Demonstrated volume comes from the last training block's capacity profile.
    block = store.latest_training_block(athlete_id)
    volume_weeks: list[ap.WeeklyVolume] = []
    for w in ((block.profile or {}).get("weeks") if block else None) or []:
        volume_weeks.append(ap.WeeklyVolume(
            week_start=str(w.get("week_start") or ""), miles=float(w.get("week_mi") or 0.0),
            run_days=int(w.get("run_days") or 0), long_pct=float(w.get("long_pct") or 0.0),
            race_week=bool(w.get("race_week")),
        ))

    # Race history + the weekly feed: prefer the durable training block already persisted in the
    # store (``training_blocks``), which holds the same report + weeks an earlier `marathon-report`
    # wrote. Explicit --report/--training paths override the store; the output/marathon/ files are a
    # last-resort fallback so the dossier no longer silently depends on those artifacts surviving.
    ath = store.get_athlete(athlete_id)
    sid = strava_id or (ath.strava_athlete_id if ath else None)
    mdir = Path(marathon_dir) if marathon_dir else (PROJECT_ROOT / "output" / "marathon")

    report_data = _resolve_report_data(
        Path(report) if report else None,
        block,
        (mdir / f"report_{sid}.json") if sid else None,
    )
    races: list[ap.RacePerformance] = []
    source_date: str | None = None
    if report_data:
        for row in report_data.get("all_races_detected") or []:
            rp = ap.race_from_detected(row)
            if rp is not None:
                races.append(rp)
        source_date = ((report_data.get("recommended_vdot") or {}).get("source_race") or {}).get("date")
    if source_date is None and races:
        source_date = max(r.date for r in races)

    # Fold applied tune-up results into the timeline so a fresh tune-up shows up as a dated fitness
    # read and resolves a stale anchor (closes the record-tune-up → dossier flywheel). Tune-ups carry
    # the VDOT measured at write time, so this only re-shapes data — the dossier math stays pure.
    for ev in store.list_events(athlete_id, status="applied"):
        if ev["event_type"] != "TuneUpResult":
            continue
        try:
            payload = json.loads(ev["payload_json"])
        except (TypeError, ValueError):
            continue
        tu_date = payload.get("race_date") or str(ev["ts"] or "")[:10]
        rp = ap.race_from_tune_up(
            payload.get("distance_m"), payload.get("time_s"), payload.get("new_vdot"), tu_date,
        )
        if rp is None:
            continue
        races.append(rp)
        if rp.date and (source_date is None or rp.date > source_date):
            source_date = rp.date

    feed_weeks = _resolve_feed_weeks(
        Path(training) if training else None,
        block,
        (mdir / f"training_{sid}.jsonl") if sid else None,
    )

    goals = [
        ("A", baseline.goal_marathon_s),
        ("B", getattr(baseline, "goal_marathon_b_s", None)),
        ("C", getattr(baseline, "goal_marathon_c_s", None)),
    ]
    goals = [(lbl, t) for lbl, t in goals if t]

    return ap.build_dossier(
        baseline.name or athlete_id,
        volume_weeks=volume_weeks, races=races, feed_weeks=feed_weeks,
        current_vdot=current_vdot, goals=goals, source_date=source_date,
        build_weeks=build_weeks, today=date.today(),
        injury_prone=bool(baseline.injury_prone), current_opener_mpw=current_opener,
        pronouns=_resolve_pronoun_spec(baseline.name or athlete_id, baseline),
    )


def _capture_dossier_snapshot(
    store: Store, athlete_id: str, dossier, *, inputs_fingerprint: str = ""
) -> None:
    """Append a `DossierSnapshot` of the just-computed dossier (best-effort, append-only).

    Capture is provenance/accumulation, not plan state — failures are swallowed so a report or
    publish never breaks on the side write. The flattened columns mirror the fleet-analytics query."""
    from dataclasses import asdict

    from engine.athlete_profile import DOSSIER_VERSION
    from store.models import DossierSnapshot

    if dossier is None:
        return
    v, f, a = dossier.volume, dossier.fitness, dossier.anchor
    baseline = store.load_survey_baseline(athlete_id)
    injury_prone = bool(baseline.injury_prone) if baseline else None
    try:
        snap = DossierSnapshot(
            athlete_id=athlete_id,
            dossier_version=DOSSIER_VERSION,
            inputs_fingerprint=inputs_fingerprint,
            full_json=asdict(dossier),
            responder=f.responder,
            demonstrated_opener_mpw=v.demonstrated_opener_mpw,
            peak_mpw=v.peak_mpw,
            sustainable_low_mpw=v.sustainable_low_mpw,
            sustainable_high_mpw=v.sustainable_high_mpw,
            volume_vdot_corr=f.volume_vdot_corr,
            endurance_gap=f.endurance_gap,
            current_vdot=f.current_vdot,
            anchor_age_days=a.age_days,
            anchor_stale=a.stale,
            injury_prone=injury_prone,
        )
        store.append_dossier_snapshot(snap)
    except Exception as exc:  # noqa: BLE001
        print(f"Dossier snapshot capture skipped: {exc}", file=sys.stderr)


def _cmd_athlete_report(args: argparse.Namespace) -> int:
    """Read-only athlete dossier: demonstrated volume (opener / sustainable band / peak), the VDOT-over-
    time race history + responder profile, goal realism (A/B/C), fitness-anchor staleness, and the
    coach-facing personalization recommendations. Reads the store + the output/marathon/ artifacts;
    mutates nothing. `--json` emits the full dossier."""
    from dataclasses import asdict

    from engine.readiness import _fmt_clock

    store = _open_store(args)
    if store.load_survey_baseline(args.athlete_id) is None:
        print(f"No survey baseline for {args.athlete_id}; run build-plan first.", file=sys.stderr)
        return 1
    dossier = _load_dossier(
        store, args.athlete_id, strava_id=args.strava_id,
        report=args.report, training=args.training, marathon_dir=args.marathon_dir,
    )
    _capture_dossier_snapshot(
        store, args.athlete_id, dossier,
        inputs_fingerprint=fingerprint_athlete_inputs(store.load_survey_baseline(args.athlete_id)),
    )

    if args.json:
        print(json.dumps(asdict(dossier), ensure_ascii=False, indent=2))
        return 0

    v, f, a = dossier.volume, dossier.fitness, dossier.anchor
    current_vdot = f.current_vdot
    print(f"Athlete dossier — {dossier.name}  (current VDOT {current_vdot:g})")
    if v.active_weeks == 0 and not f.races:
        print("  (no training block or race artifacts on file — run marathon-report first for full analysis)")
    print("\nVolume (last block):")
    print(f"  opener ~{v.demonstrated_opener_mpw:g} mpw · sustainable {v.sustainable_low_mpw:g}–{v.sustainable_high_mpw:g} · "
          f"peak {v.peak_mpw:g} · avg {v.avg_active_mpw:g} · {v.active_weeks} active wk")
    for n in v.notes:
        print(f"    • {n}")

    print("\nFitness over time:")
    if f.races:
        print(f"  {'Date':<11} {'Race':<22} {'VDOT':>5}  {'Trail4wk':>8}")
        for r in f.races:
            tv = f"{r.trailing_4wk_mpw:g}" if r.trailing_4wk_mpw is not None else "—"
            print(f"  {r.date:<11} {r.name[:22]:<22} {r.vdot:>5}  {tv:>8}")
        span = f"{f.vdot_min}–{f.vdot_max}" if f.vdot_min is not None else "n/a"
        corr = f.volume_vdot_corr if f.volume_vdot_corr is not None else "n/a"
        print(f"  span {span} · volume↔VDOT r={corr} · responder: {f.responder}")
    else:
        print("  (no rated races on file)")
    for n in f.notes:
        print(f"    • {n}")

    print("\nGoal realism:")
    for g in dossier.goals:
        print(f"  {g.label}: {_fmt_clock(g.goal_time_s):<8} needs VDOT {g.required_vdot:<5} → {g.verdict} "
              f"(realistic ~{_fmt_clock(g.realistic_time_s)})")

    print(f"\nFitness anchor: {a.note}")

    if dossier.recommendations:
        print("\nRecommendations:")
        for r in dossier.recommendations:
            print(f"  • {r}")

    if dossier.proposed_inputs:
        print("\nProposed input changes (data-backed; coach approves via `review`):")
        for pi in dossier.proposed_inputs:
            cur = f" (current {pi.current})" if pi.current is not None else ""
            print(f"  • {pi.field} → {pi.value}{cur}")
            print(f"      {pi.rationale}")
        if getattr(args, "propose", False):
            return _write_dossier_proposals(store, args.athlete_id, dossier)
        print(
            f"\n  Re-run with --propose to log these as proposed events, then "
            f"`python main.py review {args.athlete_id}` to approve."
        )
    elif getattr(args, "propose", False):
        print("\nNo data-backed input changes to propose — the current plan already matches the dossier.")
    return 0


def _write_dossier_proposals(store: Store, athlete_id: str, dossier) -> int:
    """Append the dossier's `ProposedInput`s as `proposed` ManualOverride events (never applied),
    plus one applied CoachNote capturing the rationale as an audit trail. `review` approves them and
    replans — so the dossier informs the plan only with explicit coach sign-off, never silently."""
    provenance = "Dossier proposals (athlete-report --propose):\n" + "\n".join(
        f"- {pi.field} → {pi.value} (current {pi.current}): {pi.rationale}" for pi in dossier.proposed_inputs
    )
    store.append_event_record(
        EventRecord(
            athlete_id=athlete_id,
            source="coach",
            status="applied",
            payload=CoachNotePayload(text=provenance, tags=["dossier", "proposal_provenance"]),
        )
    )
    n = 0
    for pi in dossier.proposed_inputs:
        ev = EventRecord(
            athlete_id=athlete_id,
            source="coach",
            status="proposed",
            payload=ManualOverridePayload(field=pi.field, value=pi.value),
        )
        store.append_event_record(ev)
        print(f"  proposed {event_type_name(ev.payload)}: {ev.payload.model_dump_json()}")
        n += 1
    print(
        f"\nLogged {n} proposed event(s) + provenance note for {athlete_id}. "
        f"Run `python main.py review {athlete_id}` to approve (nothing changes until you do)."
    )
    return 0


def _cmd_narrative_log(args: argparse.Namespace) -> int:
    """Distillation monitor: per-surface, how often the optional LLM pass actually changed the
    deterministic narrative, by how much, and the guard pass rate. Surfaces flagged
    `det-candidate` are ones the LLM rarely changes — candidates to make fully deterministic and drop
    the LLM for. Read-only over the append-only `narrative_renders` log."""
    from engine.narrative_capture import summarize_surface_stats

    store = _open_store(args)
    rows = [dict(r) for r in store.list_narrative_renders(
        args.athlete_id, surface=args.surface, limit=args.limit,
    )]
    if not rows:
        scope = args.athlete_id or "any athlete"
        print(f"No captured narrative renders for {scope} yet — publish a sheet to start logging.")
        return 0

    stats = summarize_surface_stats(rows)
    if args.json:
        from dataclasses import asdict

        print(json.dumps({
            "renders": len(rows),
            "surfaces": [
                {**asdict(s), "llm_change_rate": s.llm_change_rate, "deterministic_candidate": s.deterministic_candidate}
                for s in stats
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    scope = args.athlete_id or "all athletes"
    print(f"Narrative distillation log — {scope}  ({len(rows)} render(s))")
    print(f"  {'Surface':<14} {'n':>4} {'LLM':>4} {'chg':>4} {'chg-rate':>9} {'~|Δch|':>7} {'guard✗':>7}  candidate")
    for s in stats:
        rate = f"{s.llm_change_rate:.3f}" if s.llm_change_rate is not None else "—"
        cand = "yes" if s.deterministic_candidate else "no"
        print(f"  {s.surface:<14} {s.n:>4} {s.llm_renders:>4} {s.llm_changed:>4} {rate:>9} "
              f"{s.mean_abs_char_delta:>7} {s.guard_failures:>7}  {cand}")
    print("\n  candidate = LLM observed ≥5× and changed the deterministic text <20% of the time →")
    print("  consider dropping the LLM for that surface and keeping the deterministic template.")
    return 0


def _cmd_dossier_log(args: argparse.Namespace) -> int:
    """Fleet/historical dossier analytics over the append-only `dossier_snapshots` log: responder
    distribution, fitness-anchor staleness, demonstrated-opener vs current-plan-opener gaps, and the
    goal-realism spread. With ``athlete_id`` it shows that athlete's signal trend across snapshots.
    Read-only — this is the surface where a fleet pattern earns an engine/policy change before any
    code change. Snapshots are written by `athlete-report` and `publish-sheet`."""
    from statistics import mean

    store = _open_store(args)
    rows = [dict(r) for r in store.list_dossier_snapshots(args.athlete_id, limit=args.limit)]
    if not rows:
        scope = args.athlete_id or "any athlete"
        print(f"No dossier snapshots for {scope} yet — run athlete-report or publish-sheet to start logging.")
        return 0

    responders: dict[str, int] = {}
    for r in rows:
        responders[r["responder"] or "unknown"] = responders.get(r["responder"] or "unknown", 0) + 1
    ages = [int(r["anchor_age_days"]) for r in rows if r["anchor_age_days"] is not None]
    stale_n = sum(1 for r in rows if r["anchor_stale"] == 1)
    corrs = [float(r["volume_vdot_corr"]) for r in rows if r["volume_vdot_corr"] is not None]
    gaps = [float(r["endurance_gap"]) for r in rows if r["endurance_gap"] is not None]

    if args.json:
        print(json.dumps({
            "snapshots": len(rows),
            "responder_distribution": responders,
            "anchor": {
                "stale": stale_n, "stale_pct": round(100 * stale_n / len(rows), 1),
                "age_days_mean": round(mean(ages), 1) if ages else None,
                "age_days_max": max(ages) if ages else None,
            },
            "volume_vdot_corr_mean": round(mean(corrs), 2) if corrs else None,
            "endurance_gap_mean": round(mean(gaps), 1) if gaps else None,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.athlete_id:
        print(f"Dossier snapshot trend — {args.athlete_id}  ({len(rows)} snapshot(s), newest first)")
        print(f"  {'When':<20} {'VDOT':>5} {'resp':<16} {'open':>5} {'peak':>5} {'r':>5} {'anchor':>8}")
        for r in rows:
            when = str(r["computed_at"])[:19]
            anchor = (f"{r['anchor_age_days']}d" if r["anchor_age_days"] is not None else "—")
            anchor += "✗" if r["anchor_stale"] == 1 else ""
            corr = r["volume_vdot_corr"] if r["volume_vdot_corr"] is not None else "—"
            print(f"  {when:<20} {r['current_vdot'] or '—':>5} {(r['responder'] or '—')[:16]:<16} "
                  f"{r['demonstrated_opener_mpw'] or '—':>5} {r['peak_mpw'] or '—':>5} {corr:>5} {anchor:>8}")
        return 0

    print(f"Fleet dossier analytics — {len(rows)} snapshot(s)")
    print("\nResponder distribution:")
    for resp, n in sorted(responders.items(), key=lambda kv: -kv[1]):
        print(f"  {resp:<18} {n:>4}  ({round(100 * n / len(rows))}%)")
    print("\nFitness anchor:")
    print(f"  stale: {stale_n}/{len(rows)} ({round(100 * stale_n / len(rows), 1)}%)"
          + (f" · age mean {round(mean(ages), 1)}d · max {max(ages)}d" if ages else ""))
    if corrs:
        print(f"\nVolume→VDOT correlation: mean r={round(mean(corrs), 2)} (n={len(corrs)})")
    if gaps:
        print(f"Endurance gap (short−marathon VDOT): mean {round(mean(gaps), 1)} (n={len(gaps)})")
    print("\n  This is the 'earn it with data' surface — a pattern shared across athletes here is")
    print("  the evidence for a future engine/policy change (changes stay deferred by design).")
    return 0


def _cmd_plan_log(args: argparse.Namespace) -> int:
    """Plan artifacts grouped by engine + club-policy version, joined to the season's weekly-actuals
    adherence. Read-only. Caveat: adherence is     season-scoped, so a mid-season replan attributes the
    whole season's actuals to whichever artifact is queried — treat the join as directional, not exact."""
    store = _open_store(args)
    arts = store.list_plan_artifacts(args.athlete_id, limit=args.limit)
    if not arts:
        scope = args.athlete_id or "any athlete"
        print(f"No plan artifacts for {scope} yet — run build-plan first.")
        return 0

    groups: dict[tuple[str, str], int] = {}
    for a in arts:
        key = (a.engine_version or "—", a.club_policy_version or "—")
        groups[key] = groups.get(key, 0) + 1

    # Season-scoped adherence: mean(actual/prescribed) over elapsed scored weeks, reusing the same
    # plan↔week mapping the monitor and execution scorer use.
    from engine.execution import execution_from_actuals

    def _adherence(art) -> float | None:
        if not art.season_id:
            return None
        actuals = store.load_weekly_actuals(art.athlete_id, season_id=art.season_id)
        if not actuals:
            return None
        summary = execution_from_actuals(store.plan_from_artifact(art), actuals)
        return summary.mean_adherence

    if args.json:
        print(json.dumps({
            "artifacts": len(arts),
            "by_version": [
                {"engine_version": e, "club_policy_version": p, "count": n}
                for (e, p), n in sorted(groups.items())
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"Plan artifact analytics — {len(arts)} artifact(s)")
    print("\nBy engine × club-policy version:")
    print(f"  {'engine':<10} {'policy':<10} {'count':>6}")
    for (e, p), n in sorted(groups.items()):
        print(f"  {e:<10} {p:<10} {n:>6}")

    if args.athlete_id:
        print(f"\nAdherence (season-scoped) — {args.athlete_id}:")
        print(f"  {'When':<20} {'engine':<8} {'policy':<8} {'adherence':>10}")
        for a in arts:
            adh = _adherence(a)
            adh_s = f"{adh:.2f}" if adh is not None else "—"
            print(f"  {str(a.created_at)[:19]:<20} {(a.engine_version or '—'):<8} "
                  f"{(a.club_policy_version or '—'):<8} {adh_s:>10}")
        print("\n  Caveat: adherence is the whole season's actuals vs this plan's prescribed weeks;")
        print("  mid-season replans share one actuals series, so read the join as directional.")
    return 0


def _cmd_publish_club(args: argparse.Namespace) -> int:
    """Render the club-wide 'Long Runs', 'Read Me First', and 'Workout Dictionary' tabs."""
    from render.long_runs import ClubAthlete

    store = _open_store(args)
    resolved = _load_style_bundle(store, args.style_bundle)
    if resolved is None:
        return 1
    spec, ss_id = resolved

    if args.athletes:
        ids = [a.strip() for a in args.athletes.split(",") if a.strip()]
        athletes_meta = [store.get_athlete(i) for i in ids]
    else:
        athletes_meta = store.list_athletes()

    club: list = []
    for a in athletes_meta:
        if a is None:
            continue
        art = store.load_latest_plan(a.id)
        if not art:
            continue
        plan = store.plan_from_artifact(art)
        club.append((a, plan))
    if not club:
        print("No athletes with a plan artifact found. Run build-plan for the roster first.", file=sys.stderr)
        return 1

    # Spine: the explicit --spine athlete, else the plan whose race date is the club consensus
    # (most common across the roster) with the most weeks.
    if args.spine:
        spine = next((p for a, p in club if a.id == args.spine or a.name == args.spine), None)
        if spine is None:
            print(f"--spine {args.spine!r} not in the roster.", file=sys.stderr)
            return 1
    else:
        from collections import Counter

        dates = Counter(str(p.goal.get("date"))[:10] for _, p in club)
        consensus = dates.most_common(1)[0][0]
        candidates = [p for _, p in club if str(p.goal.get("date"))[:10] == consensus]
        spine = max(candidates, key=lambda p: len(p.weeks))

    roster = [ClubAthlete(a.name, p) for a, p in club]
    from render.long_runs import season_marathons

    marathons = season_marathons([p for _, p in club])
    out: dict = {}
    if args.only in (None, "longruns"):
        out["long_runs"] = render_long_runs(spine, roster, spec, spreadsheet_id=ss_id, sheet_title=args.long_runs_title)
    if args.only in (None, "readme"):
        out["read_me"] = render_read_me(spine, spec, spreadsheet_id=ss_id, sheet_title=args.read_me_title, athletes=[a.name for a, _ in club], marathons=marathons)
    if args.only in (None, "dictionary"):
        out["workout_dictionary"] = render_workout_dictionary(spec, spreadsheet_id=ss_id, sheet_title=args.dictionary_title)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_coach_margin(args: argparse.Namespace) -> int:
    """Show actual vs estimated race times, VDOT margin, Daniels paces, and Table 15.1 effect."""
    from engine.analyze import MILES_PER_METER
    from engine import readiness as rd
    from engine.paces import training_paces
    from engine.vdot import RACE_METERS, race_equivalent_times, vdot_from_race

    dist_key = _DISTANCE_CHOICES[args.distance]
    dist_m = RACE_METERS[dist_key]
    if args.actual_time is None:
        print("Provide --actual-time.", file=sys.stderr)
        return 1

    est_s: int | None = args.estimated_time
    est_note = ""
    if est_s is None and args.estimated_pace is not None:
        miles = dist_m * MILES_PER_METER
        est_s = int(round(miles * args.estimated_pace))
        est_note = f" (= {_fmt_pace_mi(args.estimated_pace)} × {miles:.2f} mi)"
    if est_s is None:
        print("Provide --estimated-time or --estimated-pace (M:SS per mile).", file=sys.stderr)
        return 1

    break_days = args.break_days
    if break_days is None and args.athlete_id:
        store = _open_store(args)
        baseline = store.load_survey_baseline(args.athlete_id)
        break_days = int(getattr(baseline, "recent_break_days", None) or 0) if baseline else 0
    break_days = int(break_days or 0)
    crossed = bool(args.cross_trained)

    actual_vdot = vdot_from_race(dist_m, args.actual_time)
    est_vdot = vdot_from_race(dist_m, est_s)
    if actual_vdot is None or est_vdot is None:
        print("Could not compute VDOT for the given times.", file=sys.stderr)
        return 1

    eff_actual = rd.adjusted_vdot(actual_vdot, break_days, crossed)
    eff_est = rd.adjusted_vdot(est_vdot, break_days, crossed)
    fresh_actual = rd.assess_freshness(actual_vdot, args.race_age_days, break_days,
                                       "leg_aerobic" if crossed else "none")
    fresh_est = rd.assess_freshness(est_vdot, args.race_age_days, break_days,
                                    "leg_aerobic" if crossed else "none")
    plan_actual = actual_vdot if fresh_actual.trust_race_vdot else eff_actual
    plan_est = est_vdot if fresh_est.trust_race_vdot else eff_est

    def pace_row(vdot: float) -> dict[str, str]:
        p = training_paces(vdot)
        return {
            "easy": str(p.get("easy", "")),
            "marathon": str(p.get("marathon", "")),
            "threshold": str(p.get("threshold", "")),
            "interval": str(p.get("interval", "")),
        }

    pa, pe = pace_row(plan_actual), pace_row(plan_est)
    equiv_actual = race_equivalent_times(plan_actual)
    equiv_est = race_equivalent_times(plan_est)

    print(f"Distance: {dist_key}")
    print(f"Break: {break_days} d not running"
          + (" (FVDOT-2 cross-train)" if crossed else " (FVDOT-1)"))
    print()
    print(f"{'':12} {'actual':>14} {'estimated':>14}")
    print(f"{'finish':12} {_fmt_hms(args.actual_time):>14} {_fmt_hms(est_s):>14}{est_note}")
    print(f"{'raw VDOT':12} {actual_vdot:14.1f} {est_vdot:14.1f}  (Δ {est_vdot - actual_vdot:+.1f})")
    print(f"{'plan VDOT':12} {plan_actual:14.1f} {plan_est:14.1f}  (Δ {plan_est - plan_actual:+.1f})")
    print(f"{'trust raw?':12} {str(fresh_actual.trust_race_vdot):>14} {str(fresh_est.trust_race_vdot):>14}")
    print()
    print("Daniels training paces at plan VDOT:")
    for label in ("easy", "marathon", "threshold", "interval"):
        print(f"  {label:10} {pa[label]:>16}  →  {pe[label]:>16}")
    print()
    print("Equivalent race times at plan VDOT:")
    for dist in ("5K", "10K", "Half Marathon", "Marathon"):
        print(f"  {dist:14} {_fmt_hms(equiv_actual[dist]):>10}  →  {_fmt_hms(equiv_est[dist]):>10}")
    return 0


def _cmd_pull_intake(args: argparse.Namespace) -> int:
    from store.intake_sheet import pull_survey_for_athlete

    if not args.match_name and not args.match_strava_id:
        print("Provide --match-name and/or --match-strava-id.", file=sys.stderr)
        return 1
    defaults_path = Path(args.defaults)
    if not defaults_path.exists():
        print(f"Missing --defaults file: {defaults_path}", file=sys.stderr)
        return 1
    try:
        defaults = SurveyInputs.model_validate_json(
            defaults_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid defaults JSON: {exc}", file=sys.stderr)
        return 1
    ss_id = args.spreadsheet_id or default_club_spreadsheet_id()
    try:
        survey, strava_id, row = pull_survey_for_athlete(
            defaults=defaults,
            spreadsheet_id=ss_id,
            tab=args.tab,
            match_name=args.match_name or None,
            match_strava_id=args.match_strava_id or None,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    body = survey.model_dump_json(indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        print(f"Wrote {out_path} (sheet row {row})", file=sys.stderr)
    else:
        print(body)
    if strava_id:
        print(f"# Strava athlete id: {strava_id}", file=sys.stderr)
    return 0


def _cmd_nyrr_races(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from lib.data_feeds.nyrr import list_chip_races_for_search

    try:
        rid, rows = list_chip_races_for_search(
            args.search,
            exclude_virtual=not args.include_virtual,
        )
    except (LookupError, OSError, RuntimeError) as exc:
        print(f"NYRR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"runner_id": rid, "races": [asdict(r) for r in rows]},
            indent=2,
            ensure_ascii=False,
        )
    )
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
    p_mr.add_argument(
        "--db",
        default=None,
        help="SQLite store path for the historical training-block snapshot (default output/z2tc.db).",
    )
    p_mr.add_argument(
        "--no-store",
        action="store_true",
        help="Skip persisting the training block to the store (files only).",
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

    p_pull = sub.add_parser(
        "pull-intake",
        help="Read club Intake tab → merged SurveyInputs JSON (Sheets API).",
    )
    p_pull.add_argument(
        "--defaults",
        required=True,
        type=Path,
        help="Base SurveyInputs JSON; non-empty sheet cells overlay (use Strava/numeric fill).",
    )
    p_pull.add_argument(
        "--match-name",
        default=None,
        help="Substring match on the athlete full_name column.",
    )
    p_pull.add_argument(
        "--match-strava-id",
        default=None,
        help="Exact Strava athlete id parsed from the strava column.",
    )
    p_pull.add_argument(
        "--tab",
        default="Intake",
        help="Linked Form responses tab name (default Intake).",
    )
    p_pull.add_argument(
        "--spreadsheet-id",
        default=None,
        help="Workbook id (default club workbook or Z2TC_CLUB_SPREADSHEET_ID).",
    )
    p_pull.add_argument(
        "--out",
        default=None,
        help="Write JSON to this path (default: print to stdout).",
    )
    p_pull.set_defaults(func=_cmd_pull_intake)

    p_nyrr = sub.add_parser(
        "nyrr-races",
        help="Look up official NYRR chip times (public RMS API used by results.nyrr.org).",
    )
    p_nyrr.add_argument(
        "--search",
        required=True,
        help='Runner name text (same box as the site), e.g. "Kelly Hession".',
    )
    p_nyrr.add_argument(
        "--include-virtual",
        action="store_true",
        help="Include NYRR Virtual* events in the race list.",
    )
    p_nyrr.set_defaults(func=_cmd_nyrr_races)

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

    p_ls = sub.add_parser("list-seasons", help="List an athlete's seasons (active marked with *).")
    p_ls.add_argument("athlete_id")
    p_ls.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_ls.set_defaults(func=_cmd_list_seasons)

    p_ss = sub.add_parser(
        "start-season",
        help="Carry the athlete forward into a new block: seed baseline from prior ending state + race history.",
    )
    p_ss.add_argument("athlete_id")
    p_ss.add_argument("--label", required=True, help='Season label, e.g. "2027 Boston".')
    p_ss.add_argument("--race-name", required=True, help="Primary race name for the new block.")
    p_ss.add_argument("--race-date", required=True, type=_parse_date, help="New A-race date (YYYY-MM-DD).")
    p_ss.add_argument("--goal", required=True, help="Goal finish time H:MM:SS for the new race.")
    p_ss.add_argument("--block-weeks", type=int, default=None, help="Override block length (default: carry prior).")
    p_ss.add_argument(
        "--completed-time",
        default=None,
        help="Actual finish time H:MM:SS of the just-completed marathon (adds it to the fitness scan).",
    )
    p_ss.add_argument(
        "--report",
        default=None,
        help="Optional marathon-report JSON; its all_races_detected feed the VDOT history scan.",
    )
    p_ss.add_argument("--break-days", type=int, default=0, help="Days off since last race (detraining).")
    p_ss.add_argument("--cross-trained", action="store_true", help="Leg-aerobic cross-training during the break.")
    p_ss.add_argument("--no-build", action="store_true", help="Seed the baseline only; skip building the plan.")
    p_ss.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_ss.set_defaults(func=_cmd_start_season)

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

    p_cn = sub.add_parser(
        "coach-note",
        help="Append a coach note, or an effort-corrected race estimate, to the event log.",
    )
    p_cn.add_argument("athlete_id")
    p_cn.add_argument("--text", default=None, help="Free-text coach note / estimate rationale.")
    p_cn.add_argument("--tag", action="append", help="Optional tag (repeatable).")
    p_cn.add_argument("--race-name", dest="race_name", default=None, help="Name of the race being estimated.")
    p_cn.add_argument("--race-date", dest="race_date", type=_parse_date, default=None, help="Race date YYYY-MM-DD.")
    p_cn.add_argument(
        "--distance", choices=sorted(_DISTANCE_CHOICES), default=None,
        help="Race distance for the estimate.",
    )
    p_cn.add_argument(
        "--estimated-time", dest="estimated_time", type=_parse_hms, default=None,
        help="Coach's effort-corrected finish time (H:MM:SS).",
    )
    p_cn.add_argument(
        "--actual-time", dest="actual_time", type=_parse_hms, default=None,
        help="As-recorded finish time (H:MM:SS), optional.",
    )
    p_cn.add_argument(
        "--break-days", dest="break_days", type=int, default=None,
        help="Days off used to detrain the estimate (default: athlete's recent_break_days).",
    )
    p_cn.add_argument(
        "--cross-trained", dest="cross_trained", action="store_true",
        help="Leg-aerobic cross-training during the break (FVDOT-2, smaller loss).",
    )
    p_cn.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_cn.set_defaults(func=_cmd_coach_note)

    p_pn = sub.add_parser(
        "propose-notes",
        help="Store raw coach text as a CoachNote; append LLM-proposed events (status=proposed).",
    )
    p_pn.add_argument("athlete_id")
    p_pn.add_argument("--text", default=None, help="Raw coach note (otherwise use --file).")
    p_pn.add_argument("--file", type=Path, default=None, help="Path to UTF-8 text file.")
    p_pn.add_argument("--tag", action="append", help="Optional tag on the CoachNote (repeatable).")
    p_pn.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_pn.set_defaults(func=_cmd_propose_notes)

    p_ia = sub.add_parser(
        "interpret-activities",
        help="Scan training.jsonl for long titles/descriptions; CoachNote + proposed events.",
    )
    p_ia.add_argument("athlete_id")
    p_ia.add_argument(
        "--training",
        required=True,
        type=Path,
        help="training.jsonl path (e.g. output/marathon/training_<id>.jsonl).",
    )
    p_ia.add_argument(
        "--weeks",
        type=int,
        default=4,
        help="How many trailing ISO weeks to scan (default 4).",
    )
    p_ia.add_argument(
        "--min-chars",
        dest="min_chars",
        type=int,
        default=40,
        help="Minimum combined title+description length (default 40).",
    )
    p_ia.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_ia.set_defaults(func=_cmd_interpret_activities)

    p_rev = sub.add_parser(
        "review",
        help="Review proposed events: approve/reject; replan when anything approved.",
    )
    p_rev.add_argument("athlete_id")
    p_rev.add_argument(
        "--yes-all",
        action="store_true",
        help="Approve all proposed events without prompting.",
    )
    p_rev.add_argument(
        "--no-replan",
        action="store_true",
        help="Do not save a new plan artifact after approvals.",
    )
    p_rev.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_rev.set_defaults(func=_cmd_review)

    p_mr2 = sub.add_parser(
        "mark-race",
        help="Tag a race's effort quality (max/submaximal/compromised) and/or exclude it.",
    )
    p_mr2.add_argument("athlete_id")
    p_mr2.add_argument("--race-date", dest="race_date", type=_parse_date, required=True, help="Race date YYYY-MM-DD.")
    p_mr2.add_argument("--quality", choices=["max", "submaximal", "compromised"], default=None)
    p_mr2.add_argument("--exclude", action="store_true", help="Exclude this race from fitness/volume reads.")
    p_mr2.add_argument("--note", default=None, help="Reason / context.")
    p_mr2.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_mr2.set_defaults(func=_cmd_mark_race)

    p_fs = sub.add_parser(
        "fitness-select",
        help="Resolve the fitness VDOT from candidate races + directives; --apply writes a FitnessAnchor.",
    )
    p_fs.add_argument("athlete_id")
    p_fs.add_argument("--report", default=None, help="Marathon report JSON (default: output/marathon/report_<strava-id>.json).")
    p_fs.add_argument("--strava-id", dest="strava_id", default=None, help="Strava id to locate the default report.")
    p_fs.add_argument("--anchor-date", dest="anchor_date", type=_parse_date, default=None, help="Pin this race date as the fitness source.")
    p_fs.add_argument("--break-days", dest="break_days", type=int, default=None, help="Override detraining days (default: athlete's recent_break_days).")
    p_fs.add_argument("--apply", action="store_true", help="Write the resolved FitnessAnchor event.")
    p_fs.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_fs.set_defaults(func=_cmd_fitness_select)

    p_cm = sub.add_parser(
        "coach-margin",
        help="Compare actual vs estimated race times: VDOT margin, Daniels paces, Table 15.1.",
    )
    p_cm.add_argument("--athlete-id", dest="athlete_id", default=None,
                      help="Load recent_break_days from survey baseline.")
    p_cm.add_argument("--distance", choices=list(_DISTANCE_CHOICES), required=True)
    p_cm.add_argument("--actual-time", dest="actual_time", type=_parse_hms, required=True)
    p_cm.add_argument("--estimated-time", dest="estimated_time", type=_parse_hms, default=None)
    p_cm.add_argument("--estimated-pace", dest="estimated_pace", type=_parse_pace_mi, default=None,
                      help="M:SS per mile (marathon/half time derived from distance).")
    p_cm.add_argument("--break-days", dest="break_days", type=int, default=None)
    p_cm.add_argument("--race-age-days", dest="race_age_days", type=int, default=None)
    p_cm.add_argument("--cross-trained", dest="cross_trained", action="store_true")
    p_cm.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_cm.set_defaults(func=_cmd_coach_margin)

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
        help="Tab title (default <athlete name>).",
    )
    p_pub.add_argument(
        "--hidden",
        action="store_true",
        help="Hide the tab after writing (draft plans in the club workbook).",
    )
    p_pub.add_argument(
        "--training",
        default=None,
        help="Current-block weekly feed (same JSONL `monitor` reads). When given, every elapsed week "
             "is scored on-plan/short so the narrative gives earned positive reinforcement; without it "
             "the narrative uses the shortfall-only monitor events.",
    )
    p_pub.add_argument(
        "--llm-narrative",
        dest="llm_narrative",
        action="store_true",
        help="Smooth the summary / personalization / notes prose via the LLM boundary (number-safe; "
             "falls back to deterministic text without an API key).",
    )
    p_pub.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_pub.set_defaults(func=_cmd_publish_sheet)

    p_tune = sub.add_parser(
        "tune-up-plan",
        help="Forward-looking tune-up race checkpoints (when to race + target times to confirm the goal).",
    )
    p_tune.add_argument("athlete_id")
    p_tune.add_argument("--json", action="store_true", help="Emit the full ladder as JSON.")
    p_tune.add_argument(
        "--db",
        default=None,
        help=f"SQLite path (default: {default_db_path()}).",
    )
    p_tune.set_defaults(func=_cmd_tune_up_plan)

    p_rt = sub.add_parser(
        "record-tune-up",
        help="Log an actual tune-up race result (folds VDOT on replan) and report goal tracking.",
    )
    p_rt.add_argument("athlete_id")
    p_rt.add_argument(
        "--distance", choices=sorted(_DISTANCE_CHOICES), required=True,
        help="Tune-up race distance (5k | 10k | half | marathon).",
    )
    p_rt.add_argument(
        "--time", type=_parse_hms, required=True,
        help="Actual finish time (H:MM:SS or MM:SS) — a genuine race effort.",
    )
    p_rt.add_argument(
        "--race-date", default=None,
        help="ISO date the tune-up was run (default: today). Freshens the dossier fitness anchor.",
    )
    p_rt.add_argument("--json", action="store_true", help="Emit the result + verdict as JSON.")
    p_rt.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_rt.set_defaults(func=_cmd_record_tune_up)

    p_ar = sub.add_parser(
        "athlete-report",
        help="Read-only athlete dossier: demonstrated volume, VDOT-over-time + responder profile, goal realism, recommendations.",
    )
    p_ar.add_argument("athlete_id")
    p_ar.add_argument("--strava-id", dest="strava_id", default=None, help="Strava id to locate report/training artifacts.")
    p_ar.add_argument("--report", default=None, help="Marathon report JSON (default: <marathon-dir>/report_<strava-id>.json).")
    p_ar.add_argument("--training", default=None, help="Training feed JSONL (default: <marathon-dir>/training_<strava-id>.jsonl).")
    p_ar.add_argument("--marathon-dir", dest="marathon_dir", default=str(PROJECT_ROOT / "output" / "marathon"),
                      help="Directory holding the report_/training_ artifacts.")
    p_ar.add_argument("--json", action="store_true", help="Emit the full dossier as JSON.")
    p_ar.add_argument(
        "--propose", action="store_true",
        help="Log the dossier's data-backed input changes as proposed events (+ a provenance CoachNote) "
             "for review/approval. Never applies them — run `review` to fold any in.",
    )
    p_ar.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_ar.set_defaults(func=_cmd_athlete_report)

    p_nl = sub.add_parser(
        "narrative-log",
        help="Distillation monitor: per-surface LLM-vs-deterministic change rate from the narrative_renders log.",
    )
    p_nl.add_argument("athlete_id", nargs="?", default=None,
                      help="Limit to one athlete (omit for fleet-wide analysis).")
    p_nl.add_argument("--surface", default=None, help="Limit to one surface (summary | personalized | notes).")
    p_nl.add_argument("--limit", type=int, default=None, help="Only the most recent N captured renders.")
    p_nl.add_argument("--json", action="store_true", help="Emit the aggregate as JSON.")
    p_nl.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_nl.set_defaults(func=_cmd_narrative_log)

    p_dl = sub.add_parser(
        "dossier-log",
        help="Fleet dossier analytics from dossier_snapshots: responder mix, anchor staleness, goal-realism spread.",
    )
    p_dl.add_argument("athlete_id", nargs="?", default=None,
                      help="Limit to one athlete's snapshot trend (omit for fleet-wide analysis).")
    p_dl.add_argument("--limit", type=int, default=None, help="Only the most recent N snapshots.")
    p_dl.add_argument("--json", action="store_true", help="Emit the aggregate as JSON.")
    p_dl.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_dl.set_defaults(func=_cmd_dossier_log)

    p_pl = sub.add_parser(
        "plan-log",
        help="Plan-artifact analytics: counts by engine × club-policy version, joined to season adherence.",
    )
    p_pl.add_argument("athlete_id", nargs="?", default=None,
                      help="Limit to one athlete (omit for fleet-wide analysis).")
    p_pl.add_argument("--limit", type=int, default=None, help="Only the most recent N artifacts.")
    p_pl.add_argument("--json", action="store_true", help="Emit the aggregate as JSON.")
    p_pl.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_pl.set_defaults(func=_cmd_plan_log)

    p_club = sub.add_parser(
        "publish-club",
        help="Render the club-wide 'Long Runs', 'Read Me First', and 'Workout Dictionary' tabs.",
    )
    p_club.add_argument(
        "--athletes",
        default=None,
        help="Comma-separated athlete ids/names for the columns (default: all athletes with a plan).",
    )
    p_club.add_argument(
        "--spine",
        default=None,
        help="Athlete id/name whose plan sets the club calendar (default: roster's consensus race).",
    )
    p_club.add_argument(
        "--only",
        choices=["longruns", "readme", "dictionary"],
        default=None,
        help="Render only one tab (default: all).",
    )
    p_club.add_argument("--long-runs-title", default="Long Runs", help="Long Runs tab title.")
    p_club.add_argument("--read-me-title", default="Read Me First", help="Read Me tab title.")
    p_club.add_argument("--dictionary-title", default="Workout Dictionary", help="Workout Dictionary tab title.")
    p_club.add_argument(
        "--style-bundle",
        default=str(PROJECT_ROOT / "output" / "club_workbook_style.json"),
        help="JSON from ingest-style (style_spec + spreadsheet_id).",
    )
    p_club.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    p_club.set_defaults(func=_cmd_publish_club)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
