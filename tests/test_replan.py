"""Replan folds approved/applied events into baseline before ``build_plan``."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from engine.plan import build_plan, common
from engine.plan.models import AthleteInputs
from engine.plan.replan import fold_events_to_inputs, replan
from store.db import Store
from store.events import (
    CoachNotePayload,
    EffortQualityPayload,
    FitnessAnchorPayload,
    RaceEstimatePayload,
    SetDaysPayload,
    SetGoalPayload,
    TuneUpResultPayload,
    WeeklyEvaluationPayload,
)


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


def _new_athlete(db: Store, aid: str) -> None:
    db._conn.execute(  # noqa: SLF001
        "INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json) VALUES (?,?,?,?,?)",
        (aid, None, aid, "2026-01-01", "{}"),
    )
    db._conn.commit()  # noqa: SLF001


def test_replan_race_estimate_sets_effective_vdot(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_re.db", project_root=tmp_path)
    aid = "a-re"
    _new_athlete(db, aid)
    db.append_event(
        "e1", aid, "2026-01-01T00:00:00+00:00", "coach", "applied", "RaceEstimate",
        RaceEstimatePayload(
            race_name="Melbourne", race_date="2025-10-11",
            distance_m=42195.0, actual_time_s=14425, estimated_time_s=14100,
            estimated_vdot=38.9, effective_vdot=36.2, break_days=28,
            note="sick race",
        ).model_dump(mode="json"),
    )
    plan = replan(_base_inputs(vdot=33.8), db, aid)
    assert plan.vdot == 36.2  # detrained effective VDOT, not the raw baseline
    assert any("coach_note: race-estimate Melbourne" in f for f in plan.flags)


def test_replan_fitness_anchor_sets_vdot(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_fa.db", project_root=tmp_path)
    aid = "a-fa"
    _new_athlete(db, aid)
    db.append_event(
        "e1", aid, "2026-01-01T00:00:00+00:00", "coach", "applied", "FitnessAnchor",
        FitnessAnchorPayload(race_date="2025-10-11", vdot=36.2, source="Marathon (estimate)").model_dump(mode="json"),
    )
    plan = replan(_base_inputs(vdot=33.8), db, aid)
    assert plan.vdot == 36.2
    assert any("fitness-anchor" in f for f in plan.flags)


def test_replan_effort_quality_is_flag_only(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_eq.db", project_root=tmp_path)
    aid = "a-eq"
    _new_athlete(db, aid)
    db.append_event(
        "e1", aid, "2026-01-01T00:00:00+00:00", "coach", "applied", "EffortQuality",
        EffortQualityPayload(race_date="2026-04-26", quality="submaximal").model_dump(mode="json"),
    )
    base = _base_inputs()
    plan = replan(base, db, aid)
    assert plan.vdot == base.vdot
    assert any("effort=submaximal" in f for f in plan.flags)


def test_replan_coach_note_is_flag_only(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_cn.db", project_root=tmp_path)
    aid = "a-cn"
    _new_athlete(db, aid)
    db.append_event(
        "e1", aid, "2026-01-01T00:00:00+00:00", "coach", "applied", "CoachNote",
        CoachNotePayload(text="watch left achilles").model_dump(mode="json"),
    )
    base = _base_inputs()
    plan = replan(base, db, aid)
    assert plan.vdot == base.vdot  # provenance only — no numeric change
    assert any("coach_note: watch left achilles" in f for f in plan.flags)


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


def test_replan_skips_rejected(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_rej.db", project_root=tmp_path)
    aid = "a-rej"
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
        "rejected",
        "SetGoal",
        SetGoalPayload(goal_marathon_s=9999).model_dump(mode="json"),
    )
    base = _base_inputs()
    plan = replan(base, db, aid)
    assert plan.goal["goal_time_s"] == base.goal_marathon_s


def test_fold_events_to_inputs_matches_replan_numeric_inputs(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_fold.db", project_root=tmp_path)
    aid = "a-fold"
    _new_athlete(db, aid)
    db.append_event(
        "e1", aid, "2026-01-01T00:00:00+00:00", "coach", "applied", "RaceEstimate",
        RaceEstimatePayload(
            race_name="Melbourne", race_date="2025-10-11",
            distance_m=42195.0, actual_time_s=14425, estimated_time_s=14100,
            estimated_vdot=38.9, effective_vdot=36.2, break_days=28,
            note="sick race",
        ).model_dump(mode="json"),
    )
    base = _base_inputs(vdot=33.8)
    folded, _ = fold_events_to_inputs(base, db, aid)
    plan = replan(base, db, aid)
    assert folded.vdot == plan.vdot == 36.2


def test_replan_weekly_evaluation_updates_inputs(tmp_path: Path):
    db = Store(db_path=tmp_path / "t_we.db", project_root=tmp_path)
    aid = "a-we"
    _new_athlete(db, aid)
    db.append_event(
        "e1",
        aid,
        "2026-02-01T00:00:00+00:00",
        "coach",
        "applied",
        "WeeklyEvaluation",
        WeeklyEvaluationPayload(
            week_start="2026-01-27",
            calibrated_vdot=37.0,
            estimated_mpw=22.5,
            easy_pace_override_s=600,
            note="post-check-in",
        ).model_dump(mode="json"),
    )
    base = _base_inputs(vdot=40.0, w_now=18.0)
    folded, flags = fold_events_to_inputs(base, db, aid)
    assert folded.vdot == 37.0
    assert folded.w_now == 22.5
    assert folded.reentry_start_mpw == 22.5
    assert folded.easy_pace_override_s == 600
    assert any("weekly-evaluation" in f for f in flags)
    plan = build_plan(replace(folded, method=common.DANIELS, days_per_week=5, p_history=55.0))
    assert plan.paces["easy_low_s"] == 592
    assert plan.paces["easy_high_s"] == 608


def test_replan_injury_emits_return_guidance(tmp_path: Path):
    from store.events import InjuryPayload

    db = Store(db_path=tmp_path / "t_inj.db", project_root=tmp_path)
    aid = "a-inj"
    _new_athlete(db, aid)
    db.append_event(
        "e1",
        aid,
        "2026-01-01T00:00:00+00:00",
        "coach",
        "applied",
        "Injury",
        InjuryPayload(area="achilles", severity=2, days_off=5).model_dump(mode="json"),
    )
    plan = replan(_base_inputs(), db, aid)
    assert any("Hanson p.145" in f for f in plan.flags)
