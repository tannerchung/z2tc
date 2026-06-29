#!/usr/bin/env python3
"""Merge marathon-report JSON + optional chip times into a base SurveyInputs JSON.

Use this after ``marathon-report`` (Strava). Chip lookup defaults to NYRR when
``--chip-search`` / ``--nyrr-search`` is set; additional feeds register in
``lib/data_feeds/chip_lookup.py``.

Example::

    python scripts/merge_report_nyrr_survey.py \\
        --base /tmp/kelly_intake.json \\
        --report output/kelly_strava/report_42251408.json \\
        --training output/kelly_strava/training_42251408.jsonl \\
        --chip-search \"Kelly Hession\" \\
        -o /tmp/kelly_survey_merged.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from store.merge_survey import merge_strava_report
from store.models import SurveyInputs


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
        help="Optional Strava activities JSONL (with sport_type) for cross-training classification.",
    )
    p.add_argument(
        "--chip-search",
        "--nyrr-search",
        dest="chip_search",
        default="",
        help="Runner name for chip-time lookup (NYRR + registered external feeds).",
    )
    p.add_argument(
        "--no-nyrr",
        action="store_true",
        help="Skip NYRR even when --chip-search is set (external feeds only).",
    )
    p.add_argument(
        "--returning-marathoner",
        action="store_true",
        help="Force returning-marathoner merge path (block anchor + decay).",
    )
    p.add_argument(
        "--not-returning",
        action="store_true",
        help="Force first-timer path even if Strava shows a marathon.",
    )
    p.add_argument(
        "--today",
        default="",
        help="Override 'today' for post-marathon window (YYYY-MM-DD, default: system date).",
    )
    p.add_argument("-o", "--out", type=Path, required=True, help="Write merged SurveyInputs JSON.")
    args = p.parse_args()

    if args.returning_marathoner and args.not_returning:
        print("Choose at most one of --returning-marathoner / --not-returning.", file=sys.stderr)
        return 1

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
    activities = _load_weeks(args.activities) if args.activities else None

    returning: bool | None = None
    if args.returning_marathoner:
        returning = True
    elif args.not_returning:
        returning = False

    try:
        merged, provenance = merge_strava_report(
            base,
            report,
            weeks,
            today=today,
            chip_search_name=args.chip_search.strip() or None,
            include_nyrr=not args.no_nyrr,
            activities=activities,
            returning_marathoner=returning,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(merged.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    for line in provenance:
        print(f"  {line}", file=sys.stderr)
    print(
        f"returning={merged.returning_marathoner} vdot={merged.vdot} w_now={merged.w_now} "
        f"p_history={merged.p_history} longest_run_mi={merged.longest_run_mi} "
        f"decayed_peak_mpw={merged.decayed_peak_mpw} recent_break_days={merged.recent_break_days}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
