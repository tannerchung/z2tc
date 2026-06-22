#!/usr/bin/env python3
"""Merge marathon-report JSON + optional NYRR chip times into a base SurveyInputs JSON.

Use this after ``marathon-report`` (Strava) when you want official NYRR clock times for
races that exist on both feeds, then refresh ``vdot``, ``w_now``, ``p_history``, and
longest-run fields before ``build-plan``.

Example::

    python scripts/merge_report_nyrr_survey.py \\
        --base /tmp/kelly_intake.json \\
        --report output/kelly_strava/report_42251408.json \\
        --training output/kelly_strava/training_42251408.jsonl \\
        --nyrr-search \"Kelly Hession\" \\
        -o /tmp/kelly_survey_merged.json

    python scripts/run_kelly_demo.py --survey /tmp/kelly_survey_merged.json \\
        --strava-id 42251408 --athlete-id kelly-live \\
        --training output/kelly_strava/training_42251408.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from engine.analyze import _filter_weeks, fmt_duration, summarize
from engine.readiness import classify_cross_training
from engine.vdot import recommended_vdot
from lib.data_feeds.nyrr import list_chip_races_for_search
from store.models import SurveyInputs

# A week under this many run miles counts as "not running" for break detection.
OFF_WEEK_MILES = 1.0


def _load_weeks(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL in {path}: {exc}") from exc
    return out


def _w_now_post_marathon(weeks: list[dict], marathon_date: date, today: date) -> float:
    post = _filter_weeks(weeks, marathon_date + timedelta(days=1), today)
    summ = summarize(post)
    weekly = sorted(summ.weekly_run_miles.items(), key=lambda kv: kv[0])
    if not weekly:
        return 0.0
    last_n = [m for _, m in weekly[-4:]]
    return round(sum(last_n) / len(last_n), 1)


def _longest_break_days(weeks: list[dict], since: date, today: date) -> int:
    """Longest run of consecutive low-mileage weeks since ``since`` → days (×7).

    This is the *fitness-clock* break signal for Daniels Table 15.1 (engine/readiness):
    a genuine gap of **not running**, not an off-season dip in mileage. Weekly granularity,
    so it rounds to whole weeks — good enough to flag a category II+ layoff for the coach."""
    summ = summarize(_filter_weeks(weeks, since, today))
    weekly = sorted(summ.weekly_run_miles.items(), key=lambda kv: kv[0])
    longest = run = 0
    for _, miles in weekly:
        run = run + 1 if (miles or 0.0) < OFF_WEEK_MILES else 0
        longest = max(longest, run)
    return longest * 7


def _cross_training_during_break(
    activities: list[dict], since: date, today: date
) -> tuple[bool, str | None]:
    """Classify cross-training in the lead-up window from Strava ``sport_type`` counts
    (engine/readiness.classify_cross_training): leg-aerobic offsets detraining (FVDOT-2),
    strength/mobility does not."""
    counts: dict[str, int] = {}
    for a in activities:
        sport = str(a.get("sport_type") or a.get("type") or "")
        if sport in ("Run", "TrailRun", "VirtualRun", ""):
            continue
        ds = str(a.get("start_date") or a.get("start_date_local") or "")[:10]
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if since <= d <= today:
            counts[sport] = counts.get(sport, 0) + 1
    if not counts:
        return False, None
    bucket = classify_cross_training(list(counts))
    total = sum(counts.values())
    summary = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    return bucket == "leg_aerobic", f"{summary} ({total} acts; {bucket})"


def _apply_nyrr_to_races(
    races: list[dict], chip_index: dict[tuple[str, str], int]
) -> tuple[list[dict], int]:
    patched: list[dict] = []
    n = 0
    for r in races:
        cat = r.get("category")
        d = r.get("date")
        if not isinstance(cat, str) or not isinstance(d, str):
            patched.append(dict(r))
            continue
        chip = chip_index.get((d[:10], cat))
        if chip is None:
            patched.append(dict(r))
            continue
        old = r.get("duration_s")
        if isinstance(old, int) and old == chip:
            patched.append(dict(r))
            continue
        nr = dict(r)
        nr["duration_s"] = chip
        nr["time"] = fmt_duration(chip)
        patched.append(nr)
        n += 1
    return patched, n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", type=Path, required=True, help="Base SurveyInputs JSON (e.g. pull-intake output).")
    p.add_argument("--report", type=Path, required=True, help="report_<id>.json from marathon-report.")
    p.add_argument(
        "--training",
        type=Path,
        required=True,
        help="training_<id>.jsonl used for w_now (post-marathon weeks).",
    )
    p.add_argument(
        "--activities",
        type=Path,
        default=None,
        help="Optional Strava activities JSONL (with sport_type) to classify cross-training "
        "during the lead-up for the freshness model.",
    )
    p.add_argument(
        "--nyrr-search",
        default="",
        help="If set, resolve NYRR chip times by runner name search (e.g. 'Kelly Hession').",
    )
    p.add_argument(
        "--today",
        default="",
        help="Override 'today' for post-marathon window (YYYY-MM-DD, default: system date).",
    )
    p.add_argument("-o", "--out", type=Path, required=True, help="Write merged SurveyInputs JSON.")
    args = p.parse_args()

    try:
        base = SurveyInputs.model_validate_json(args.base.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid base survey: {exc}", file=sys.stderr)
        return 1

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid report JSON: {exc}", file=sys.stderr)
        return 1

    weeks = _load_weeks(args.training)
    today = date.fromisoformat(args.today) if args.today else date.today()

    latest_m = report.get("latest_marathon")
    if not isinstance(latest_m, dict) or not latest_m.get("date"):
        print("Report has no latest_marathon date; cannot derive block metrics.", file=sys.stderr)
        return 1
    m_date = date.fromisoformat(str(latest_m["date"])[:10])

    tb = report.get("training_block") or {}
    weekly = tb.get("weekly_run_miles") or {}
    peak_mi = 0.0
    if isinstance(weekly, dict) and weekly:
        peak_mi = max(float(v) for v in weekly.values() if isinstance(v, (int, float)))

    longest = tb.get("longest_run") or {}
    lr_mi = longest.get("miles")
    longest_mi = float(lr_mi) if isinstance(lr_mi, (int, float)) else base.longest_run_mi

    post = report.get("post_marathon") or {}
    races = list(post.get("races") or [])

    chip_index: dict[tuple[str, str], int] = {}
    if args.nyrr_search.strip():
        try:
            rid, chip_rows = list_chip_races_for_search(args.nyrr_search.strip())
        except (LookupError, OSError, RuntimeError) as exc:
            print(f"NYRR lookup failed: {exc}", file=sys.stderr)
            return 1
        for r in chip_rows:
            if r.category:
                chip_index[(r.start_date, r.category)] = r.duration_s
        races, n_chip = _apply_nyrr_to_races(races, chip_index)
        print(f"[nyrr] applied {n_chip} chip time override(s) on post-marathon races", file=sys.stderr)
        print(
            json.dumps(
                {
                    "nyrr_runner_id_used": rid,
                    "nyrr_search": args.nyrr_search.strip(),
                    "chip_index_keys": [list(k) for k in chip_index],
                },
                indent=2,
            ),
            file=sys.stderr,
        )

    vd = recommended_vdot(races)
    if not vd:
        print("Could not compute recommended_vdot from (patched) post-marathon races.", file=sys.stderr)
        return 1

    w_now = _w_now_post_marathon(weeks, m_date, today)
    src = vd["source_race"]

    # Fitness-clock context: longest running break + cross-training since the last marathon.
    break_days = _longest_break_days(weeks, m_date + timedelta(days=1), today)
    crossed, cross_note = False, None
    if args.activities is not None:
        try:
            acts = _load_weeks(args.activities)
        except SystemExit:
            raise
        crossed, cross_note = _cross_training_during_break(acts, m_date + timedelta(days=1), today)

    half_name: str | None = None
    half_secs: int | None = None
    for r in races:
        if r.get("category") != "Half Marathon":
            continue
        ds = r.get("duration_s")
        if not isinstance(ds, int):
            continue
        if half_secs is None or ds < half_secs:
            half_secs = ds
            half_name = str(r.get("name") or "") or None

    mar_name = str(latest_m.get("name") or "") or None
    mar_raw = latest_m.get("duration_s")
    mar_secs = int(mar_raw) if isinstance(mar_raw, int) else None
    chip_m = chip_index.get((m_date.isoformat(), "Marathon"))
    if chip_m is not None:
        mar_secs = chip_m

    merged = base.model_copy(
        update={
            "vdot": float(vd["vdot"]),
            "w_now": w_now,
            "p_history": round(peak_mi, 1),
            "longest_run_mi": round(longest_mi, 1),
            "latest_half_race_text": half_name,
            "latest_half_time_s": half_secs,
            "latest_marathon_race_text": mar_name,
            "latest_marathon_time_s": mar_secs,
            "recent_break_days": break_days,
            "cross_trained_during_break": crossed,
            "cross_training_note": cross_note,
        }
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(merged.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    print(
        f"vdot={merged.vdot} w_now={merged.w_now} p_history={merged.p_history} "
        f"longest_run_mi={merged.longest_run_mi} recent_break_days={merged.recent_break_days} "
        f"cross_trained_during_break={merged.cross_trained_during_break} "
        f"(VDOT from {src.get('category')} {src.get('time')})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
