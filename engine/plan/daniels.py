"""Daniels-style marathon generator (Zone 2 Track Club).

Two quality sessions per week. In the marathon-specific phases the Saturday Q1 is a
**nonstop E/M/T blend** (`common.marathon_q1_workout`, mirroring Daniels' 2Q Table 14.3),
with a midweek Q2 (threshold or intervals). Every 4th week is a **club cutback / down week**
(~80% volume). Long-run length follows the Daniels time/share rule plus a **house rule**
(see ``common.daniels_long_run``); quality volume is bounded by the single-session caps.
Strides are an economy touch — at most ``common.STRIDES_PER_PHASE`` stride weeks per phase, not
every week. The ``long_run_cap_mi`` coach override (monitored) replaces the time/share cap with a
progressive ramp that tops out at the cap only for the final ``long_run_peak_weeks`` build weeks
(``common.coach_long_run_targets``). Phases: Base -> Threshold -> Race Prep -> Taper.
"""

from __future__ import annotations

from datetime import date

from . import common, workouts
from .models import (
    DAY_NAMES,
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


def _race_weekday(race_date: str) -> str:
    """The marathon's real day of week. Club long runs are Saturday, but the race — and its
    day-before shakeout — must land on the actual race weekday (e.g. a Sunday Chicago start)."""
    try:
        return DAY_NAMES[date.fromisoformat(race_date[:10]).weekday()]
    except (ValueError, TypeError):
        return common.LONG_RUN_DAY


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
    # Default is Daniels' "hold ~3 weeks before stepping in new territory" (p.219). A coach can
    # opt a monitored athlete into a faster ramp (+1 mi/running-day EVERY week, capped at peak)
    # via the aggressive_volume_ramp override, so the build reaches and holds the demonstrated
    # peak inside the block. Step size and the peak ceiling are unchanged either way.
    hold_weeks = 1 if inputs.aggressive_volume_ramp else 3
    vols = common.weekly_volumes(
        start, peak, n, inputs.days_per_week, taper_weeks,
        hold_weeks=hold_weeks, comeback_peak=common.comeback_peak_mpw(inputs),
    )
    step_up = common.volume_step_ups(vols)
    easy_s, easy_str = common.easy_pace(paces)
    long_s = common.long_run_pace_s(inputs, easy_s)
    q2_day = common.midweek_quality_day(inputs.days_per_week)  # midweek Q2, kept clear of the Sat long
    mp_s = common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = _fmt(mp_s)

    plan_flags = common.goal_flags(mp_s, paces["threshold_s"], paces["marathon_s"])
    plan_flags += secondary_marathon_flags(inputs)
    if not inputs.race_fit and common.needs_base_phase(inputs, vols[0]):
        plan_flags.append(
            f"base phase needed: week 1 target {vols[0]:g} mi exceeds current {inputs.w_now:g} mi; "
            "bridge with easy base weeks before week 1"
        )
    race_dow = _race_weekday(inputs.race_date)
    if race_dow not in ("Sat", "Sun"):
        plan_flags.append(
            f"race falls on {race_dow} (not a weekend) — club Saturday long runs and the taper "
            "may need re-anchoring nearer race day; review the final-week spacing"
        )

    achieved_peak = max(vols[:build_n]) if build_n else 0.0
    if achieved_peak + 0.05 < peak:
        ramp_note = "even the +1 mi/day weekly ramp" if inputs.aggressive_volume_ramp else "holding the ramp (Daniels p.219)"
        plan_flags.append(
            f"peak not reached: {ramp_note} tops the build at {achieved_peak:g} mi vs P {peak:g} mi — "
            "raise the re-entry start, lengthen the block, or enable the aggressive ramp"
        )
    if inputs.aggressive_volume_ramp:
        plan_flags.append(
            "coach override: +1 mi per running day every week to the demonstrated peak (faster than "
            "Daniels' 3-week hold) — monitor adherence and fatigue weekly"
        )
    if inputs.long_run_cap_mi:
        peak_weeks = inputs.long_run_peak_weeks or common.DEFAULT_LONG_RUN_PEAK_WEEKS
        plan_flags.append(
            f"coach override: long run ramps progressively to {inputs.long_run_cap_mi:g} mi and tops out "
            f"there ~{peak_weeks} week(s) before the taper (over the 3 h time-on-feet / weekly-share "
            "caps) — monitor long-run recovery and fueling"
        )
    if inputs.quality_long_runs_race_prep_only:
        plan_flags.append(
            "coach override: threshold long runs kept easy/aerobic (midweek Q2 carries the quality); "
            "quality long runs confined to the race-prep block and spaced — suited to a 4-day load"
        )

    # The last non-down build week carries the dress rehearsal (race-practice long run) — the
    # block's most race-specific session, landing ~3-4 weeks out before the taper trims volume.
    dress_rehearsal_wk = max(
        (wk for wk in range(1, build_n + 1) if _phase(wk, build_n) == "Race Prep" and wk % 4 != 0),
        default=0,
    )

    # Coach long-run cap: precompute a progressive ramp to the cap that only tops out for the last
    # few build weeks, rather than reaching the cap and holding it most of the block.
    override_long: dict[int, float] | None = None
    if inputs.long_run_cap_mi:
        override_long = common.coach_long_run_targets(
            vols, build_n, inputs.long_run_cap_mi,
            inputs.long_run_peak_weeks or common.DEFAULT_LONG_RUN_PEAK_WEEKS, long_s,
        )

    weeks: list[PlannedWeek] = []
    peak_long_mi = 0.0
    long_run_cites: list[str] = []
    strides_used: dict[str, int] = {}  # phase → stride weeks placed (capped at STRIDES_PER_PHASE)
    t_occ = 0       # threshold-phase Q2 (midweek) rotation counter
    rp_occ = 0      # race-prep Q2 (midweek) rotation counter
    t_q1_occ = 0    # threshold-phase long-run rotation counter
    rp_q1_occ = 0   # race-prep long-run rotation counter
    base_q1_occ = 0  # base-phase long-run rotation counter (easy ↔ fartlek)
    taper_occ = 0   # taper Q2 rotation counter (short threshold → race-pace sharpener)
    for i in range(n):
        wk = i + 1
        target = vols[i]
        phase = _phase(wk, build_n)
        is_down = wk <= build_n and wk % 4 == 0
        caps = common.session_caps(target, mp_s)
        week_flags: list[str] = []
        fixed: dict[str, Workout] = {}

        if phase == "Taper":
            if wk == n:  # race week — dedicated shakeout structure, built below
                race = Workout(
                    WorkoutKind.RACE, f"{inputs.race_name} - race day", distance_mi=round(MARATHON_M / common.METERS_PER_MILE, 1)
                )
            else:
                # The long run steps DOWN through the taper as a fraction of the peak long run
                # (Daniels ch.14 / Pfitzinger ch.7) — it must not sit near peak two weeks out.
                taper_pos = wk - (build_n + 1)               # 0-based index among non-race taper weeks
                fracs = common.taper_long_fracs(taper_weeks - 1)
                frac = fracs[taper_pos] if taper_pos < len(fracs) else fracs[-1]
                taper_long = min(
                    round((peak_long_mi or common.LONG_RUN_CAP_MI) * frac, 1),
                    round(target * 0.55, 1),               # still a sane share of the cut week
                )
                fixed[LR] = common.long_run_easy(round(taper_long, 1), easy_s, easy_str)
                # Rotate a light quality touch: a short threshold first, then a race-pace
                # sharpener nearer the race (mirrors the Runna taper: a goal-pace session in
                # the final weeks). Volume is trimmed inside the catalog builders.
                taper_ctx = workouts.WeekContext(
                    caps=caps, paces=paces, mp_s=mp_s, mp_str=mp_str, easy_s=easy_s, easy_str=easy_str,
                )
                fixed[q2_day] = workouts.taper_q2(taper_occ, taper_ctx)
                taper_occ += 1
        else:
            lr = common.daniels_long_run(target, long_s)
            if override_long is not None:
                # Coach override (monitored): follow the precomputed ramp, which climbs toward the
                # cap and only sits at it for the final few build weeks (down weeks are book
                # cutbacks). The ramp may exceed the 3 h / weekly-share safety caps near the peak.
                base_long_mi = override_long[wk]
                long_mi = base_long_mi
            else:
                base_long_mi = lr.recommended_mi
                week_flags += lr.flags
                long_mi = base_long_mi * (0.85 if is_down else 1.0)
            if base_long_mi > peak_long_mi:
                peak_long_mi = base_long_mi
                long_run_cites = lr.citations
            ctx = workouts.WeekContext(
                caps=caps, paces=paces, mp_s=mp_s, mp_str=mp_str,
                easy_s=easy_s, easy_str=easy_str, long_mi=round(long_mi, 1),
            )
            # Long run: easy in Base / down weeks; otherwise rotate the catalog's phase menu so
            # the quality long run varies with purpose (blend → progression; then MP blocks →
            # fast finish as race day nears) instead of the same E/M/T blend every week.
            # Coach override (quality_long_runs_race_prep_only): on a 4-day load, Daniels' Q1
            # long run doesn't have to be hard every week (Higdon's 4-day plan keeps every long
            # run easy; Daniels caps/recovers Q1). Keep threshold long runs easy/aerobic — the
            # midweek Q2 carries the weekly quality — and confine quality long runs to the
            # race-specific block, alternated with easy longs so they're spaced.
            sparse_lr = inputs.quality_long_runs_race_prep_only
            if is_down:
                fixed[LR] = common.long_run_easy(round(long_mi, 1), easy_s, easy_str)
            elif phase == "Base":
                # Base long runs are aerobic; rotate plain easy ↔ a light fartlek for variety.
                fixed[LR] = workouts.base_long(base_q1_occ, ctx)
                base_q1_occ += 1
            elif phase == "Threshold":
                if sparse_lr:
                    fixed[LR] = workouts.base_long(base_q1_occ, ctx)
                    base_q1_occ += 1
                else:
                    fixed[LR] = workouts.long_run_for_phase("Threshold", t_q1_occ, ctx)
                    t_q1_occ += 1
            elif wk == dress_rehearsal_wk:
                fixed[LR] = workouts.named("race_practice", ctx)
            elif sparse_lr and rp_q1_occ % 2 == 1:
                # Space the race-prep quality longs with an easy aerobic long every other week.
                fixed[LR] = workouts.base_long(base_q1_occ, ctx)
                base_q1_occ += 1
                rp_q1_occ += 1
            else:  # Race Prep quality long run
                fixed[LR] = workouts.long_run_for_phase("Race Prep", rp_q1_occ, ctx)
                rp_q1_occ += 1

            if not is_down:
                if phase == "Threshold":
                    # Rotate the T format week to week (same threshold stimulus, different feel):
                    # cruise miles → tempo → broken-T → over/unders.
                    fixed[q2_day] = workouts.threshold_q2(t_occ, ctx)
                    t_occ += 1
                elif phase == "Race Prep":
                    # Defer hard VO2max off mileage step-up weeks (Daniels p.36 / Pfitzinger
                    # ch.3): don't raise volume and pile on intervals the same week.
                    if step_up[i]:
                        fixed[q2_day] = common.threshold_workout(caps["T"], paces["threshold_s"], paces["threshold"])
                        week_flags.append("VO2max deferred this week (mileage step-up) — quality held at threshold")
                    else:
                        # Rotate the sharpener: VO2max 1000s → pyramid → descending → R reps.
                        fixed[q2_day] = workouts.race_prep_q2(rp_occ, ctx)
                        rp_occ += 1

        # Strides are an economy touch, not a weekly fixture: at most STRIDES_PER_PHASE stride
        # weeks per phase (front-loaded), and never on a recovery/down week.
        stride_days = 0
        if not is_down and strides_used.get(phase, 0) < common.STRIDES_PER_PHASE:
            stride_days = 1
            strides_used[phase] = strides_used.get(phase, 0) + 1

        if phase == "Taper" and wk == n:
            days = common.race_week_days(
                inputs.days_per_week, race, easy_s, easy_str, race_day=_race_weekday(inputs.race_date)
            )
        else:
            # In the taper, cap easy days so a shortened long run sheds volume rather than
            # piling onto the midweek easy runs.
            max_easy = 6.0 if phase == "Taper" else None
            days = common.assemble_week(
                inputs.days_per_week, target, fixed, easy_s, easy_str,
                stride_days=stride_days, max_easy_mi=max_easy,
            )
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
