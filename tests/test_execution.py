"""Tests for the pure execution summary (engine/execution.py)."""

from __future__ import annotations

from datetime import date

from engine.execution import (
    ExecutionSummary,
    execution_from_actuals,
    summarize_execution,
    week_start_for_index,
)
from engine.plan.models import PlannedWeek, TrainingPlan
from store.events import AdherenceFlagPayload, MissedQualityPayload, WeeklyEvaluationPayload


def _plan() -> TrainingPlan:
    return TrainingPlan(
        athlete="t", method="daniels", vdot=40.0, peak_miles=30.0, block_weeks=4,
        goal={"date": "2026-02-01"}, weeks=[], paces={},
    )


def _plan_with_weeks() -> TrainingPlan:
    # Race 2026-02-01, 4-week block → week Mondays: 01-04, 01-11, 01-18, 01-25.
    weeks = [
        PlannedWeek(index=1, phase="Base", label="W1", target_miles=20.0),
        PlannedWeek(index=2, phase="Base", label="W2", target_miles=25.0),
        PlannedWeek(index=3, phase="Build", label="W3", target_miles=30.0),
        PlannedWeek(index=4, phase="Build", label="W4", target_miles=32.0),
    ]
    return TrainingPlan(
        athlete="t", method="daniels", vdot=40.0, peak_miles=32.0, block_weeks=4,
        goal={"date": "2026-02-01"}, weeks=weeks, paces={},
    )


def test_week_start_for_index_matches_monday_grid():
    p = _plan()
    # Race 2026-02-01; block 4 wk → week 1 Monday = race - 4 wk; consecutive weeks step 7 days.
    w1 = week_start_for_index(p, 1)
    w2 = week_start_for_index(p, 2)
    assert w1 == "2026-01-04" and w2 == "2026-01-11"
    assert week_start_for_index(TrainingPlan(athlete="t", method="d", vdot=40, peak_miles=30, block_weeks=4, goal={}, weeks=[], paces={}), 1) is None


def test_summarize_folds_flags_quality_and_notes():
    payloads = [
        AdherenceFlagPayload(week_start="2026-01-04", prescribed_mi=20.0, actual_mi=14.0, ratio=0.70),
        AdherenceFlagPayload(week_start="2026-01-11", prescribed_mi=22.0, actual_mi=21.0, ratio=0.95),
        MissedQualityPayload(week_index=1, day="Tue", expected_label="Threshold"),
        MissedQualityPayload(week_index=1, day="Thu", expected_label="Intervals"),
        WeeklyEvaluationPayload(week_start="2026-01-04", note="travel week"),
    ]
    s = summarize_execution(payloads)
    assert s.has_signal
    assert s.weeks_flagged_short == 1            # only ratio 0.70 < 0.92
    assert s.worst_ratio == 0.70
    assert s.recent_short_week == "2026-01-04"
    assert s.missed_quality_count == 2
    assert s.coach_notes == [("2026-01-04", "travel week")]

    wk1 = s.for_week(week_start="2026-01-04", week_index=1)
    assert wk1 is not None
    assert wk1.short and wk1.ratio == 0.70
    assert wk1.missed_quality_days == ["Tue", "Thu"]
    assert wk1.coach_note == "travel week"


def test_for_week_none_when_no_signal():
    s = summarize_execution([])
    assert not s.has_signal
    assert s.for_week(week_start="2026-01-04", week_index=2) is None


def test_on_plan_week_not_flagged_but_present():
    # A >=0.92 ratio is recorded (so a coach note could attach) but doesn't count as short.
    s = summarize_execution([AdherenceFlagPayload(week_start="2026-01-11", prescribed_mi=22.0, actual_mi=21.0, ratio=0.95)])
    assert s.weeks_flagged_short == 0 and s.worst_ratio is None
    wk = s.for_week(week_start="2026-01-11")
    assert wk is not None and not wk.short


def test_execution_from_actuals_scores_elapsed_weeks_both_ways():
    plan = _plan_with_weeks()
    actuals = {
        "2026-01-04": 20.0,   # on plan (1.0)
        "2026-01-11": 15.0,   # short (0.6)
        "2026-01-18": 29.0,   # on plan (0.967)
        "2026-01-25": 32.0,   # future week — must be ignored
    }
    s = execution_from_actuals(plan, actuals, today=date(2026, 1, 20))
    assert s.scored_full_block
    assert s.weeks_logged == 3          # the future week is excluded
    assert s.weeks_on_track == 2
    assert s.weeks_flagged_short == 1
    assert s.by_week_index[1].on_track and s.by_week_index[1].verdict == "on_track"
    assert s.by_week_index[2].short and s.by_week_index[2].verdict == "short"
    assert s.worst_ratio == 0.6
    assert s.recent_short_week == "2026-01-11"
    assert s.mean_adherence == round((1.0 + 0.6 + 29.0 / 30.0) / 3, 3)
    assert 4 not in s.by_week_index    # future week never scored


def test_execution_from_actuals_ignores_no_data_weeks():
    plan = _plan_with_weeks()
    s = execution_from_actuals(plan, {"2026-01-04": 20.0}, today=date(2026, 1, 20))
    # Weeks 2 & 3 have elapsed but have no actuals entry → never marked short (honest, not 0%).
    assert s.weeks_logged == 1 and s.weeks_on_track == 1 and s.weeks_flagged_short == 0
    assert 2 not in s.by_week_index and 3 not in s.by_week_index


def test_execution_from_actuals_folds_qualitative_payloads():
    plan = _plan_with_weeks()
    s = execution_from_actuals(
        plan, {"2026-01-04": 20.0}, today=date(2026, 1, 20),
        payloads=[
            MissedQualityPayload(week_index=1, day="Tue", expected_label="Threshold"),
            WeeklyEvaluationPayload(week_start="2026-01-04", note="felt strong"),
        ],
    )
    wk = s.for_week(week_start="2026-01-04", week_index=1)
    assert wk is not None and wk.on_track
    assert wk.missed_quality_days == ["Tue"] and wk.coach_note == "felt strong"
