"""Deterministic building blocks shared by both generators.

Every rule here is a direct transcription of the project's Training Plan Formula
Reference (sections cited inline as e.g. "sec.4"). Pure arithmetic, no IO. The
generators compose these; the numbers come out the same way every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import DAY_NAMES, AthleteInputs, PlannedDay, PlannedWeek, Segment, TrainingPlan, Workout, WorkoutKind

METERS_PER_MILE = 1609.344
MARATHON_MILES = 42195.0 / METERS_PER_MILE  # ~26.219
TEN_K_MILES = 10000.0 / METERS_PER_MILE     # ~6.214
LONG_RUN_CAP_MIN = 150                      # Daniels' easy long-run (L) time cap (p.63-64)
LONG_RUN_CAP_MIN_M = 110                    # Daniels' marathon-pace (M) run time cap (p.62, p.65)
LONG_RUN_CAP_MI = 18                        # Daniels' practical long-run distance cap (Table 14.3, p.237)

# Only Daniels and Hanson put a *time cap* on the long run (the muscle-breakdown ceiling):
# Daniels 150 min (p.63), Hanson a 2–3 h window — "beyond that, muscle breakdown begins to
# occur" (p.66). Pfitzinger and Higdon cap by *distance* (20–22 mi), not time — though
# Higdon's own rationale (p.27: glycogen depletes "after about 2 hours … or about 20 miles
# for an accomplished runner") and Pfitz's 90-min benefit floor (p.42) point the same way.
# z2tc adopts the Daniels/Hanson time ceiling and targets the 3 h upper bound, so a slower
# runner earns the same time-on-feet credit as a faster runner's longer run.
LONG_RUN_WINDOW_MIN = (120, 180)            # Hanson p.66: 2–3 h productive long-run window

DANIELS = "daniels"
PFITZINGER = "pfitzinger"
HIGDON = "higdon"
HANSON = "hanson"


# --- sec.1 Method assignment -----------------------------------------------------
def assign_method(inputs) -> str:
    """Pfitzinger needs an established base and 5+ days; otherwise Daniels. A forced
    ``inputs.method`` always wins (incl. the single-author reference engines, e.g. Higdon)."""
    if inputs.method in (DANIELS, PFITZINGER, HIGDON, HANSON):
        return inputs.method
    if inputs.p_history >= 40 and inputs.days_per_week >= 5:
        return PFITZINGER
    return DANIELS


# --- sec.2c Marathon pace + goal sanity flags ------------------------------------
def marathon_pace_s(goal_marathon_s: int) -> int:
    """Goal marathon pace, per mile, in seconds. MP is goal-driven, not VDOT-driven."""
    return round(goal_marathon_s / MARATHON_MILES)


def goal_flags(mp_s: int, threshold_s: int, vdot_marathon_s: int) -> list[str]:
    """Flag an aggressive goal: MP work behaves like tempo when the gap to Threshold
    is small, or when goal MP is well faster than VDOT-derived marathon pace."""
    flags: list[str] = []
    if mp_s - threshold_s < 10:
        flags.append("aggressive_goal: goal MP within ~10 s/mi of Threshold (MP will feel like tempo)")
    if mp_s < vdot_marathon_s - 10:
        flags.append("aggressive_goal: goal MP faster than current-fitness marathon pace")
    return flags


# --- sec.3 Weekly mileage progression --------------------------------------------
def peak_mileage(inputs) -> float:
    """Peak weekly volume (sec.3a): demonstrated capacity, with optional coach target.

    ``coach_target_mpw`` overrides the inferred peak when set (scenario generator / coach).
    """
    base = float(max(inputs.p_history, inputs.w_now))
    if inputs.coach_target_mpw is not None and inputs.coach_target_mpw > 0:
        return float(inputs.coach_target_mpw)
    return base


def comeback_peak_mpw(inputs) -> float:
    """Ceiling for the *fast* Daniels ch.15 regain (``weekly_volumes`` ``comeback_peak``).

    Defaults to demonstrated ``p_history``; ``coach_floor_mpw`` raises that ceiling when the
    coach asserts higher proven capacity during the regain phase.
    """
    p = float(inputs.p_history)
    if inputs.coach_floor_mpw is not None and inputs.coach_floor_mpw > p + 0.05:
        return float(inputs.coach_floor_mpw)
    return p


def _taper_fracs(taper_weeks: int) -> list[float]:
    """Fractions of peak for the final weeks (sec.3e): volume falls, intensity is held
    (the generators keep a short quality touch in the taper)."""
    table = {1: [0.55], 2: [0.70, 0.50], 3: [0.80, 0.62, 0.45]}
    return table.get(taper_weeks, [0.80, 0.62, 0.45])


def weekly_volumes(
    start: float,
    peak: float,
    n_weeks: int,
    days_per_week: int,
    taper_weeks: int = 3,
    hold_weeks: int = 3,
    down_week_every: int = 4,
    comeback_peak: float | None = None,
    comeback_hold_weeks: int = 1,
) -> list[float]:
    """Target weekly mileage for each week of the block (sec.3b-3e).

    **New territory (Daniels p.219, printed p.205):** increase weekly mileage *"about every
    4th week"*, by **1 mi per running session**, **never more than +10 mi** — "no need to go
    over 80 miles per week". Pfitzinger (p.50) explicitly adopts this same rule and adds
    *"increase in steps … when charting new territory, don't increase week after week."* So the
    build **holds** the level for ``hold_weeks`` running weeks, then **steps up** by
    ``min(days_per_week, 10)`` toward ``peak``. Every ``down_week_every``-th week is a
    **recovery week** at ~80% of the held level.

    **Comeback / regained territory (Daniels ch.15, p.284):** below ``comeback_peak`` the
    athlete is *regaining* demonstrated fitness, not charting new ground — Daniels returns a
    layoff athlete at ≤50% of prebreak mileage for the first half of the comeback and 75% for
    the second half, i.e. far quicker than the p.219 hold. So below ``comeback_peak`` the level
    steps every ``comeback_hold_weeks`` week(s); at/above it (truly new mileage) the slow
    ``hold_weeks`` rule applies. ``comeback_peak`` is normally the athlete's demonstrated peak
    (``p_history``); pass ``None`` for a pure base-build (no regained territory).

    An **already-based** athlete whose ``start`` is at/above ``peak`` simply holds at peak with
    recovery weeks. The final ``taper_weeks`` descend off the **achieved** peak.
    """
    n_weeks = max(1, n_weeks)
    taper_weeks = max(0, min(taper_weeks, n_weeks - 1))
    build_n = n_weeks - taper_weeks
    step = max(1, min(int(days_per_week), 10))  # Daniels p.219: +1 mi/session, +10 cap

    vols: list[float] = []
    level = min(float(start), float(peak))
    weeks_held = 0
    for i in range(build_n):
        wk = i + 1
        if down_week_every and wk % down_week_every == 0:
            vols.append(round(level * 0.8, 1))  # recovery week; does not advance the hold
            continue
        vols.append(round(level, 1))
        weeks_held += 1
        regaining = comeback_peak is not None and level < float(comeback_peak) - 0.05
        hold_target = max(1, comeback_hold_weeks) if regaining else hold_weeks
        if weeks_held >= hold_target and level < peak:
            level = min(level + step, peak)
            weeks_held = 0

    taper_base = max(vols) if vols else float(peak)  # taper off the volume actually reached
    for frac in _taper_fracs(taper_weeks):
        vols.append(round(taper_base * frac, 1))
    return vols[:n_weeks]


def volume_step_ups(vols: list[float]) -> list[bool]:
    """Mark weeks whose target rises above every prior week — a **mileage step-up**.

    Daniels Principle 6 / Accelerating Setbacks (p.36, fig 2.3) and Pfitzinger ch.3: don't
    stack a hard VO2max session on top of a week you're also raising volume. The generators
    use this to defer ``I`` work off step-up weeks (see ``daniels``/``pfitzinger``)."""
    ups = [False] * len(vols)
    running_max: float | None = None
    for i, v in enumerate(vols):
        if running_max is not None and v > running_max + 0.05:
            ups[i] = True
        running_max = v if running_max is None else max(running_max, v)
    return ups


def ramp_start(inputs) -> float:
    """Where the weekly-volume ramp begins. ``build_plan`` resolves ``reentry_start_mpw`` from
    readiness (a race-fit returner re-enters above an off-season ``w_now``); a direct generator
    call with no resolved start falls back to current volume."""
    return float(inputs.reentry_start_mpw or inputs.w_now)


def long_run_pace_s(inputs, easy_pace_s: int) -> int:
    """Pace used to convert the time-on-feet window into a long-run *distance*. Prefer the
    athlete's observed long-run pace (Strava) over the VDOT easy pace — runners often run
    long faster than the VDOT easy range, so this sizes the 2-3 h window to the distance they
    actually cover. VDOT still drives every *prescribed* pace (E/M/T/I)."""
    return int(inputs.observed_long_pace_s or easy_pace_s)


def needs_base_phase(inputs, first_week_target: float) -> bool:
    """sec.3b: week 1 must be runnable comfortably today. If current volume is well under
    the first week's target, the athlete needs a bridging base phase first."""
    return inputs.w_now + 1.0 < first_week_target


# --- sec.4 Long run --------------------------------------------------------------
@dataclass
class LongRun:
    time_cap_mi: float        # distance reachable in Daniels' 150-min anchor at easy pace
    share_mi: float           # 30%/25%-of-week distance
    recommended_mi: float
    window_cap_mi: float = 0.0      # distance reachable in the 3 h productive ceiling (Hanson p.66)
    time_on_feet_min: float = 0.0   # minutes the recommended long run takes at easy pace
    citations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def daniels_long_run(weekly_miles: float, easy_pace_s: float, marathon_build: bool = True) -> LongRun:
    """Long run length, governed by **time on feet** (sec.4).

    The lesser of: the time-on-feet ceiling, an 18-mi distance cap, and the 30%/25%-of-week
    share. The 18-mi ceiling is Daniels' 2Q program, where even high-mileage long runs are
    "the lesser of 18 miles and 130 min" (Table 14.3, p.237); without it the share/third
    rule overshoots at high volume (e.g. 68 mpw -> ~19-20 mi).

    The time ceiling differs by intent:

    * ``marathon_build=True`` (z2tc default) targets the **3 h upper bound** of Hanson's
      2–3 h productive window (p.66). This is the key correction for *slower* runners: at
      ~11:00/mi a 3 h cap is ~16 mi — the same time-on-feet stimulus a 7:30/mi runner gets
      from a 20-miler — instead of being clipped to ~13.6 mi by Daniels' conservative 150
      min. The prescription is held to ``min(window_cap, 18, max(share, 1/3 week))`` so it
      never becomes a disproportionate (boom-bust) fraction of a *supported* week.
    * ``marathon_build=False`` is Daniels' literal lesser-of using the 150-min anchor:
      ``min(time_cap_mi, 18, share_mi)``.

    The volume-too-low flag still keys off Daniels' 150-min anchor: if a full 2.5 h long run
    would exceed 1/3 of the week, weekly volume is the limiter, not time.
    """
    time_cap_mi = LONG_RUN_CAP_MIN * 60.0 / easy_pace_s          # Daniels 150-min anchor
    window_cap_mi = LONG_RUN_WINDOW_MIN[1] * 60.0 / easy_pace_s  # Hanson 3 h productive ceiling
    share_pct = 0.30 if weekly_miles <= 40 else 0.25            # Daniels p.64 tier
    share_mi = share_pct * weekly_miles
    third = weekly_miles / 3.0

    flags: list[str] = []
    if marathon_build:
        recommended = min(window_cap_mi, LONG_RUN_CAP_MI, max(share_mi, third))
        citations = ["hanson_long_run_window", "daniels_long_run"]
    else:
        recommended = min(time_cap_mi, LONG_RUN_CAP_MI, share_mi)
        citations = ["daniels_long_run"]

    if time_cap_mi > third + 0.05:
        flags.append(
            "volume too low: a 150-min long run would exceed 1/3 of the week; raise weekly volume"
        )
    return LongRun(
        time_cap_mi=round(time_cap_mi, 1),
        share_mi=round(share_mi, 1),
        recommended_mi=round(recommended, 1),
        window_cap_mi=round(window_cap_mi, 1),
        time_on_feet_min=round(recommended * easy_pace_s / 60.0, 1),
        citations=citations,
        flags=flags,
    )


def long_run_notes(peak_long_mi: float, easy_pace_s: float, citation_keys: list[str]) -> list[str]:
    """Athlete-facing rationale + book references for the peak long run, for ``TrainingPlan.notes``."""
    from . import citations as _cite

    time_min = peak_long_mi * easy_pace_s / 60.0
    notes = [_cite.long_run_rationale(peak_long_mi, time_min, LONG_RUN_WINDOW_MIN)]
    notes += [f"long-run cap — {_cite.get(k)}" for k in citation_keys]
    return notes


def pfitzinger_long_run(week_index: int, build_n: int, base_mi: float = 12.0, peak_mi: float = 20.0) -> float:
    """Pfitzinger long run (sec.4): build by *distance* to 20-22 mi, no time cap.

    p.257 ("a long run is any run of 16 miles or longer") is a labeling *definition* inside
    his 55-100 mpw schedules, **not a floor** — his lowest (≤55 mpw) schedule opens with ~12-mi
    long runs and grows them (p.285). So the ladder starts near 12 and ramps to ~20; it is not
    clamped up to 16."""
    if build_n <= 1:
        return peak_mi
    frac = min(1.0, max(0.0, (week_index - 1) / (build_n - 1)))
    return round(base_mi + (peak_mi - base_mi) * frac, 1)


# --- sec.5 Single-session caps (Daniels fig. 4.1, p.62 + M-pace text p.65) --------
def session_caps(weekly_miles: float, mp_s: int | None = None) -> dict[str, float]:
    """Upper bound (miles) on the quality volume in one session.

    Straight from Daniels' intensity table (figure 4.1, p.62): T is 10% of weekly
    miles; I is the lesser of 10 km and 8% of the week; R is the lesser of 5 mi and 5%
    of the week. The marathon-pace cap is the lesser of 18 mi and 20% of the week
    (p.62 gives a 15-20% band; p.65 states 20%), plus the 110-minute M-pace ceiling
    when ``mp_s`` is supplied. (The 15-mi T guard rarely binds below ~150 mpw.)
    """
    m_cap = min(18.0, 0.20 * weekly_miles)
    if mp_s:
        m_cap = min(m_cap, LONG_RUN_CAP_MIN_M * 60.0 / mp_s)
    return {
        "T": round(min(0.10 * weekly_miles, 15.0), 1),
        "M": round(m_cap, 1),
        "I": round(min(0.08 * weekly_miles, TEN_K_MILES), 1),
        "R": round(min(0.05 * weekly_miles, 5.0), 1),
    }


# --- sec.6 Recovery after racing -------------------------------------------------
def recovery_days_after_race(distance_m: float) -> int:
    """1 easy day per 3,000 m of race distance (sec.6): ~3 after 10K, 7 after a half,
    14 after a marathon."""
    return int(distance_m // 3000)


# --- Week assembly (shared by both generators) -----------------------------------
# Club long runs are Saturday (Zone 2 Track Club). Quality work stays midweek (Tue/Wed).
LONG_RUN_DAY = "Sat"

RUN_DAYS_BY_COUNT = {
    3: ["Tue", "Thu", "Sat"],
    4: ["Tue", "Wed", "Fri", "Sat"],
    5: ["Mon", "Tue", "Wed", "Fri", "Sat"],
    6: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    7: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}


def run_days(days_per_week: int) -> list[str]:
    return RUN_DAYS_BY_COUNT.get(max(3, min(7, days_per_week)), RUN_DAYS_BY_COUNT[4])


def easy_pace(paces: dict) -> tuple[int, str]:
    """Midpoint of the Easy/Long range, in seconds and formatted (used for long-run
    time-cap math and easy days)."""
    lo, hi = paces.get("easy_low_s"), paces.get("easy_high_s")
    if lo is None or hi is None:
        secs = lo or hi or 540
    else:
        secs = round((lo + hi) / 2)
    m, s = divmod(secs, 60)
    return secs, f"{m}:{s:02d}"


def easy_workout(miles: float, pace_s: int, pace_str: str, *, strides: bool = False) -> Workout:
    flags = ["6-8 x strides"] if strides else []
    label = "Easy run + strides" if strides else "Easy run"
    return Workout(WorkoutKind.EASY, label, distance_mi=round(miles, 1), pace=pace_str, pace_s=pace_s, flags=flags)


TEMPO_MAX_MIN = 20  # Daniels p.67: a single steady tempo run is ~20 min; beyond that, cruise intervals


def threshold_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """Threshold session bounded by the 10%-of-week T cap (``cap_mi``).

    Daniels (p.67-68): a steady tempo is ~20 min at T pace; accumulating more T volume
    means breaking the session into **cruise intervals** (T bouts with short jog rests),
    not running a longer continuous tempo. Warm-up/cool-down (~3 mi) sit outside the cap.
    """
    work = max(3.0, round(cap_mi, 1))
    tempo_max_mi = TEMPO_MAX_MIN * 60.0 / pace_s
    if work <= tempo_max_mi + 0.05:
        seg = Segment(reps=1, pace_label="T", pace_s=pace_s, distance_m=round(work * METERS_PER_MILE))
        label = f"Tempo: {work:g} mi @ T ({pace_str}/mi) + wu/cd"
    else:
        reps = max(2, round(work))  # ~1-mile cruise intervals
        per = round(work / reps, 1)
        seg = Segment(reps=reps, pace_label="T", pace_s=pace_s, distance_m=round(per * METERS_PER_MILE), recovery="60 s jog")
        label = f"Cruise intervals: {reps} x {per:g} mi @ T ({pace_str}/mi), 60 s jog + wu/cd"
    return Workout(
        WorkoutKind.THRESHOLD,
        label,
        distance_mi=round(work + 3.0, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def interval_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    reps = max(4, round(cap_mi * METERS_PER_MILE / 1000.0))
    seg = Segment(reps=reps, pace_label="I", pace_s=pace_s, distance_m=1000, recovery="equal-time jog")
    work_mi = reps * 1000.0 / METERS_PER_MILE
    return Workout(
        WorkoutKind.INTERVAL,
        f"VO2max: {reps} x 1000 m @ I ({pace_str}/mi), equal-time jog + wu/cd",
        distance_mi=round(work_mi + 3.0, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def marathon_q1_workout(
    total_mi: float,
    m_cap: float,
    mp_s: int,
    mp_str: str,
    t_s: int,
    t_str: str,
    easy_pace_s: int,
    easy_str: str,
) -> Workout:
    """Daniels 2Q **Q1** session (ch.14, Table 14.3): one *nonstop* long run that blends
    E → M → (T surge) → M → E, e.g. "3 E + 4 M + 1 T + 1 M + 2 E".

    The marathon-pace volume is bounded by ``m_cap`` (``session_caps["M"]`` = 18 mi / 20%
    week / 110 min); a single 1-mi T surge is inserted on long enough days; the rest is easy
    running as warm-up/cool-down. This is a quality session (`MARATHON_PACE`), so the long run
    stays one of the week's two Q sessions rather than being split into separate L and M days.
    """
    total = round(total_mi, 1)
    m_total = round(min(m_cap, max(2.0, total * 0.5)), 1)
    t_mi = 1.0 if total >= 10 else 0.0
    m_back = 1.0 if (t_mi and m_total >= 4.0) else 0.0
    m_front = round(m_total - m_back, 1)
    easy_total = round(max(2.0, total - (m_front + t_mi + m_back)), 1)
    wu = round(easy_total * 0.6, 1)
    cd = round(max(0.0, easy_total - wu), 1)

    segs = [Segment(reps=1, pace_label="E", pace_s=easy_pace_s, distance_m=round(wu * METERS_PER_MILE))]
    parts = [f"{wu:g} E"]
    segs.append(Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(m_front * METERS_PER_MILE)))
    parts.append(f"{m_front:g} M")
    if t_mi:
        segs.append(Segment(reps=1, pace_label="T", pace_s=t_s, distance_m=round(t_mi * METERS_PER_MILE)))
        parts.append(f"{t_mi:g} T")
    if m_back:
        segs.append(Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(m_back * METERS_PER_MILE)))
        parts.append(f"{m_back:g} M")
    segs.append(Segment(reps=1, pace_label="E", pace_s=easy_pace_s, distance_m=round(cd * METERS_PER_MILE)))
    parts.append(f"{cd:g} E")

    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Q1 long run {total:g} mi (nonstop): " + " + ".join(parts) + f" (M @ {mp_str}/mi)",
        distance_mi=total,
        pace=mp_str,
        pace_s=mp_s,
        segments=segs,
    )


def mp_long_run(total_mi: float, mp_block_mi: float, mp_s: int, mp_str: str, easy_pace_s: int) -> Workout:
    """A long run with a marathon-pace finishing block (counts as a quality session).

    Used by the Pfitzinger generator, whose marathon-pace long run is a steady run with a MP
    portion (ch.7) rather than Daniels' alternating E/M/T blend — see ``marathon_q1_workout``."""
    block = round(min(mp_block_mi, max(2.0, total_mi * 0.4)), 1)
    seg = Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(block * METERS_PER_MILE))
    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Long run {total_mi:g} mi w/ {block:g} mi @ MP ({mp_str}/mi) finish",
        distance_mi=round(total_mi, 1),
        pace=mp_str,
        pace_s=mp_s,
        segments=[seg],
    )


def long_run_easy(total_mi: float, easy_pace_s: int, easy_str: str) -> Workout:
    return Workout(
        WorkoutKind.LONG,
        f"Long run {total_mi:g} mi @ Easy ({easy_str}/mi)",
        distance_mi=round(total_mi, 1),
        pace=easy_str,
        pace_s=easy_pace_s,
    )


def medium_long_run(total_mi: float, easy_pace_s: int, easy_str: str) -> Workout:
    return Workout(
        WorkoutKind.MEDIUM_LONG,
        f"Medium-long run {total_mi:g} mi",
        distance_mi=round(total_mi, 1),
        pace=easy_str,
        pace_s=easy_pace_s,
    )


def rest_day() -> Workout:
    return Workout(WorkoutKind.REST, "Rest")


def cross_training_day(minutes: int = 60, *, label: str | None = None) -> Workout:
    """Scheduled non-running aerobic work (Higdon Mon/Sun cross); ``distance_mi`` stays None."""
    return Workout(
        WorkoutKind.CROSS,
        label or f"Cross training ({minutes} min)",
        distance_mi=None,
        duration_min=minutes,
    )


def assemble_week(
    days_per_week: int,
    target_mi: float,
    fixed: dict[str, Workout],
    easy_pace_s: int,
    easy_str: str,
    stride_days: int = 2,
) -> list[PlannedDay]:
    """Place ``fixed`` workouts on their days and fill the remaining run days with easy
    miles so the week sums to ~``target_mi``. Strides go on the first ``stride_days``
    easy days."""
    rdays = run_days(days_per_week)
    fixed_miles = sum((w.distance_mi or 0.0) for w in fixed.values())
    easy_days = [d for d in rdays if d not in fixed]
    remaining = max(0.0, target_mi - fixed_miles)
    per = remaining / len(easy_days) if easy_days else 0.0

    days: list[PlannedDay] = []
    strides_left = stride_days
    for d in DAY_NAMES:
        if d in fixed:
            days.append(PlannedDay(d, fixed[d]))
        elif d in easy_days:
            use_strides = strides_left > 0
            if use_strides:
                strides_left -= 1
            days.append(PlannedDay(d, easy_workout(per, easy_pace_s, easy_str, strides=use_strides)))
        else:
            days.append(PlannedDay(d, rest_day()))
    return days


def adapt_training_plan(
    plan: TrainingPlan,
    inputs: AthleteInputs,
    *,
    native_run_days: int | None = None,
    entry_week1_mpw: float | None = None,
) -> TrainingPlan:
    """Attach citation-backed coach flags when athlete parameters diverge from a book program.

    Verbatim grids stay unchanged; this layer only documents mismatches (block length, day
    count, entry base). Engines call this as the final step before returning a ``TrainingPlan``.
    """
    from dataclasses import replace

    flags = list(plan.flags)
    if native_run_days is not None and inputs.days_per_week < native_run_days:
        flags.append(
            f"adapt_schedule: athlete runs {inputs.days_per_week} d/wk vs program native "
            f"{native_run_days} run days — review day mapping; cumulative-fatigue layouts need the book frequency"
        )
    if entry_week1_mpw is not None and inputs.w_now + 1.05 < entry_week1_mpw:
        flags.append(
            f"adapt_schedule: below program week-1 entry (~{entry_week1_mpw:g} mpw) at w_now "
            f"{inputs.w_now:g} mpw — build base first (cf. Pfitzinger p.285; Higdon p.46)"
        )
    if inputs.block_weeks != 18:
        flags.append(
            f"adapt_schedule: block_weeks={inputs.block_weeks} vs canonical 18-wk book grid — "
            "manual compress/extend of early base vs taper not auto-applied"
        )
    return replace(plan, flags=flags)


# Plan doc / architecture name for the adaptation layer.
adapt_schedule = adapt_training_plan


def append_post_marathon_recovery(plan: TrainingPlan, easy_pace_s: int, easy_str: str) -> TrainingPlan:
    """Five easy weeks after the marathon (Pfitzinger mesocycle 5, p.290) — not part of the build."""
    from dataclasses import replace

    last_idx = plan.weeks[-1].index if plan.weeks else 0
    extra: list[PlannedWeek] = []
    targets = (3.0, 6.0, 10.0, 14.0, 18.0)
    for j, target in enumerate(targets, start=1):
        wk = last_idx + j
        days = assemble_week(5, target, {}, easy_pace_s, easy_str, stride_days=0)
        extra.append(
            PlannedWeek(
                index=wk,
                phase="Recovery",
                label=f"Post-marathon recovery wk{j}/5 (p.290)",
                target_miles=target,
                is_down_week=False,
                days=days,
                flags=["post_race_recovery_block"],
            )
        )
    flags = list(plan.flags) + [
        "post-marathon recovery weeks appended — not part of the marathon build (Pfitzinger p.290)"
    ]
    return replace(plan, weeks=list(plan.weeks) + extra, flags=flags)
