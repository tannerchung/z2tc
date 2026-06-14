import pytest

from engine.monitor import adherence_payload, monitor_week
from engine.plan.models import PlannedDay, PlannedWeek, Workout, WorkoutKind


def test_adherence_low_volume_triggers():
    p = adherence_payload("2026-01-05", prescribed_mi=40.0, actual_mi=30.0)
    assert p is not None
    assert p.ratio == pytest.approx(0.75, rel=1e-3)
    assert adherence_payload("2026-01-05", 40.0, 38.0) is None


def test_monitor_week_missed_quality():
    wk = PlannedWeek(
        index=1,
        phase="Threshold",
        label="T",
        target_miles=35.0,
        is_down_week=False,
        days=[
            PlannedDay(
                "Wed",
                Workout(WorkoutKind.THRESHOLD, "Tempo", distance_mi=6.0),
            )
        ],
    )
    ev = monitor_week(
        wk,
        week_start="2026-01-05",
        actual_week_run_miles=35.0,
        actual_by_day={"Wed": 0.0},
    )
    kinds = [type(x).__name__ for x in ev]
    assert "MissedQualityPayload" in kinds
