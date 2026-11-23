"""Tests for progressive coaching scope flags and informal fueling/hydration integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.plan import build_club_plan
from engine.plan.models import AthleteInputs
from engine.plan.onboarding_milestones import next_onboarding_prompt
from engine.plan.race_fuel import nutrition_for_long_run
from engine.plan.replan import fold_events_to_inputs
from store.db import Store
from store.events import (
    EnvironmentalContextPayload,
    FuelingLogPayload,
     parse_event_payload,
)


def _base_athlete(**kw: Any) -> AthleteInputs:
    d: dict[str, Any] = dict(
        name="Alex",
        vdot=45.0,
        goal_marathon_s=3 * 3600 + 45 * 60,
        w_now=30.0,
        p_history=38.0,
        longest_run_mi=13.0,
        days_per_week=4,
        race_date="2026-11-01",
    )
    d.update(kw)
    return AthleteInputs(**d)


def test_athlete_inputs_progressive_scope_defaults_off():
    a = _base_athlete()
    assert a.enable_fueling_guidance is False
    assert a.enable_hydration_weather is False
    assert a.enable_biomechanics_forensics is False
    assert a.enable_readiness_gates is False
    assert a.sweat_sodium_tier is None
    assert a.last_gi_distress_score is None
    assert a.workout_limiter_focus is None


def test_replan_folds_coaching_scope_and_fueling_gi_feedback(tmp_path: Path):
    db = Store(db_path=tmp_path / "scope.db", project_root=tmp_path)
    aid = "athlete-scope"
    db._conn.execute(
        "INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json) VALUES (?,?,?,?,?)",
        (aid, None, "Alex", "2026-01-01", "{}"),
    )
    db._conn.commit()

    scope_ev = parse_event_payload({
        "kind": "SetCoachingScope",
        "enable_fueling_guidance": True,
        "enable_hydration_weather": True,
        "sweat_sodium_tier": "salty",
        "preferred_gel": "Maurten Gel 100",
        "workout_limiter_focus": "form_stiffness",
    })
    db.append_event("e1", aid, "2026-07-01T10:00:00+00:00", "coach", "applied", "SetCoachingScope", scope_ev.model_dump(mode="json"))

    fuel_ev = FuelingLogPayload(
        run_date="2026-07-04",
        gels_count=4,
        carbs_g_per_hr=65.0,
        gi_distress_1_to_5=4,
        note="Stomach sloshed at mile 13, skipped water station",
    )
    db.append_event("e2", aid, "2026-07-04T14:00:00+00:00", "strava", "applied", "FuelingLog", fuel_ev.model_dump(mode="json"))

    env_ev = EnvironmentalContextPayload(
        run_date="2026-07-11",
        temp_f=76.0,
        dew_point_f=68.0,
    )
    db.append_event("e3", aid, "2026-07-10T18:00:00+00:00", "coach", "applied", "EnvironmentalContext", env_ev.model_dump(mode="json"))

    folded, flags = fold_events_to_inputs(_base_athlete(), db, aid)
    assert folded.enable_fueling_guidance is True
    assert folded.enable_hydration_weather is True
    assert folded.sweat_sodium_tier == "salty"
    assert folded.preferred_gel == "Maurten Gel 100"
    assert folded.workout_limiter_focus == "form_stiffness"
    assert folded.last_gi_distress_score == 4
    assert folded.ambient_temp_f == 76.0
    assert folded.ambient_dew_point_f == 68.0
    assert any("coaching_scope:" in f for f in flags)


def test_race_fuel_scales_hydration_and_gi_stepdown():
    base = _base_athlete(preferred_gel="Maurten Gel 100")
    normal = nutrition_for_long_run(135.0, base)
    assert normal is not None
    assert normal.carbs_g_per_hr == (60, 80)
    assert normal.fluid_ml_per_hr == (450, 800)

    # Salty sweater + warm/humid day + prior GI distress >= 3
    stressed = _base_athlete(
        preferred_gel="Maurten Gel 100",
        enable_hydration_weather=True,
        sweat_sodium_tier="salty",
        ambient_temp_f=78.0,
        ambient_dew_point_f=68.0,
        last_gi_distress_score=4,
    )
    adj = nutrition_for_long_run(135.0, stressed)
    assert adj is not None
    # GI distress >= 3 steps down the carb range by 10g/hr and adds water pairing cue
    assert adj.carbs_g_per_hr[0] < normal.carbs_g_per_hr[0]
    assert adj.fluid_ml_per_hr[1] > normal.fluid_ml_per_hr[1]
    assert adj.sodium_mg_per_hr[0] >= 800
    assert "plain water" in adj.notes.lower()


def test_club_plan_only_attaches_fueling_tips_when_scope_flag_enabled():
    # Default athlete: zero fueling_tip flags on weeks
    plan_default = build_club_plan(_base_athlete())
    assert not any(
        any(f.startswith("fueling_tip:") for f in w.flags)
        for w in plan_default.weeks
    )

    # Enabled athlete: long runs >= 90 min receive an informal 1-line fueling_tip flag
    plan_enabled = build_club_plan(_base_athlete(enable_fueling_guidance=True, preferred_gel="Maurten Gel 100"))
    assert any(
        any(f.startswith("fueling_tip:") for f in w.flags)
        for w in plan_enabled.weeks
    )


def test_progressive_onboarding_milestones_never_bombard_week_1():
    athlete = _base_athlete(longest_run_mi=10.0, w_now=22.0, p_history=28.0)
    plan = build_club_plan(athlete)

    # Week 1 with a short long run (<13 mi): no secondary prompts at all; let them just run!
    p_wk1 = next_onboarding_prompt(plan, athlete, week_index=1)
    assert p_wk1 is None

    # First week where long run reaches >= 12.0 mi (after week 1) and fueling is still False:
    long_wk = next(w.index for w in plan.weeks if w.index > 1 and w.long_run and w.long_run.miles >= 12.0)
    p_fuel = next_onboarding_prompt(plan, athlete, week_index=long_wk)
    assert p_fuel is not None
    assert p_fuel.module_key == "enable_fueling_guidance"
    assert "gel" in p_fuel.informal_question.lower()

    # Once fueling is enabled, entering Peak / Race Prep (wtg <= 8) triggers the informal salty-sweater check:
    athlete_fueled = _base_athlete(enable_fueling_guidance=True, preferred_gel="Maurten 100")
    peak_wk = max(1, plan.block_weeks - 6)
    p_hyd = next_onboarding_prompt(plan, athlete_fueled, week_index=peak_wk)
    assert p_hyd is not None
    assert p_hyd.module_key == "enable_hydration_weather"
    assert "salt" in p_hyd.informal_question.lower()
