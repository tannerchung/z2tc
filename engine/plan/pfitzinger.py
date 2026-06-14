"""Pfitzinger marathon generator.

Mesocycles (Endurance -> LT + Endurance -> Race Prep -> Taper) with a midweek
medium-long run, marathon-pace-loaded long runs, lactate-threshold tempos, and VO2max
intervals. No long-run time cap; long runs build 16 -> 20-22 mi on an established base.
"""

from __future__ import annotations

from . import common
from .models import (
    AthleteInputs,
    MARATHON_M,
    PlannedWeek,
    TrainingPlan,
    Workout,
    WorkoutKind,
    secondary_marathon_flags,
    training_plan_goal_payload,
)

TAPER_WEEKS = 3
LR = common.LONG_RUN_DAY


def _phase(wk: int, build_n: int) -> str:
    if wk > build_n:
        return "Taper"
    e1 = max(1, round(build_n * 0.40))
    e2 = max(e1 + 1, round(build_n * 0.75))
    if wk <= e1:
        return "Endurance"
    if wk <= e2:
        return "LT + Endurance"
    return "Race Prep"


def build_pfitzinger_plan(inputs: AthleteInputs, paces: dict) -> TrainingPlan:
    peak = common.peak_mileage(inputs)
    n = inputs.block_weeks
    taper_weeks = min(TAPER_WEEKS, n - 1)
    build_n = n - taper_weeks

    vols = common.weekly_volumes(inputs.w_now, peak, n, inputs.days_per_week, taper_weeks)
    easy_s, easy_str = common.easy_pace(paces)
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = common.goal_flags(mp_s, paces["threshold_s"], paces["marathon_s"])
    plan_flags += secondary_marathon_flags(inputs)
    if common.needs_base_phase(inputs, vols[0]):
        plan_flags.append(
            f"base phase needed: week 1 target {vols[0]:g} mi exceeds current {inputs.w_now:g} mi"
        )

    tune_up_week = None  # mark the first race-prep week for a tune-up race
    weeks: list[PlannedWeek] = []
    for i in range(n):
        wk = i + 1
        target = vols[i]
        phase = _phase(wk, build_n)
        is_down = wk <= build_n and wk % 4 == 0
        caps = common.session_caps(target)
        week_flags: list[str] = []
        fixed: dict[str, Workout] = {}

        if phase == "Taper":
            if wk == n:
                fixed[LR] = Workout(
                    WorkoutKind.RACE, f"{inputs.race_name} - race day", distance_mi=round(MARATHON_M / common.METERS_PER_MILE, 1)
                )
            else:
                fixed["Wed"] = common.medium_long_run(round(min(12.0, target * 0.25), 1), easy_s, easy_str)
                fixed["Tue"] = common.threshold_workout(min(caps["T"], 4.0), paces["threshold_s"], paces["threshold"])
                fixed[LR] = common.long_run_easy(round(target * 0.40, 1), easy_s, easy_str)
        else:
            long_mi = min(common.pfitzinger_long_run(wk, build_n), round(target * 0.40, 1))
            mlr_mi = min(15.0, max(11.0, round(target * 0.25, 1)))
            fixed["Wed"] = common.medium_long_run(round(mlr_mi, 1), easy_s, easy_str)

            if is_down:
                fixed[LR] = common.long_run_easy(round(long_mi * 0.85, 1), easy_s, easy_str)
            elif phase == "Endurance":
                fixed[LR] = common.long_run_easy(round(long_mi, 1), easy_s, easy_str)
                fixed["Tue"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
            else:
                fixed[LR] = common.mp_long_run(round(long_mi, 1), caps["M"], mp_s, mp_str, easy_s)
                if phase == "LT + Endurance":
                    fixed["Tue"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                else:  # Race Prep
                    fixed["Tue"] = common.interval_workout(caps["I"], paces["interval_s"], paces["interval"])
                    if tune_up_week is None:
                        tune_up_week = wk
                        week_flags.append("tune-up race (8-15K) recommended this week; recompute VDOT after")

        days = common.assemble_week(inputs.days_per_week, target, fixed, easy_s, easy_str)
        label = f"{phase}{' (down week)' if is_down else ''}"
        weeks.append(
            PlannedWeek(
                index=wk,
                phase=phase,
                label=label,
                target_miles=target,
                is_down_week=is_down,
                days=days,
                flags=week_flags,
            )
        )

    return TrainingPlan(
        athlete=inputs.name,
        method=common.PFITZINGER,
        goal=training_plan_goal_payload(inputs),
        vdot=inputs.vdot,
        paces=paces,
        peak_miles=peak,
        block_weeks=n,
        weeks=weeks,
        flags=plan_flags,
    )


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"
