"""Replan folds approved/applied events into baseline before ``build_plan``."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.plan import common
from engine.plan.models import AthleteInputs
from engine.plan.replan import replan
from store.db import Store
from store.events import SetDaysPayload, SetGoalPayload, TuneUpResultPayload


def _base_inputs(**kw):
    d = dict(
        name="X",
        vdot=43.0,
        goal_marathon_s=3 * 3600 + 55 * 60,
        w_now=28.0,
        p_history=31.0,
        longest_run_mi=13.0,
        days_per_week=4,
        race_date="2026-10-10",
    )
    d.update(kw)
    return AthleteInputs(**d)


def test_replan_set_days_changes_method_assignment(tmp_path: Path):
    db = Store(db_path=tmp_path / "t.db", project_root=tmp_path)
    aid = "athlete-1"
    db._conn.execute(  # noqa: SLF001
        "INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json) VALUES (?,?,?,?,?)",
        (aid, None, "X", "2026-01-01", "{}"),
    )
    db._conn.commit()  # noqa: SLF001
    p = SetDaysPayload(n=5)
    db.append_event("e1", aid, "2026-01-02T00:00:00+00:00", "coach", "applied", "SetDays", p.model_dump(mode="json"))
    base = _base_inputs(p_history=50.0)
    plan = replan(base, db, aid)
    assert common.assign_method(base) == common.DANIELS
    assert plan.method == common.PFITZINGER


def test_replan_tuneup_updates_vdot(tmp_path: Path):
    db = Store(db_path=tmp_path / "t2.db", project_root=tmp_path)
    aid = "a2"
    db._conn.execute(  # noqa: SLF001
        "INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json) VALUES (?,?,?,?,?)",
        (aid, None, "Y", "2026-01-01", "{}"),
    )
    db._conn.commit()  # noqa: SLF001
    db.append_event(
        "e1",
        aid,
        "2026-01-01T00:00:00+00:00",
        "strava",
        "applied",
        "TuneUpResult",
        TuneUpResultPayload(distance_m=5000, time_s=1200, new_vdot=48.0).model_dump(mode="json"),
    )
    base = _base_inputs()
    plan = replan(base, db, aid)
    assert plan.vdot == 48.0


def test_replan_skips_proposed(tmp_path: Path):
    db = Store(db_path=tmp_path / "t3.db", project_root=tmp_path)
    aid = "a3"
    db._conn.execute(  # noqa: SLF001
        "INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json) VALUES (?,?,?,?,?)",
        (aid, None, "Z", "2026-01-01", "{}"),
    )
    db._conn.commit()  # noqa: SLF001
    db.append_event(
        "e1",
        aid,
        "2026-01-01T00:00:00+00:00",
        "llm",
        "proposed",
        "SetGoal",
        SetGoalPayload(goal_marathon_s=9999).model_dump(mode="json"),
    )
    base = _base_inputs()
    plan = replan(base, db, aid)
    assert plan.goal["goal_time_s"] == base.goal_marathon_s
