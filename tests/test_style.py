"""Style harvest → StyleSpec (fixture only, no live Sheets)."""

from engine.plan.models import (
    DAY_NAMES,
    PlannedDay,
    PlannedWeek,
    TrainingPlan,
    Workout,
    WorkoutKind,
)
from render.sheets import plan_to_values
from render.style import derive_style_spec


def test_derive_style_spec_from_fixture_dump() -> None:
    dump = {
        "spreadsheet_id": "fixture",
        "tabs": [
            {
                "title": "Demo",
                "sample_cells": [
                    {
                        "a1": "A1",
                        "userEnteredFormat": {
                            "textFormat": {"fontSize": 14, "fontFamily": "Roboto"}
                        },
                    }
                ],
            }
        ],
    }
    spec = derive_style_spec(dump)
    assert spec.title_font_size == 14
    assert spec.title_font_family == "Roboto"


def test_plan_to_values_has_week_header_and_days() -> None:
    days = [
        PlannedDay(
            day=dn,
            workout=(
                Workout(kind=WorkoutKind.EASY, label="easy", distance_mi=5.0)
                if dn == "Mon"
                else Workout(kind=WorkoutKind.REST, label="rest")
            ),
        )
        for dn in DAY_NAMES
    ]
    week = PlannedWeek(
        index=1,
        phase="base",
        label="wk1",
        target_miles=40.0,
        days=days,
    )
    plan = TrainingPlan(
        athlete="Test",
        method="daniels",
        goal={"name": "Marathon", "date": "2025-11-02", "goal_time_s": 14400},
        vdot=50.0,
        paces={},
        peak_miles=45.0,
        block_weeks=18,
        weeks=[week],
    )
    grid = plan_to_values(plan)
    assert any(r and r[0] == "week" for r in grid)
    header = next(r for r in grid if r and r[0] == "week")
    assert list(header[:5]) == ["week", "phase", "label", "target_mi", "planned_mi"]
    assert header[5:12] == list(DAY_NAMES)
