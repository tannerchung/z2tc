#!/usr/bin/env python3
"""Backfill the SQLite store with per-athlete coach overrides on top of imported baselines.

Context: the numeric baseline (``vdot`` / ``w_now`` / ``p_history`` / longest) is owned by the
intake + Strava merge pipeline (``scripts/import_all_athletes.py``), which writes a season +
survey baseline per athlete. The *coach overrides* that shape a draft — midweek quality count,
long-run cap, aggressive ramp, etc. — have no Form question, so they used to be applied inline
and lost on rebuild. This script makes them durable by patching the active season's baseline
with an editable per-athlete override map, then rebuilding the plan artifact (with a resolved-
inputs snapshot) so a future ``replan`` reproduces the draft faithfully.

Run order::

    python scripts/import_all_athletes.py            # (re)derive baselines into the store
    python scripts/backfill_db.py                    # layer coach overrides + rebuild
    python scripts/backfill_db.py --only cindy-kim   # one athlete
    python scripts/backfill_db.py --dry-run          # print the patch without writing

The override values below are recovered from the draft history. **Confirm with the coach**
before trusting them; entries marked CONFIRM are best-effort and likely incomplete.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from engine.plan import build_plan  # noqa: E402
from store.db import Store, default_db_path, fingerprint_athlete_inputs  # noqa: E402


@dataclass(frozen=True)
class SeasonSeed:
    """Coach overrides + optional VDOT anchor to layer onto an athlete's active-season baseline.

    ``overrides`` keys must be ``SurveyInputs`` fields (they map 1:1 to ``AthleteInputs``).
    ``vdot_anchor`` writes a FitnessAnchor event when the calibrated fitness differs from the
    merged survey VDOT (e.g. a draft that was hand-tuned to a higher VDOT).
    """

    athlete_id: str
    overrides: dict = field(default_factory=dict)
    vdot_anchor: float | None = None
    confirmed: bool = False


# Recovered from the draft history. Cindy's knobs are well-attested; Gaurav's are partial.
SEEDS: list[SeasonSeed] = [
    SeasonSeed(
        athlete_id="cindy-kim",
        overrides={
            "weekday_quality_sessions": 2,
            "aggressive_volume_ramp": True,
            "long_run_cap_mi": 18.0,
            "strides_per_phase": 2,
            "quality_long_runs_race_prep_only": True,
        },
        confirmed=False,  # CONFIRM with coach
    ),
    SeasonSeed(
        athlete_id="gaurav-goel",
        overrides={
            "weekday_quality_sessions": 2,
        },
        confirmed=False,  # CONFIRM with coach — only the midweek-quality count is attested
    ),
]


def apply_seed(store: Store, seed: SeasonSeed, *, dry: bool) -> str:
    season = store.get_active_season(seed.athlete_id)
    if season is None:
        return "no_active_season (run import_all_athletes first)"
    survey = store.load_survey_baseline(seed.athlete_id, season_id=season.id)
    if survey is None:
        return "no_baseline"

    unknown = [k for k in seed.overrides if k not in survey.model_fields]
    if unknown:
        return f"unknown_fields:{unknown}"

    print(f"\n=== {seed.athlete_id} (season {season.id}: {season.label}) ===")
    for k, v in seed.overrides.items():
        print(f"  set {k} = {v!r} (was {getattr(survey, k)!r})")
    if seed.vdot_anchor is not None:
        print(f"  FitnessAnchor vdot = {seed.vdot_anchor}")
    if not seed.confirmed:
        print("  ! values not coach-confirmed")
    if dry:
        return "dry_run"

    patched = survey.model_copy(update=dict(seed.overrides))
    store.save_survey_baseline(seed.athlete_id, patched, season_id=season.id)

    if seed.vdot_anchor is not None:
        from store.events import EventRecord, FitnessAnchorPayload

        store.append_event_record(
            EventRecord(
                athlete_id=seed.athlete_id,
                source="coach",
                status="applied",
                payload=FitnessAnchorPayload(
                    vdot=seed.vdot_anchor, source="backfill: draft-calibrated VDOT"
                ),
            ),
            season_id=season.id,
        )

    from engine.plan.replan import replan, resolve_inputs

    baseline = patched.to_athlete_inputs()
    resolved = resolve_inputs(baseline, store, seed.athlete_id, season_id=season.id)
    plan = replan(baseline, store, seed.athlete_id, season_id=season.id)
    fp = fingerprint_athlete_inputs(resolved) + "_backfill"
    store.save_plan_artifact(
        seed.athlete_id, plan, fp, season_id=season.id, resolved_inputs=resolved
    )
    return f"ok (method={plan.method}, vdot={plan.vdot})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="Apply to a single athlete slug.")
    ap.add_argument("--dry-run", action="store_true", help="Print the patch without writing.")
    ap.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    args = ap.parse_args()

    seeds = [s for s in SEEDS if (args.only is None or s.athlete_id == args.only)]
    if not seeds:
        print(f"No seed for --only {args.only!r}", file=sys.stderr)
        return 1

    store = Store(Path(args.db) if args.db else None)
    results: dict[str, str] = {}
    for seed in seeds:
        try:
            results[seed.athlete_id] = apply_seed(store, seed, dry=args.dry_run)
        except Exception as exc:  # keep going; report at the end
            results[seed.athlete_id] = f"error: {exc}"

    print("\n=== backfill summary ===")
    for slug, status in results.items():
        print(f"  {slug:16} {status}")
    failed = [s for s in results.values() if not (s.startswith("ok") or s == "dry_run")]
    return 1 if failed and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
