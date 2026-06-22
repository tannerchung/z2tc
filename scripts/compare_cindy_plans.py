#!/usr/bin/env python3
"""Compare an athlete's raw survey baseline vs event-folded inputs across all four engines.

Loads ``survey_baselines`` + ``events`` (via ``fold_events_to_inputs`` in ``engine/plan/replan.py``),
prints VDOT / easy pace / week-1 and peak weekly miles for each forced ``method``.

Usage::

    PYTHONPATH=. python scripts/compare_cindy_plans.py
    PYTHONPATH=. python scripts/compare_cindy_plans.py --athlete-id kelly-hession
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.plan import build_plan, common
from engine.plan.replan import fold_events_to_inputs, replan
from store.db import Store, default_db_path


def _peak_week_mi(plan) -> float:
    if not plan.weeks:
        return 0.0
    return max(w.target_miles for w in plan.weeks)


def _week1_mi(plan) -> float:
    if not plan.weeks:
        return 0.0
    return plan.weeks[0].target_miles


def _print_block(title: str, base) -> None:
    print(f"\n=== {title} (vdot={base.vdot} w_now={base.w_now} reentry={base.reentry_start_mpw}) ===")
    print(f"{'method':12} {'vdot':>6} {'easy':>12} {'wk1_mi':>8} {'peak_mi':>8}")
    rows = [
        (common.DANIELS, None, None),
        (common.PFITZINGER, None, None),
        (common.HIGDON, "intermediate1", None),
        (common.HANSON, None, "beginner"),
    ]
    for method, higdon, hanson in rows:
        inp = replace(
            base,
            method=method,
            higdon_program=higdon,
            hanson_program=hanson,
            emit_peak_scenarios=False,
            append_post_marathon_recovery=False,
        )
        plan = build_plan(inp)
        easy = str(plan.paces.get("easy", ""))
        print(f"{method:12} {plan.vdot:6.1f} {easy:>12} {_week1_mi(plan):8.1f} {_peak_week_mi(plan):8.1f}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--athlete-id", default="cindy-kim", help="SQLite athlete id (default: cindy-kim)")
    p.add_argument("--db", type=Path, default=None, help="Path to z2tc.db (default: output/z2tc.db)")
    args = p.parse_args()

    db_path = args.db or default_db_path(PROJECT_ROOT)
    store = Store(db_path=db_path, project_root=PROJECT_ROOT)
    survey = store.load_survey_baseline(args.athlete_id)
    if survey is None:
        print(f"No survey_baselines row for {args.athlete_id!r} in {db_path}", file=sys.stderr)
        return 1
    if store.get_athlete(args.athlete_id) is None:
        print(f"No athletes row for {args.athlete_id!r}", file=sys.stderr)
        return 1

    raw_base = survey.to_athlete_inputs()
    folded, _flags = fold_events_to_inputs(raw_base, store, args.athlete_id)

    _print_block("RAW (survey baseline only)", raw_base)
    _print_block("CALIBRATED (inputs after event fold)", folded)

    auto = replan(raw_base, store, args.athlete_id)
    print(
        f"\nAuto-assign replan: method={auto.method} vdot={auto.vdot} "
        f"wk1={_week1_mi(auto):.1f} peak={_peak_week_mi(auto):.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
