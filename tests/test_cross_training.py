"""Standing weekly cross-training overlay (Pfitzinger ch.4).

A coach can seat a non-running aerobic session on chosen weekdays; it fills rest days only, never
displaces a run, skips race/tune-up weeks, and leaves running mileage untouched (CROSS = 0 mi).
"""

from __future__ import annotations

from engine.plan import build_club_plan
from engine.plan.models import AthleteInputs, WorkoutKind


def _inputs(**over) -> AthleteInputs:
    base = dict(
        name="Tamara", vdot=44.0, goal_marathon_s=4 * 3600, w_now=25.0, p_history=33.0,
        longest_run_mi=18.0, days_per_week=3, race_date="2026-11-01", block_weeks=16,
        race_name="Test Marathon",
    )
    base.update(over)
    return AthleteInputs(**base)


def test_friday_cross_training_seated_on_rest_days():
    plan = build_club_plan(_inputs(cross_training_days=("Fri",), cross_training_minutes=45))
    race_weeks = {w.index for w in plan.weeks if any(d.workout.kind == WorkoutKind.RACE for d in w.days)}
    seated = 0
    for w in plan.weeks:
        fri = next((d for d in w.days if d.day == "Fri"), None)
        assert fri is not None
        if w.index in race_weeks:
            assert fri.workout.kind != WorkoutKind.CROSS  # race weeks stay clean
        elif fri.workout.kind == WorkoutKind.CROSS:
            seated += 1
            assert fri.workout.duration_min == 45
            assert fri.workout.distance_mi is None
    assert seated >= 1


def test_cross_training_does_not_change_running_mileage():
    base = _inputs()
    with_xc = _inputs(cross_training_days=("Fri",))
    plan_a = build_club_plan(base)
    plan_b = build_club_plan(with_xc)
    miles_a = [round(w.planned_running_miles, 1) for w in plan_a.weeks]
    miles_b = [round(w.planned_running_miles, 1) for w in plan_b.weeks]
    assert miles_a == miles_b
    assert round(plan_a.peak_miles, 1) == round(plan_b.peak_miles, 1)


def test_no_cross_training_by_default():
    plan = build_club_plan(_inputs())
    assert not any(d.workout.kind == WorkoutKind.CROSS for w in plan.weeks for d in w.days)


def test_cross_training_only_fills_rest_not_runs():
    # Friday is a run day at 5 days/week (Mon/Tue/Wed/Fri/Sat) — the overlay must not overwrite it.
    plan = build_club_plan(_inputs(days_per_week=5, p_history=42.0, cross_training_days=("Fri",)))
    for w in plan.weeks:
        fri = next((d for d in w.days if d.day == "Fri"), None)
        if fri and fri.workout.kind == WorkoutKind.CROSS:
            raise AssertionError("cross-training overwrote a scheduled run day")
