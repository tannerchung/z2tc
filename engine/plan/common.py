"""Deterministic building blocks shared by both generators.

Every rule here is a direct transcription of the project's Training Plan Formula
Reference (sections cited inline as e.g. "sec.4"). Pure arithmetic, no IO. The
generators compose these; the numbers come out the same way every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import DAY_NAMES, PlannedDay, Segment, Workout, WorkoutKind

METERS_PER_MILE = 1609.344
MARATHON_MILES = 42195.0 / METERS_PER_MILE  # ~26.219
TEN_K_MILES = 10000.0 / METERS_PER_MILE     # ~6.214
LONG_RUN_CAP_MIN = 150                      # Daniels' hard time cap (sec.4)

DANIELS = "daniels"
PFITZINGER = "pfitzinger"


# --- sec.1 Method assignment -----------------------------------------------------
def assign_method(inputs) -> str:
    """Pfitzinger needs an established base and 5+ days; otherwise Daniels. A forced
    ``inputs.method`` always wins."""
    if inputs.method in (DANIELS, PFITZINGER):
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
    """Peak weekly volume (sec.3a): demonstrated capacity, never set down from history by
    an off-season low. We don't inflate beyond history (injury-safe, deterministic)."""
    return float(max(inputs.p_history, inputs.w_now))


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
    down_week_every: int = 4,
) -> list[float]:
    """Target weekly mileage for each week of the block (sec.3b-3e).

    The build phase ramps from ``start`` toward ``peak`` adding at most
    ``days_per_week`` miles per week (sec.3c: <=1 mi per session), with every 4th week a
    step-back to ~80% of the current level. The final ``taper_weeks`` descend off peak.
    """
    n_weeks = max(1, n_weeks)
    taper_weeks = max(0, min(taper_weeks, n_weeks - 1))
    build_n = n_weeks - taper_weeks

    vols: list[float] = []
    level = float(start)
    for i in range(build_n):
        wk = i + 1
        if down_week_every and wk % down_week_every == 0:
            vols.append(round(min(level, peak) * 0.8, 1))
        else:
            vols.append(round(min(level, peak), 1))
            level = min(level + days_per_week, peak)

    for frac in _taper_fracs(taper_weeks):
        vols.append(round(peak * frac, 1))
    return vols[:n_weeks]


def needs_base_phase(inputs, first_week_target: float) -> bool:
    """sec.3b: week 1 must be runnable comfortably today. If current volume is well under
    the first week's target, the athlete needs a bridging base phase first."""
    return inputs.w_now + 1.0 < first_week_target


# --- sec.4 Long run --------------------------------------------------------------
@dataclass
class LongRun:
    time_cap_mi: float   # distance reachable in 150 min at easy pace
    share_mi: float      # 30%/25%-of-week distance
    recommended_mi: float
    flags: list[str] = field(default_factory=list)


def daniels_long_run(weekly_miles: float, easy_pace_s: float, marathon_build: bool = True) -> LongRun:
    """Daniels rule (sec.4): long run is the lesser of the 150-minute cap and the
    30%/25%-of-week share (``share_mi``).

    **House rule (marathon_build=True):** when weekly volume is high enough that
    ``share_mi`` exceeds one-third of the week, we still cap the *prescription* at
    ``min(time_cap_mi, max(share_mi, third))`` so the long run does not exceed ~1/3 of
    the week — a Zone 2 coaching choice. Daniels' literal lesser-of-two is
    ``min(time_cap_mi, share_mi)`` (the ``marathon_build=False`` branch).

    If a 150-minute run would exceed 1/3 of the week, we flag that weekly volume is too
    low to support a full time-cap long run.
    """
    time_cap_mi = LONG_RUN_CAP_MIN * 60.0 / easy_pace_s
    share_pct = 0.30 if weekly_miles <= 40 else 0.25
    share_mi = share_pct * weekly_miles
    third = weekly_miles / 3.0

    flags: list[str] = []
    if marathon_build:
        # House rule: allow prescription up to min(time cap, max(share, 1/3 week)).
        recommended = min(time_cap_mi, max(share_mi, third))
    else:
        recommended = min(time_cap_mi, share_mi)

    if time_cap_mi > third + 0.05:
        flags.append(
            "volume too low: a 150-min long run would exceed 1/3 of the week; raise weekly volume"
        )
    return LongRun(round(time_cap_mi, 1), round(share_mi, 1), round(recommended, 1), flags)


def pfitzinger_long_run(week_index: int, build_n: int, base_mi: float = 16.0, peak_mi: float = 20.0) -> float:
    """Pfitzinger long run (sec.4): build 16 -> 20-22, no time cap. Linear ramp across the
    build phase, clamped to the [base, peak] band."""
    if build_n <= 1:
        return peak_mi
    frac = min(1.0, max(0.0, (week_index - 1) / (build_n - 1)))
    return round(base_mi + (peak_mi - base_mi) * frac, 1)


# --- sec.5 Single-session caps (Daniels) -----------------------------------------
def session_caps(weekly_miles: float) -> dict[str, float]:
    """Upper bound (miles) on the quality volume in one session (sec.5)."""
    return {
        "T": round(min(0.10 * weekly_miles, 15.0), 1),
        "M": round(min(18.0, (0.20 if weekly_miles > 40 else 0.30) * weekly_miles), 1),
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


def threshold_workout(cap_mi: float, pace_s: int, pace_str: str) -> Workout:
    tempo = max(3.0, round(cap_mi, 1))
    seg = Segment(reps=1, pace_label="T", pace_s=pace_s, distance_m=round(tempo * METERS_PER_MILE))
    return Workout(
        WorkoutKind.THRESHOLD,
        f"Tempo: {tempo:g} mi @ T ({pace_str}/mi) + wu/cd",
        distance_mi=round(tempo + 3.0, 1),
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


def mp_long_run(total_mi: float, mp_block_mi: float, mp_s: int, mp_str: str, easy_pace_s: int) -> Workout:
    """A long run with a marathon-pace finishing block (counts as a quality session)."""
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
