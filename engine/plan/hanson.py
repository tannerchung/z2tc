"""Hansons Marathon Method — 18-wk marathon block.

Six cumulative-fatigue days: **Wed off**; **Sun long** (≤16 mi, ~25% week for Beginner);
**Tue** Speed/Strength SOS after base weeks; **Thu** tempo @ goal MP. Paces use goal MP
(Table 3.5, p.105) plus VDOT easy range for fillers — Hansons pace by goal time, not VDOT
equivalents.
"""

from __future__ import annotations

from . import citations as cite_mod
from . import common
from .hanson_grids import PROGRAMS
from .models import (
    AthleteInputs,
    DAY_NAMES,
    PlannedDay,
    PlannedWeek,
    TrainingPlan,
    WorkoutKind,
    secondary_marathon_flags,
    training_plan_goal_payload,
)


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def build_hanson_plan(inputs: AthleteInputs, paces: dict) -> TrainingPlan:
    key = (inputs.hanson_program or "beginner").lower().replace(" ", "")
    if key not in PROGRAMS:
        key = "beginner"
    rows = PROGRAMS[key]

    easy_s, easy_str = common.easy_pace(paces)
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = common.goal_flags(mp_s, paces["threshold_s"], paces["marathon_s"])
    plan_flags += secondary_marathon_flags(inputs)
    plan_flags.append(
        f"Hansons program `{key}` — verbatim daily grids from Tables 4.2–4.4; "
        "paces filled from athlete VDOT easy + goal MP."
    )

    weeks: list[PlannedWeek] = []
    peak_run = 0.0
    n = len(rows)
    prev_target = 0.0
    for i, row in enumerate(rows):
        wk = i + 1
        phase = "Taper" if wk > n - 3 else ("Base" if wk <= 5 else "SOS")
        target = sum(cell.miles or 0.0 for cell in row if cell.kind != WorkoutKind.CROSS)
        is_down = wk > 5 and wk < n - 2 and target < prev_target - 0.5
        prev_target = target

        days: list[PlannedDay] = []
        for day, cell in zip(DAY_NAMES, row):
            w = cell.to_workout(paces, mp_s, mp_str, easy_s, easy_str)
            if w.kind == WorkoutKind.RACE:
                if w.distance_mi and abs(w.distance_mi - 26.2) < 0.1:
                    w.label = f"{inputs.race_name} - race day"
            days.append(PlannedDay(day, w))

        run_mi = sum(x.running_miles for x in days)
        peak_run = max(peak_run, run_mi)

        weeks.append(
            PlannedWeek(
                index=wk,
                phase=phase,
                label=f"{phase}{' (down)' if is_down else ''}",
                target_miles=round(target, 1),
                is_down_week=is_down,
                days=days,
                flags=[],
            )
        )

    notes = [
        cite_mod.PACE_BASIS["hanson"],
        str(cite_mod.get("hanson_pace_basis")),
        str(cite_mod.get("hanson_beginner_schedule")),
        "Hansons cumulative-fatigue model (ch.4): Wed off; Tue/Thu SOS; Sun long ≤16 mi (p.62).",
        str(cite_mod.get("hanson_16_cap")),
        str(cite_mod.get("hanson_long_run_window")),
    ]

    plan = TrainingPlan(
        athlete=inputs.name,
        method=common.HANSON,
        goal=training_plan_goal_payload(inputs),
        vdot=inputs.vdot,
        paces=paces,
        peak_miles=round(peak_run, 1),
        block_weeks=n,
        weeks=weeks,
        flags=plan_flags,
        notes=notes,
    )
    entry_w1 = sum(cell.miles or 0.0 for cell in rows[0] if cell.kind != WorkoutKind.CROSS)
    return common.adapt_training_plan(plan, inputs, native_run_days=6, entry_week1_mpw=entry_w1)
