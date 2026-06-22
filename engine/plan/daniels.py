"""Daniels-style marathon generator (Zone 2 Track Club).

Two quality sessions per week. In the marathon-specific phases the Saturday Q1 is a
**nonstop E/M/T blend** (`common.marathon_q1_workout`, mirroring Daniels' 2Q Table 14.3),
with a midweek Q2 (threshold or intervals). Every 4th week is a **club cutback / down week**
(~80% volume). Long-run length follows the Daniels time/share rule plus a **house rule**
(see ``common.daniels_long_run``); quality volume is bounded by the single-session caps.
Phases: Base -> Threshold -> Race Prep -> Taper.
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

    start = common.ramp_start(inputs)
    # Below demonstrated capacity she's regaining fitness, not charting new territory, so the
    # ramp climbs quickly back to p_history (Daniels ch.15, p.284) and only slows above it.
    vols = common.weekly_volumes(
        start, peak, n, inputs.days_per_week, taper_weeks, comeback_peak=common.comeback_peak_mpw(inputs)
    )
    step_up = common.volume_step_ups(vols)
    easy_s, easy_str = common.easy_pace(paces)
    long_s = common.long_run_pace_s(inputs, easy_s)
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = common.goal_flags(mp_s, paces["threshold_s"], paces["marathon_s"])
    plan_flags += secondary_marathon_flags(inputs)
    if not inputs.race_fit and common.needs_base_phase(inputs, vols[0]):
        plan_flags.append(
            f"base phase needed: week 1 target {vols[0]:g} mi exceeds current {inputs.w_now:g} mi; "
            "bridge with easy base weeks before week 1"
        )
    achieved_peak = max(vols[:build_n]) if build_n else 0.0
    if achieved_peak + 0.05 < peak:
        plan_flags.append(
            f"peak not reached: holding the ramp (Daniels p.219) tops the build at {achieved_peak:g} mi "
            f"vs P {peak:g} mi — raise the re-entry start or lower P"
        )

    weeks: list[PlannedWeek] = []
    peak_long_mi = 0.0
    long_run_cites: list[str] = []
    for i in range(n):
        wk = i + 1
        target = vols[i]
        phase = _phase(wk, build_n)
        is_down = wk <= build_n and wk % 4 == 0
        caps = common.session_caps(target, mp_s)
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
            lr = common.daniels_long_run(target, long_s)
            week_flags += lr.flags
            long_mi = lr.recommended_mi * (0.85 if is_down else 1.0)
            if lr.recommended_mi > peak_long_mi:
                peak_long_mi = lr.recommended_mi
                long_run_cites = lr.citations
            if phase == "Base" or is_down:
                fixed[LR] = common.long_run_easy(round(long_mi, 1), easy_s, easy_str)
            else:
                fixed[LR] = common.marathon_q1_workout(
                    round(long_mi, 1), caps["M"], mp_s, mp_str,
                    paces["threshold_s"], paces["threshold"], easy_s, easy_str,
                )

            if not is_down:
                if phase == "Threshold":
                    fixed["Wed"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                elif phase == "Race Prep":
                    # Defer hard VO2max off mileage step-up weeks (Daniels p.36 / Pfitzinger
                    # ch.3): don't raise volume and pile on intervals the same week.
                    if step_up[i]:
                        fixed["Wed"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                        week_flags.append("VO2max deferred this week (mileage step-up) — quality held at threshold")
                    else:
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

    notes = common.long_run_notes(peak_long_mi, long_s, long_run_cites) if peak_long_mi else []

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
        notes=notes,
    )


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"
