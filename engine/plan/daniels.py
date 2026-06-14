"""Daniels-style marathon generator (Zone 2 Track Club).

Two quality sessions per week (Saturday long run + midweek quality). Every 4th week is
a **club cutback / down week** (~80% volume) — sound practice, but not a literal quote of
Daniels' 2Q program naming. Long runs follow the Daniels time/share rule plus a **house
rule** when ``marathon_build`` is true (see ``common.daniels_long_run``). Quality volume
is bounded by the single-session caps. Phases: Base -> Threshold -> Race Prep -> Taper.
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
    b1 = max(1, round(build_n * 0.33))
    b2 = max(b1 + 1, round(build_n * 0.66))
    if wk <= b1:
        return "Base"
    if wk <= b2:
        return "Threshold"
    return "Race Prep"


def build_daniels_plan(inputs: AthleteInputs, paces: dict) -> TrainingPlan:
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
            f"base phase needed: week 1 target {vols[0]:g} mi exceeds current {inputs.w_now:g} mi; "
            "bridge with easy base weeks before week 1"
        )

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
            if wk == n:  # race week
                fixed[LR] = Workout(
                    WorkoutKind.RACE, f"{inputs.race_name} - race day", distance_mi=round(MARATHON_M / common.METERS_PER_MILE, 1)
                )
            else:
                fixed["Wed"] = common.threshold_workout(min(caps["T"], 4.0), paces["threshold_s"], paces["threshold"])
                fixed[LR] = common.long_run_easy(round(target * 0.45, 1), easy_s, easy_str)
        else:
            lr = common.daniels_long_run(target, easy_s)
            week_flags += lr.flags
            long_mi = lr.recommended_mi * (0.85 if is_down else 1.0)
            if phase == "Base" or is_down:
                fixed[LR] = common.long_run_easy(round(long_mi, 1), easy_s, easy_str)
            else:
                fixed[LR] = common.mp_long_run(round(long_mi, 1), caps["M"], mp_s, mp_str, easy_s)

            if not is_down:
                if phase == "Threshold":
                    fixed["Wed"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                elif phase == "Race Prep":
                    fixed["Wed"] = common.interval_workout(caps["I"], paces["interval_s"], paces["interval"])

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
        method=common.DANIELS,
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
