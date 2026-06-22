"""Higdon marathon programs — verbatim weekly grids (halhigdon.com), single-author reference.

Novice 1/2: Mon+Fri rest, Sun cross (60 min). Intermediate 1/2: Mon cross, Fri rest,
Sat pace + Sun long back-to-back. Paces filled from VDOT easy range + goal MP; Higdon does
not prescribe VDOT — MP is goal race pace (p.78).
"""

from __future__ import annotations

from . import citations
from . import common
from .higdon_grids import PROGRAMS
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

NOVICE_MAX_MPW = 25.0
CITE_NOVICE = "Higdon, Marathon: The Ultimate Training Guide (Novice program; p.46 entry ~15-25 mpw)"


def build_higdon_plan(inputs: AthleteInputs, paces: dict) -> TrainingPlan:
    prog_key = (inputs.higdon_program or "novice1").lower().replace(" ", "")
    if prog_key not in PROGRAMS:
        prog_key = "novice1"
    rows = PROGRAMS[prog_key]

    easy_s, easy_str = common.easy_pace(paces)
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = secondary_marathon_flags(inputs)
    base = max(inputs.w_now, inputs.p_history)
    if prog_key.startswith("novice") and base > NOVICE_MAX_MPW + 0.05:
        plan_flags.append(
            f"above Higdon Novice range: demonstrated ~{base:g} mpw exceeds ~{NOVICE_MAX_MPW:g} mpw Novice entry "
            f"({CITE_NOVICE}) — consider Intermediate 1/2"
        )

    native_run_days = 5 if prog_key.startswith("intermediate") else 4

    entry_w1 = sum(cell.miles or 0.0 for cell in rows[0] if cell.kind != WorkoutKind.CROSS)

    weeks: list[PlannedWeek] = []
    prev_long: float | None = None
    peak_run = 0.0
    n_weeks = len(rows)

    for i, row in enumerate(rows):
        wk = i + 1
        days: list[PlannedDay] = []
        cur_long_mi: float | None = None
        for day, cell in zip(DAY_NAMES, row):
            w = cell.to_workout(paces, mp_s, mp_str, easy_s, easy_str)
            if w.kind == WorkoutKind.RACE:
                if w.distance_mi and abs(w.distance_mi - 26.2) < 0.1:
                    w.label = f"{inputs.race_name} - race day"
                elif w.distance_mi and abs(w.distance_mi - 13.1) < 0.1:
                    w.flags.append("tune_up_race")
            days.append(PlannedDay(day, w))
            if w.kind == WorkoutKind.LONG and w.distance_mi:
                cur_long_mi = float(w.distance_mi)

        run_mi = sum(d.running_miles for d in days)
        peak_run = max(peak_run, run_mi)
        if wk > n_weeks - 3:
            phase, is_down = "Taper", False
        else:
            if cur_long_mi is not None and prev_long is not None and cur_long_mi < prev_long - 0.5:
                phase, is_down = "Stepback", True
            else:
                phase, is_down = "Build", False
        if cur_long_mi is not None:
            prev_long = cur_long_mi

        weeks.append(
            PlannedWeek(
                index=wk,
                phase=phase,
                label=phase + (" (stepback)" if is_down else ""),
                target_miles=round(run_mi, 1),
                is_down_week=is_down,
                days=days,
                flags=[],
            )
        )

    notes = [
        citations.PACE_BASIS["higdon"],
        str(citations.get("higdon_pace_basis")),
        str(citations.get("higdon_novice_schedule")),
        f"long-run peak — {citations.get('higdon_20')}",
    ]

    plan = TrainingPlan(
        athlete=inputs.name,
        method=common.HIGDON,
        goal=training_plan_goal_payload(inputs),
        vdot=inputs.vdot,
        paces=paces,
        peak_miles=round(peak_run, 1),
        block_weeks=len(rows),
        weeks=weeks,
        flags=plan_flags,
        notes=notes,
    )
    return common.adapt_training_plan(
        plan,
        inputs,
        native_run_days=native_run_days,
        entry_week1_mpw=entry_w1,
    )


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"
