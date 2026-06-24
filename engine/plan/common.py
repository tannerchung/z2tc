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


def taper_long_fracs(non_race_taper_weeks: int) -> list[float]:
    """Fractions of the **peak long run** for the non-race taper weeks (sec.4 taper). The long
    run must step down through the taper — it should not sit near peak two weeks out. Daniels
    ch.14 / Pfitzinger ch.7: shorten the long run progressively, with the last one clearly
    reduced before race week (which carries no long run, only a shakeout + the marathon)."""
    k = max(0, non_race_taper_weeks)
    if k <= 0:
        return []
    if k == 1:
        return [0.60]
    if k == 2:
        return [0.75, 0.50]
    return [round(0.80 - 0.45 * i / (k - 1), 2) for i in range(k)]


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
    # Daniels strides (p.133): light, quick 20-sec runs (not sprints), 60 s rest — added to
    # easy days to build economy; they do NOT make the day a quality session.
    flags = ["6 x 20 sec strides"] if strides else []
    label = "Easy run, then 6 x 20 sec strides to finish" if strides else "Easy run"
    return Workout(WorkoutKind.EASY, label, distance_mi=round(miles, 1), pace=pace_str, pace_s=pace_s, flags=flags)


TEMPO_MAX_MIN = 20  # Daniels p.67: a single steady tempo run is ~20 min; beyond that, cruise intervals
WARMUP_MI = 1.5     # easy miles before a quality main set
COOLDOWN_MI = 1.5   # easy miles after a quality main set


def _prescribe(name: str, work: str) -> str:
    """Coach-prescriptive label: lead with the workout name, then the exact
    warm-up → main set → cool-down sequence a runner executes in order."""
    return f"{name}: {WARMUP_MI:g} mi easy warm-up \u2192 {work} \u2192 {COOLDOWN_MI:g} mi easy cool-down"


def threshold_workout(
    cap_mi: float, pace_s: int, pace_str: str, *, style: str = "auto", rep_mi: float = 1.0
) -> Workout:
    """Threshold session bounded by the 10%-of-week T cap (``cap_mi``).

    Daniels (p.67-68): a steady tempo is ~20 min at T pace; accumulating more T volume
    means breaking the session into **cruise intervals** (T bouts with short jog rests),
    not running a longer continuous tempo. Warm-up/cool-down (~3 mi) sit outside the cap.

    ``style`` lets the generator vary the format week to week without changing the stimulus:
    ``"tempo"`` forces a single continuous tempo (capped at ~20 min), ``"cruise"`` forces
    intervals, ``"auto"`` picks by volume. ``rep_mi`` sets the cruise-interval length
    (1.0 = mile repeats, 0.5 = "broken-T" half-mile repeats).
    """
    work = max(3.0, round(cap_mi, 1))
    tempo_max_mi = TEMPO_MAX_MIN * 60.0 / pace_s
    use_tempo = style == "tempo" or (style == "auto" and work <= tempo_max_mi + 0.05)
    if use_tempo:
        steady = round(min(work, tempo_max_mi), 1) if style == "tempo" else round(work, 1)
        seg = Segment(reps=1, pace_label="T", pace_s=pace_s, distance_m=round(steady * METERS_PER_MILE))
        label = _prescribe("Tempo run", f"{steady:g} mi @ Threshold ({pace_str}/mi)")
        total = steady
    else:
        reps = max(2, round(work / max(0.25, rep_mi)))
        per = round(work / reps, 1)
        seg = Segment(reps=reps, pace_label="T", pace_s=pace_s, distance_m=round(per * METERS_PER_MILE), recovery="60 s jog")
        label = _prescribe("Cruise intervals", f"{reps} x {per:g} mi @ Threshold ({pace_str}/mi) w/ 60 s jog")
        total = work
    return Workout(
        WorkoutKind.THRESHOLD,
        label,
        distance_mi=round(total + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def interval_workout(cap_mi: float, pace_s: int, pace_str: str, *, rep_m: int = 1000) -> Workout:
    """VO2max (Daniels I) reps at ``rep_m`` metres with equal-time jog recovery."""
    reps = max(4, round(cap_mi * METERS_PER_MILE / rep_m))
    seg = Segment(reps=reps, pace_label="I", pace_s=pace_s, distance_m=rep_m, recovery="equal-time jog")
    work_mi = reps * rep_m / METERS_PER_MILE
    return Workout(
        WorkoutKind.INTERVAL,
        _prescribe("VO2max intervals", f"{reps} x {rep_m} m @ VO2max pace ({pace_str}/mi) w/ equal-time jog"),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def interval_ladder_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """VO2max **ladder** (Daniels I): 400-800-1200-800-400 m at I pace, equal-time jog.

    A single ~3.6 km ladder is a self-contained VO2max session; ``cap_mi`` is accepted for a
    uniform call signature but the ladder shape is fixed (the wu/cd absorbs cap differences)."""
    ladder = [400, 800, 1200, 800, 400]
    segs = [
        Segment(reps=1, pace_label="I", pace_s=pace_s, distance_m=d, recovery="equal-time jog")
        for d in ladder
    ]
    work_mi = sum(ladder) / METERS_PER_MILE
    return Workout(
        WorkoutKind.INTERVAL,
        _prescribe(
            "VO2max pyramid",
            f"400-800-1200-800-400 m @ VO2max pace ({pace_str}/mi) w/ equal-time jog",
        ),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=segs,
    )


def rep_workout(cap_mi: float, pace_s: int, pace_str: str, *, rep_m: int = 400) -> Workout:
    """Repetition (Daniels R) session: short fast ``rep_m``-metre reps at R pace, full recovery.

    R work develops speed/economy; it is light on volume (``session_caps["R"]`` ≈ 5% of the
    week) and uses full (≈equal-distance jog) recovery rather than the short I jog. ``rep_m``
    sets the rep length (400 m default; 200 m for pure turnover, Daniels p.135)."""
    floor = 6 if rep_m >= 400 else 8
    reps = max(floor, round(cap_mi * METERS_PER_MILE / rep_m))
    seg = Segment(reps=reps, pace_label="R", pace_s=pace_s, distance_m=rep_m, recovery=f"full ({rep_m} m jog)")
    work_mi = reps * rep_m / METERS_PER_MILE
    return Workout(
        WorkoutKind.REP,
        _prescribe("Speed reps", f"{reps} x {rep_m} m @ Rep pace ({pace_str}/mi) w/ full {rep_m} m jog"),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def rolling_reps_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """Rolling 400s (Runna): 400 m reps at Rep pace with only a short 200 m jog float — a
    continuous, rhythm-focused turnover set (shorter recovery than ``rep_workout``'s full jog)."""
    reps = max(6, round(cap_mi * METERS_PER_MILE / 400.0))
    seg = Segment(reps=reps, pace_label="R", pace_s=pace_s, distance_m=400, recovery="200 m jog (continuous)")
    work_mi = reps * 400.0 / METERS_PER_MILE
    return Workout(
        WorkoutKind.REP,
        _prescribe("Rolling 400s", f"{reps} x 400 m @ Rep pace ({pace_str}/mi) w/ 200 m jog float"),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=[seg],
    )


def drop_set_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """VO2max **drop set** (Runna): a single 1000-800-600-400-200 m descending ladder at I pace,
    equal-time jog. Like ``descending_intervals_workout`` but shorter/sharper — finishes fast on
    tired legs. ``cap_mi`` accepted for a uniform signature; the set shape is fixed."""
    ladder = [1000, 800, 600, 400, 200]
    segs = [
        Segment(reps=1, pace_label="I", pace_s=pace_s, distance_m=d, recovery="equal-time jog")
        for d in ladder
    ]
    work_mi = sum(ladder) / METERS_PER_MILE
    return Workout(
        WorkoutKind.INTERVAL,
        _prescribe("Drop set", f"1000-800-600-400-200 m @ VO2max pace ({pace_str}/mi) w/ equal-time jog"),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=segs,
    )


def threshold_ladder_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """Threshold **ladder** (Runna "Tempo 2-1-1"): descending threshold blocks with 60 s jogs —
    a long block then shorter ones, same comfortably-hard T effort. Total T volume = ``cap_mi``
    (the 10%-of-week T cap), split 50/25/25 (each block ≥ 0.5 mi)."""
    a = max(0.5, round(cap_mi * 0.5, 1))
    b = max(0.5, round(cap_mi * 0.25, 1))
    c = max(0.5, round(cap_mi - a - b, 1))
    segs = [
        Segment(reps=1, pace_label="T", pace_s=pace_s, distance_m=round(d * METERS_PER_MILE), recovery="60 s jog")
        for d in (a, b, c)
    ]
    return Workout(
        WorkoutKind.THRESHOLD,
        _prescribe("Threshold ladder", f"{a:g} + {b:g} + {c:g} mi @ Threshold ({pace_str}/mi) w/ 60 s jog (descending)"),
        distance_mi=round(a + b + c + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=segs,
    )


def mp_reps_workout(cap_mi: float, mp_s: int, mp_str: str, *, rep_mi: float = 0.5) -> Workout:
    """Goal-pace reps (Runna "Race Pace Practice Half Miles"): short reps at marathon pace with a
    60 s jog — a low-fatigue way to rehearse race rhythm, ideal in the taper / race week. Volume
    is bounded by ``cap_mi`` (a trimmed M cap in the taper)."""
    reps = max(3, round(cap_mi / max(0.25, rep_mi)))
    seg = Segment(reps=reps, pace_label="M", pace_s=mp_s, distance_m=round(rep_mi * METERS_PER_MILE), recovery="60 s jog")
    work_mi = reps * rep_mi
    return Workout(
        WorkoutKind.MARATHON_PACE,
        _prescribe("Race-pace reps", f"{reps} x {rep_mi:g} mi @ MP ({mp_str}/mi) w/ 60 s jog"),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=mp_str,
        pace_s=mp_s,
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
        f"Marathon long run {total:g} mi (nonstop): " + " + ".join(parts) + f" (M @ {mp_str}/mi)",
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


def over_under_workout(cap_mi: float, t_s: int, t_str: str, mp_s: int, mp_str: str) -> Workout:
    """Threshold "over/unders": continuous 0.5 mi reps alternating Threshold (the *over*) with
    marathon pace (the *under*). Same lactate-clearance stimulus as cruise intervals, but the
    float down to MP — instead of a jog — trains rhythm changes at race-adjacent paces (a Runna
    staple, consistent with Daniels' T work). Each rep banks 0.5 mi of T, so the T volume sits
    near half the 10% T cap (the MP floats are easier than a tempo, so less T is appropriate)."""
    overs = max(3, round(cap_mi))
    segs: list[Segment] = []
    for _ in range(overs):
        segs.append(Segment(reps=1, pace_label="T", pace_s=t_s, distance_m=round(0.5 * METERS_PER_MILE)))
        segs.append(Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(0.5 * METERS_PER_MILE)))
    work = overs * 1.0
    return Workout(
        WorkoutKind.THRESHOLD,
        _prescribe(
            "Over/unders",
            f"{overs} x (0.5 mi @ Threshold ({t_str}/mi) / 0.5 mi @ MP ({mp_str}/mi)) nonstop",
        ),
        distance_mi=round(work + WARMUP_MI + COOLDOWN_MI, 1),
        pace=t_str,
        pace_s=t_s,
        segments=segs,
    )


def descending_intervals_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    """VO2max **descending** set: 1200-1000-800-600-400 m at I pace, equal-time jog. Same VO2max
    stimulus as straight 1000s, but the shortening reps let pace stay honest as fatigue builds.
    ``cap_mi`` is accepted for a uniform signature; the set shape is fixed (wu/cd absorbs caps)."""
    ladder = [1200, 1000, 800, 600, 400]
    segs = [
        Segment(reps=1, pace_label="I", pace_s=pace_s, distance_m=d, recovery="equal-time jog")
        for d in ladder
    ]
    work_mi = sum(ladder) / METERS_PER_MILE
    return Workout(
        WorkoutKind.INTERVAL,
        _prescribe(
            "Descending intervals",
            f"1200-1000-800-600-400 m @ VO2max pace ({pace_str}/mi) w/ equal-time jog",
        ),
        distance_mi=round(work_mi + WARMUP_MI + COOLDOWN_MI, 1),
        pace=pace_str,
        pace_s=pace_s,
        segments=segs,
    )


def progression_long_run(total_mi: float, easy_s: int, easy_str: str, mp_s: int, mp_str: str) -> Workout:
    """Thirds progression long run (Humphrey/Daniels-friendly): easy → steady → marathon pace,
    nonstop. Teaches pacing discipline and finishing strong on tired legs with less injury risk
    than a sharp fast finish. Steady is the midpoint between Easy and MP."""
    total = round(total_mi, 1)
    a = round(total / 3.0, 1)
    c = round(total - 2 * a, 1)
    steady_s = round((easy_s + mp_s) / 2)
    segs = [
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(a * METERS_PER_MILE)),
        Segment(reps=1, pace_label="steady", pace_s=steady_s, distance_m=round(a * METERS_PER_MILE)),
        Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(c * METERS_PER_MILE)),
    ]
    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Progression long run {total:g} mi (nonstop): {a:g} E + {a:g} steady + {c:g} M (M @ {mp_str}/mi)",
        distance_mi=total,
        pace=mp_str,
        pace_s=mp_s,
        segments=segs,
    )


def fast_finish_long_run(
    total_mi: float, finish_cap_mi: float, easy_s: int, easy_str: str, mp_s: int, mp_str: str
) -> Workout:
    """Mostly-easy long run closed out at marathon pace (the final block). Builds late-race grit;
    kept controlled (finish at MP, not faster) to protect the next week. The MP close is bounded
    by the M cap so it never becomes a disproportionate share of the run."""
    total = round(total_mi, 1)
    finish = round(min(finish_cap_mi, max(2.0, total * 0.4)), 1)
    easy = round(total - finish, 1)
    segs = [
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(easy * METERS_PER_MILE)),
        Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(finish * METERS_PER_MILE)),
    ]
    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Fast-finish long run {total:g} mi (nonstop): {easy:g} E + {finish:g} M (M @ {mp_str}/mi)",
        distance_mi=total,
        pace=mp_str,
        pace_s=mp_s,
        segments=segs,
    )


def mp_blocks_long_run(
    total_mi: float, m_cap: float, mp_s: int, mp_str: str, easy_s: int, easy_str: str
) -> Workout:
    """Long run with two marathon-pace blocks split by an easy float (the SF-marathon / Runna
    "MP blocks"). Race-rhythm + fueling rehearsal; the broken structure banks more MP volume than
    a single sustained block. Total MP is bounded by the M cap (18 mi / 20% week / 110 min)."""
    total = round(total_mi, 1)
    block = round(min(m_cap / 2.0, max(2.0, total * 0.25)), 1)
    rec = 1.0
    easy_total = round(max(2.0, total - 2 * block - rec), 1)
    wu = round(easy_total * 0.5, 1)
    cd = round(easy_total - wu, 1)
    segs = [
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(wu * METERS_PER_MILE)),
        Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(block * METERS_PER_MILE)),
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(rec * METERS_PER_MILE)),
        Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(block * METERS_PER_MILE)),
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(cd * METERS_PER_MILE)),
    ]
    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Marathon-pace blocks {total:g} mi (nonstop): {wu:g} E + {block:g} M + {rec:g} E + "
        f"{block:g} M + {cd:g} E (M @ {mp_str}/mi)",
        distance_mi=total,
        pace=mp_str,
        pace_s=mp_s,
        segments=segs,
    )


def race_practice_long_run(
    total_mi: float, m_cap: float, mp_s: int, mp_str: str, easy_s: int, easy_str: str
) -> Workout:
    """Dress-rehearsal long run: a short easy warm-up into one **sustained** marathon-pace block,
    then a short easy close (Runna "Race Practice Long Run"; Pfitzinger's dedicated marathon-pace
    run, ch.5). This is the block's most race-specific session — rehearse goal pace, fueling and
    kit on tired-but-not-trashed legs. The MP block is the longest single one of the build, bounded
    by the M cap (18 mi / 20% week / 110 min)."""
    total = round(total_mi, 1)
    block = round(min(m_cap, max(4.0, total - 3.0)), 1)
    rest = round(total - block, 1)
    wu = round(rest * 0.6, 1)
    cd = round(max(0.0, rest - wu), 1)
    segs = [
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(wu * METERS_PER_MILE)),
        Segment(reps=1, pace_label="M", pace_s=mp_s, distance_m=round(block * METERS_PER_MILE)),
        Segment(reps=1, pace_label="E", pace_s=easy_s, distance_m=round(cd * METERS_PER_MILE)),
    ]
    return Workout(
        WorkoutKind.MARATHON_PACE,
        f"Race-practice long run {total:g} mi (nonstop): {wu:g} E + {block:g} M + {cd:g} E (M @ {mp_str}/mi)",
        distance_mi=total,
        pace=mp_str,
        pace_s=mp_s,
        segments=segs,
    )


def long_run_easy(total_mi: float, easy_pace_s: int, easy_str: str) -> Workout:
    return Workout(
        WorkoutKind.LONG,
        f"Long run {total_mi:g} mi @ Easy ({easy_str}/mi)",
        distance_mi=round(total_mi, 1),
        pace=easy_str,
        pace_s=easy_pace_s,
    )


def long_run_fartlek(total_mi: float, easy_pace_s: int, easy_str: str) -> Workout:
    """Aerobic long run with light fartlek surges sprinkled in (Humphrey "Long Run w/ Fartlek").
    Stays an easy/long-effort day — the brief surges (~1 min, ~10K effort) break up the run and
    add a touch of turnover without making it a true quality session. Surge count scales with
    distance (~one per 1.5 mi)."""
    surges = max(4, round(total_mi / 1.5))
    return Workout(
        WorkoutKind.LONG,
        f"Long run w/ fartlek {total_mi:g} mi @ Easy ({easy_str}/mi) + {surges} x 1 min surges (~10K effort)",
        distance_mi=round(total_mi, 1),
        pace=easy_str,
        pace_s=easy_pace_s,
        flags=[f"{surges} x 1 min fartlek surges"],
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


def shakeout_workout(miles: float, easy_pace_s: int, easy_str: str) -> Workout:
    """Day-before-race opener: a very short, very easy jog with a few strides to stay loose
    without adding fatigue (standard marathon-week practice; Pfitzinger race-week p.108)."""
    return Workout(
        WorkoutKind.EASY,
        f"Shakeout: {miles:g} mi very easy + 4 x 20 sec strides (race tomorrow — stay loose)",
        distance_mi=round(miles, 1),
        pace=easy_str,
        pace_s=easy_pace_s,
        flags=["4 x 20 sec strides"],
    )


def race_week_days(
    days_per_week: int,
    race: Workout,
    easy_pace_s: int,
    easy_str: str,
    race_day: str = LONG_RUN_DAY,
) -> list[PlannedDay]:
    """Marathon week (sec.3e). The race dominates volume, so this week is **not** filled to a
    weekly mileage target like the others. Structure: a few short easy runs early in the week, a
    **day-before shakeout** with strides, the race on its actual weekday, two days out left as
    rest, and rest on the remaining days (Daniels ch.14 taper; Pfitzinger race week, p.108).

    ``race_day`` is the race's real day of week (e.g. ``"Sun"`` for a Sunday marathon). The club
    trains its long runs on Saturday, but the marathon itself — and its day-before shakeout — must
    land on the actual race weekday, so a Sunday race shakes out Saturday, not Friday."""
    workouts: dict[str, Workout] = {d: rest_day() for d in DAY_NAMES}
    workouts[race_day] = race
    ri = DAY_NAMES.index(race_day)
    day_before = DAY_NAMES[ri - 1] if ri > 0 else None
    two_before = DAY_NAMES[ri - 2] if ri >= 2 else None
    if day_before:
        workouts[day_before] = shakeout_workout(2.0, easy_pace_s, easy_str)

    # Keep the marathon week deliberately light: only (days_per_week - 3) short easy runs on top
    # of the day-before shakeout and the race. The day two out stays rest. Easy days are taken
    # from the usual midweek priority, never colliding with the race / shakeout / two-out rest.
    reserved = {race_day, day_before, two_before}
    n_easy = max(1, days_per_week - 3)
    # Easy runs must fall *before* the race within the week — never after it (so an early-week
    # race, e.g. a Monday, simply carries fewer/no easy days; those sit in the prior week).
    easy_days = [
        d for d in ["Wed", "Tue", "Mon", "Thu"]
        if d not in reserved and DAY_NAMES.index(d) < ri
    ][:n_easy]
    lengths = [4.0, 3.0, 3.0, 3.0]
    for day, miles in zip(easy_days, lengths):
        workouts[day] = easy_workout(miles, easy_pace_s, easy_str, strides=(day == easy_days[0]))

    return [PlannedDay(d, workouts[d]) for d in DAY_NAMES]


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
    stride_days: int = 1,
    max_easy_mi: float | None = None,
) -> list[PlannedDay]:
    """Place ``fixed`` workouts on their days and fill the remaining run days with easy
    miles so the week sums to ~``target_mi``. Strides go on the first ``stride_days``
    easy days. ``max_easy_mi`` caps each easy day (used in the taper so a shortened long run
    sheds volume instead of ballooning the midweek easy runs)."""
    rdays = run_days(days_per_week)
    fixed_miles = sum((w.distance_mi or 0.0) for w in fixed.values())
    easy_days = [d for d in rdays if d not in fixed]
    remaining = max(0.0, target_mi - fixed_miles)
    per = remaining / len(easy_days) if easy_days else 0.0
    if max_easy_mi is not None:
        per = min(per, max_easy_mi)

    days: list[PlannedDay] = []
    # House default follows Hanson: easy days stay easy (his SOS speed work carries the fast running,
    # easy/recovery days are kept truly easy), so we add just one light economy stride session per
    # week rather than peppering most easy runs the way a literal Daniels Phase I would (p.122/126).
    # The clamp also guarantees at least one plain easy/recovery run remains.
    strides_left = min(stride_days, max(0, len(easy_days) - 1))
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
