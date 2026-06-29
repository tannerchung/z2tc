"""Pfitzinger marathon generator.

Mesocycles (Endurance -> LT + Endurance -> Race Prep -> Taper) with a midweek
medium-long run, marathon-pace-loaded long runs, lactate-threshold tempos, and VO2max
intervals. No long-run time cap; long runs build by distance toward 20-22 mi (p.43).

Pfitzinger publishes **tiered** schedules (chapters 8-11), each with a fixed peak and a
prescribed week-1 starting mileage that assumes you are already based near it. This engine
selects a tier, peaks at the tier's peak (NOT ``p_history``), and starts at the tier's week-1
volume — flagging an athlete who is below the entry base, who is reaching past demonstrated
capacity, or who runs fewer than Pfitzinger's 5-7 days.
"""

from __future__ import annotations

from . import citations
from . import common
from . import pfitz_grids
from .models import (
    AthleteInputs,
    DAY_NAMES,
    GridCell,
    MARATHON_M,
    PlannedDay,
    PlannedWeek,
    TrainingPlan,
    Workout,
    WorkoutKind,
    secondary_marathon_flags,
    training_plan_goal_payload,
)

TAPER_WEEKS = 3
LR = common.LONG_RUN_DAY

def _seat_long_run_on_club_day(grid_row: list[GridCell]) -> list[GridCell]:
    """Shift a ch.8 grid week one day earlier so the long run lands on the club's Saturday.

    Pfitzinger's grid (``pfitz_grids``) is transcribed verbatim with the week running Monday→Sunday:
    a Monday rest, the long run last (Sunday), and on tune-up weeks the race the day *before* the long
    run. The club runs its long run on Saturday like every other engine path. Rotating the week left
    by one day moves the long run Sunday→Saturday and the Monday rest→Sunday while preserving every
    *relative* relationship Pfitzinger built — the recovery day before the long run, the spacing
    between quality sessions, and the race→long-run order (Table 3.1, pp.112-113: a long run needs no
    recovery gap from a different workout type because they tax different systems). A plain Sat/Sun
    swap would instead invert that order (long run before the race) and collapse the pre-long-run
    recovery day, so we shift rather than swap.

    The goal-marathon week is left untouched so the marathon stays on its actual (Sunday) race date.
    """
    last = grid_row[-1]
    if last.kind == WorkoutKind.RACE and (last.miles or 0) > 20:  # goal-marathon week
        return grid_row
    return grid_row[1:] + grid_row[:1]

# Pfitzinger's tiered schedules: (peak_mpw, week-1 mpw, week-1 long run, label). Week-1 figures
# come from each chapter's "Before Starting the Schedules" readiness example (p.285/302/320/338).
PFITZ_TIERS: list[tuple[float, float, float, str]] = [
    (55.0, 33.0, 12.0, "ch.8 (up to 55 mpw)"),
    (70.0, 54.0, 15.0, "ch.9 (55-70 mpw)"),
    (85.0, 65.0, 17.0, "ch.10 (70-85 mpw)"),
    (101.0, 82.0, 17.0, "ch.11 (85+ mpw)"),
]


def select_tier(demonstrated_mpw: float) -> tuple[float, float, float, str]:
    """Lowest Pfitzinger tier whose peak covers demonstrated capacity (``p_history``). Demonstrated
    mileage is a *floor* for tier choice, never a ceiling on the peak — a returner can still aim
    past it (flagged as new territory)."""
    for tier in PFITZ_TIERS:
        if demonstrated_mpw <= tier[0] + 0.05:
            return tier
    return PFITZ_TIERS[-1]


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
    n = inputs.block_weeks
    taper_weeks = min(TAPER_WEEKS, n - 1)
    build_n = n - taper_weeks

    # Pfitzinger plans are tiered (ch.8-11): peak and week-1 come from the chosen tier, not from
    # p_history. Start no lower than the tier's prescribed week 1 (his schedules open already-based).
    peak, week1, _week1_long, tier_label = select_tier(max(inputs.p_history, inputs.w_now))
    start = max(week1, common.ramp_start(inputs))
    use_ch8_spine = abs(peak - 55.0) < 0.06 and n == len(pfitz_grids.CH8_18WK_TOTALS_MI)
    if use_ch8_spine:
        vols = list(pfitz_grids.CH8_18WK_TOTALS_MI)
        ch8_down = pfitz_grids.ch8_down_week_flags()
        plan_flags_pre: list[str] = []
        plan_flags_pre.append(
            "Pfitzinger ch.8 18-wk **weekly mileage spine** (``engine/plan/pfitz_grids.py``): "
            "week 1 = 33 mi, peak = 55 mi per *Advanced Marathoning* ch.8; individual workout "
            "distances are still assembled by the engine from mesocycle rules — re-check day cells "
            "against pp.292–295 when the HK PDF is available locally."
        )
    else:
        vols = common.weekly_volumes(start, peak, n, inputs.days_per_week, taper_weeks)
        ch8_down = None
        plan_flags_pre = []

    step_up = common.volume_step_ups(vols)
    easy_s, easy_str = common.easy_pace(paces)
    long_s = common.long_run_pace_s(inputs, easy_s)
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = plan_flags_pre + common.goal_flags(mp_s, paces["threshold_s"], paces["marathon_s"])
    plan_flags += secondary_marathon_flags(inputs)
    plan_flags.append(f"Pfitzinger tier: {tier_label} — opens at a ~{week1:g}-mi week, peaks at {peak:g} mpw")
    step = max(1, min(inputs.days_per_week, 10))  # one safe weekly increment (Daniels p.219)
    if inputs.w_now + step + 0.05 < week1:
        plan_flags.append(
            f"below entry base: {tier_label} opens at a ~{week1:g}-mi week but current volume is "
            f"{inputs.w_now:g} mpw — Pfitzinger (p.285) says build a base up to ~{week1:g} mi before "
            "starting (or use Daniels to bridge there first)"
        )
    if peak > inputs.p_history + 0.5:
        plan_flags.append(
            f"uncharted peak: {peak:g} mpw is above demonstrated {inputs.p_history:g} mpw — reachable "
            "but new territory; confirm the athlete can sustain this tier (or choose a lower one)"
        )
    if inputs.days_per_week < 5:
        plan_flags.append(
            f"low frequency for Pfitzinger: his schedules run 5-7 days (p.271); a {inputs.days_per_week}-day "
            "week under-represents the structure (medium-long + 2 quality + long)"
        )
    achieved_peak = max(vols[:build_n]) if build_n else 0.0
    if achieved_peak + 0.05 < peak:
        plan_flags.append(
            f"peak not reached: holding the ramp (Daniels p.219 / Pfitz p.50) tops the build at "
            f"{achieved_peak:g} mi vs the {peak:g}-mpw tier peak"
        )

    tune_up_week = None  # mark the first race-prep week for a tune-up race
    weeks: list[PlannedWeek] = []
    peak_long_mi = 0.0
    for i in range(n):
        wk = i + 1
        target = vols[i]
        phase = _phase(wk, build_n)
        is_down = ch8_down[i] if ch8_down is not None else (wk <= build_n and wk % 4 == 0)
        caps = common.session_caps(target, mp_s)
        week_flags: list[str] = []
        fixed: dict[str, Workout] = {}

        if use_ch8_spine:
            days: list[PlannedDay] = []
            grid_row = _seat_long_run_on_club_day(pfitz_grids.CH8_18WK_GRID[i])
            for day, cell in zip(DAY_NAMES, grid_row):
                w = cell.to_workout(paces, mp_s, mp_str, easy_s, easy_str)
                if w.kind == WorkoutKind.RACE:
                    if w.distance_mi and abs(w.distance_mi - 26.2) < 0.1:
                        w.label = f"{inputs.race_name} - race day"
                    elif "tune-up" in (w.label or "").lower():
                        w.flags.append("tune_up_race")
                        if "8-10K" in (w.label or ""):
                            week_flags.append("tune-up race (8-10K) recommended this week; recompute VDOT after")
                        else:
                            week_flags.append("tune-up race (8-15K) recommended this week; recompute VDOT after")
                        week_flags.append(
                            "tune-up sits Friday, the day before the Saturday long run (Pfitzinger's "
                            "race-then-long-run pairing) — move it to the race's actual date if it "
                            "differs and keep that day's run easy"
                        )
                elif "dress rehearsal" in (w.label or "").lower():
                    w.flags.append("dress_rehearsal")
                days.append(PlannedDay(day, w))
            
            # Find long run distance for peak_long_mi
            long_kinds = {WorkoutKind.LONG, WorkoutKind.MARATHON_PACE, WorkoutKind.MEDIUM_LONG}
            longs = [d for d in days if d.workout.kind in long_kinds]
            if longs:
                long_mi = max(d.miles for d in longs)
                peak_long_mi = max(peak_long_mi, long_mi)
        else:
            # Pfitzinger long run climbs by distance toward 20-22 mi (p.43). His "16 mi = a
            # long run" (p.257) is a definition, not a floor — the ≤55 schedule opens ~12 mi
            # (p.285) — so don't force 16; just keep it a sane fraction of the week.
            long_mi = min(common.pfitzinger_long_run(wk, build_n), round(target * 0.45, 1))
            peak_long_mi = max(peak_long_mi, long_mi)
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
                    # Defer hard VO2max off mileage step-up weeks (Pfitzinger ch.3 / Daniels p.36).
                    if step_up[i]:
                        fixed["Tue"] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                        week_flags.append("VO2max deferred this week (mileage step-up) — quality held at threshold")
                    else:
                        fixed["Tue"] = common.interval_workout(caps["I"], paces["interval_s"], paces["interval"])
                        if tune_up_week is None:
                            tune_up_week = wk
                            week_flags.append("tune-up race (8-15K) recommended this week; recompute VDOT after")

            days = common.assemble_week(inputs.days_per_week, target, fixed, easy_s, easy_str,
                                        stride_pace_s=paces.get("rep_s"))

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

    notes = [
        citations.PACE_BASIS["pfitzinger"],
        str(citations.get("pfitz_pace_basis")),
    ]
    if use_ch8_spine:
        notes.append(str(citations.get("pfitz_ch8_schedule")))
    if peak_long_mi:
        notes += common.long_run_notes(peak_long_mi, long_s, ["pfitz_long_run_cap"])

    plan = TrainingPlan(
        athlete=inputs.name,
        method=common.PFITZINGER,
        goal=training_plan_goal_payload(inputs),
        vdot=inputs.vdot,
        paces=paces,
        peak_miles=peak,
        block_weeks=n,
        weeks=weeks,
        flags=plan_flags,
        notes=notes,
    )
    return common.adapt_training_plan(plan, inputs, native_run_days=6, entry_week1_mpw=33.0)


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"
