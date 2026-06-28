"""Persisting weekly actuals so positive-reinforcement execution scoring is replayable from the
store (not just a training feed file): store roundtrip + idempotent upsert, the replay into
`execution_from_actuals`, and that `monitor` persists what it reads."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

import main
from engine.execution import execution_from_actuals, week_start_for_index
from engine.plan import build_plan
from store.db import SCHEMA_VERSION, Store, fingerprint_athlete_inputs
from store.models import Athlete, SurveyInputs

REPO = Path(__file__).resolve().parents[1]
TRAINING_SYNTHETIC = REPO / "tests" / "fixtures" / "training_synthetic.jsonl"


def _survey() -> SurveyInputs:
    return SurveyInputs(
        name="Wa", vdot=45.0, goal_marathon_s=3 * 3600 + 30 * 60, w_now=30.0,
        p_history=42.0, longest_run_mi=16.0, days_per_week=5, race_date="2026-11-01",
    )


def _seed(tmp_path: Path) -> tuple[Store, str]:
    db = Store(db_path=tmp_path / "wa.db", project_root=tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="Wa", strava_athlete_id=None))
    db.save_survey_baseline("a1", _survey())
    return db, "a1"


def test_schema_version_and_roundtrip(tmp_path: Path) -> None:
    db, aid = _seed(tmp_path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    n = db.upsert_weekly_actuals(aid, {"2026-06-01": 30.0, "2026-06-08": 28.5})
    assert n == 2
    assert db.load_weekly_actuals(aid) == {"2026-06-01": 30.0, "2026-06-08": 28.5}


def test_upsert_refreshes_week_idempotently(tmp_path: Path) -> None:
    db, aid = _seed(tmp_path)
    db.upsert_weekly_actuals(aid, {"2026-06-01": 30.0})
    db.upsert_weekly_actuals(aid, {"2026-06-01": 35.0, "2026-06-08": 20.0})  # refresh wk1, add wk2
    assert db.load_weekly_actuals(aid) == {"2026-06-01": 35.0, "2026-06-08": 20.0}


def test_load_is_empty_for_unknown_athlete(tmp_path: Path) -> None:
    db, _ = _seed(tmp_path)
    assert db.load_weekly_actuals("ghost") == {}


def test_stored_actuals_replay_into_execution_scoring(tmp_path: Path) -> None:
    db, aid = _seed(tmp_path)
    inputs = _survey().to_athlete_inputs()
    plan = build_plan(inputs)
    db.save_plan_artifact(aid, plan, fingerprint_athlete_inputs(inputs))

    # Persist the first two weeks hit exactly on prescription, then score straight from the store.
    weekly = {}
    for w in plan.weeks[:2]:
        ws = week_start_for_index(plan, w.index)
        if ws:
            weekly[ws] = w.target_miles
    db.upsert_weekly_actuals(aid, weekly)

    stored = db.load_weekly_actuals(aid)
    assert stored == weekly
    ex = execution_from_actuals(plan, stored, today=date(2026, 11, 1))
    assert ex.scored_full_block
    assert ex.weeks_logged == len(weekly)
    assert ex.weeks_on_track == len(weekly)  # hit on prescription → on_track


@pytest.mark.skipif(not TRAINING_SYNTHETIC.exists(), reason="synthetic training fixture missing")
def test_monitor_persists_weekly_actuals(tmp_path: Path) -> None:
    db, aid = _seed(tmp_path)
    inputs = _survey().to_athlete_inputs()
    db.save_plan_artifact(aid, build_plan(inputs), fingerprint_athlete_inputs(inputs))

    rc = main._cmd_monitor(
        Namespace(athlete_id=aid, training=str(TRAINING_SYNTHETIC), db=str(db.path))
    )
    assert rc == 0
    # The monitor read a feed → its weekly totals are now durable in the store.
    assert db.load_weekly_actuals(aid)
