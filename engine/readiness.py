"""Coach-facing readiness model: is the athlete's goal realistic, and where should the
plan start?

This is the *advisory* layer the coach reads **before** committing the numbers that
`engine/plan` runs on. Unlike `engine/plan` (pure, deterministic, regression-tested), this
module makes calibrated judgement calls — every heuristic is labelled and override-able.
Its job (per the coach's framing): "arm me to explain to the runner what is realistic."

The decision model and provenance live in
[`docs/architecture/athlete-readiness.md`](../docs/architecture/athlete-readiness.md);
book citations are inline below. Two independent states drive everything (the "two
clocks"): **fitness** (VDOT, degraded only by a true training break — Daniels Table 15.1)
and **volume readiness** (where the mileage ramp safely starts — Daniels Table 15.2 / p.219).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .vdot import (
    _VDOT_PREFERENCE,
    RACE_METERS,
    predict_race_time,
    race_equivalent_times,
    vdot_from_race,
)

# ============================================================================
# Diminishing return — how much VDOT gain is realistic in one block
# ============================================================================
# Daniels' Principle 6 (Diminishing Return) + the paired principle of Accelerating
# Setbacks (Daniels' Running Formula 3rd ed., p.36, figure 2.3): "The fitter you get, the
# less benefit you get from training harder." There is no book formula for the *rate* of
# VDOT gain, so the numbers below are a deliberately conservative **house heuristic** that
# encodes the shape of that curve (gain shrinks as fitness rises). Tune from coaching
# experience — they only feed advisory goal-feasibility text, never the deterministic plan.
_VDOT_GAIN_PER_BUILD_WEEK_AT_FLOOR = 0.5   # ~beginner, low VDOT, fully consistent
_VDOT_CEILING_REF = 85.0                   # top of Daniels' table; gain → 0 as VDOT → here
_BLOCK_GAIN_EFFICIENCY = 0.8               # not every build week converts to fitness
_GOAL_STRETCH_BUFFER_VDOT = 2.0            # within this much of "projected" = still a stretch


def projected_vdot_gain(current_vdot: float, build_weeks: int, consistency: float = 1.0) -> float:
    """Realistic VDOT improvement over a build of ``build_weeks`` (house heuristic; see
    Principle 6 above). ``consistency`` in [0,1] scales for expected adherence."""
    if current_vdot <= 0 or build_weeks <= 0:
        return 0.0
    headroom = max(0.0, (_VDOT_CEILING_REF - current_vdot) / _VDOT_CEILING_REF)
    weekly = _VDOT_GAIN_PER_BUILD_WEEK_AT_FLOOR * headroom * max(0.0, min(1.0, consistency))
    return round(weekly * build_weeks * _BLOCK_GAIN_EFFICIENCY, 1)


def projected_vdot(current_vdot: float, build_weeks: int, consistency: float = 1.0) -> float:
    """Where fitness can realistically land by race day, given diminishing return."""
    return round(current_vdot + projected_vdot_gain(current_vdot, build_weeks, consistency), 1)


# ============================================================================
# Fitness clock — freshness and training-break adjustment (Daniels Table 15.1)
# ============================================================================
# Table 15.1 (Daniels p.282, printed p.268): VDOT keeps almost all its value through a
# short break and decays toward a ~20% floor by ~10 weeks off. FVDOT-1 = no cross-training;
# FVDOT-2 = aerobic *leg* cross-training during the break (loss roughly halved). Anchor
# points are quoted in the book; intermediate days are linearly interpolated.
_FVDOT1 = [(0, 1.000), (5, 1.000), (7, 0.994), (42, 0.889), (70, 0.800), (9999, 0.800)]
_FVDOT2 = [(0, 1.000), (5, 1.000), (7, 0.997), (42, 0.944), (70, 0.900), (9999, 0.900)]

# Strava ``sport_type`` buckets. Daniels p.282/p.284: only aerobic *leg* work offsets
# detraining (FVDOT-2); strength/mobility does not preserve running VDOT (it is
# "supplemental training", Daniels p.283).
_LEG_AEROBIC_SPORTS = frozenset({
    "Ride", "VirtualRide", "EBikeRide", "Swim", "Elliptical", "StairStepper",
    "Hike", "Walk", "NordicSki", "BackcountrySki", "RollerSki", "Canoeing", "Rowing",
})
_STRENGTH_MOBILITY_SPORTS = frozenset({
    "WeightTraining", "Workout", "Yoga", "Pilates", "Crossfit", "StandUpPaddling",
})

FRESH_RACE_MAX_AGE_DAYS = 60  # Daniels p.219: a recent (uninterrupted) race sets VDOT directly


def _interp(points: list[tuple[int, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


# Volume-capacity decay (house heuristic): demonstrated peak mileage loses practical
# currency as weeks off-peak accumulate. Same interpolation machinery as Table 15.1;
# anchors are tunable coaching defaults, not a book formula.
_VOLUME_DECAY = [
    (0, 1.00),
    (1, 0.95),
    (2, 0.90),
    (4, 0.80),
    (8, 0.65),
    (12, 0.50),
    (16, 0.40),
    (9999, 0.40),
]


def decayed_volume_capacity(p_history: float, weeks_since_peak: int) -> float:
    """Scale ``p_history`` by weeks elapsed since the athlete was at/near that peak.

    Advisory input for the volume-readiness clock — see
    ``docs/architecture/athlete-readiness.md`` §4. Does **not** change VDOT (fitness clock)."""
    if p_history <= 0:
        return 0.0
    wk = max(0, int(weeks_since_peak))
    factor = _interp(_VOLUME_DECAY, float(wk))
    return round(float(p_history) * factor, 1)


def break_adjustment_factor(days_off: int, cross_trained: bool = False) -> float:
    """FVDOT multiplier for a training break of ``days_off`` consecutive days not running
    (Daniels Table 15.1). ``cross_trained`` selects the leg-aerobic column (FVDOT-2)."""
    return round(_interp(_FVDOT2 if cross_trained else _FVDOT1, max(0, days_off)), 3)


def classify_cross_training(sport_types: list[str]) -> str:
    """Bucket Strava ``sport_type`` values for the break model (Daniels p.282/p.284).

    Returns ``"leg_aerobic"`` (offsets detraining → FVDOT-2), ``"strength_mobility"``
    (does not), or ``"none"``.
    """
    leg = any(s in _LEG_AEROBIC_SPORTS for s in sport_types)
    if leg:
        return "leg_aerobic"
    if any(s in _STRENGTH_MOBILITY_SPORTS for s in sport_types):
        return "strength_mobility"
    return "none"


def adjusted_vdot(race_vdot: float, days_off: int, cross_trained: bool = False) -> float:
    """Race VDOT discounted for a training break since the race (Daniels Table 15.1).

    A break ≤ 5 days, or none, returns the race VDOT unchanged. **An off-season *dip in
    mileage* is not a break** — only days genuinely not running count (Daniels p.155)."""
    return round(race_vdot * break_adjustment_factor(days_off, cross_trained), 1)


@dataclass
class FitnessSelection:
    """Result of choosing which race sets fitness, after applying coach directives."""

    chosen_date: str | None
    source: str                    # human-readable provenance
    race_vdot: float | None        # VDOT of the chosen race (before detraining)
    effective_vdot: float | None   # detrained to today (the number a plan should use)
    break_days: int
    considered: list[str]          # races that survived the directives
    dropped: list[str]             # "<date> <category>: <why>"
    notes: list[str] = field(default_factory=list)


def select_fitness_vdot(
    races: list[dict],
    *,
    excluded_dates: set[str] | None = None,
    effort_quality: dict[str, str] | None = None,
    time_overrides: dict[str, int] | None = None,
    anchor_date: str | None = None,
    break_days: int = 0,
    cross_trained: bool = False,
) -> FitnessSelection:
    """Pick the race that sets fitness from ``races`` after applying coach directives, then
    detrain it to today (Daniels Table 15.1).

    Each race dict needs ``category`` (a ``RACE_METERS`` key), ``date`` (ISO), ``duration_s``;
    ``name`` is optional. Directives, all keyed by race ``date``:

    - ``excluded_dates`` — `DataExclude`: drop entirely.
    - ``effort_quality`` — `EffortQuality`: a non-``max`` effort is dropped *unless* a
      ``time_override`` rehabilitates it (a coach estimate of its true worth).
    - ``time_overrides`` — `RaceEstimate`: use the corrected finish time for VDOT.
    - ``anchor_date`` — `FitnessAnchor`: pin this race regardless of preference.

    With no anchor, selection mirrors ``recommended_vdot`` (Daniels distance preference,
    fastest within a distance) over the surviving races.
    """
    excluded_dates = excluded_dates or set()
    effort_quality = effort_quality or {}
    time_overrides = time_overrides or {}

    dropped: list[str] = []
    candidates: list[dict] = []
    for r in races:
        cat, dt = r.get("category"), r.get("date")
        meters = RACE_METERS.get(cat)
        if meters is None or not dt:
            continue
        tag = f"{dt} {cat}"
        if dt in excluded_dates:
            dropped.append(f"{tag}: excluded (DataExclude)")
            continue
        time_s = time_overrides.get(dt) or r.get("duration_s")
        vd = vdot_from_race(meters, time_s)
        if vd is None:
            continue
        q = effort_quality.get(dt)
        if anchor_date is None and q in ("submaximal", "compromised") and dt not in time_overrides:
            dropped.append(f"{tag}: dropped ({q} effort)")
            continue
        candidates.append({**r, "_vdot": vd, "_est": dt in time_overrides})

    notes: list[str] = []
    chosen: dict | None = None
    if anchor_date is not None:
        chosen = next((c for c in candidates if c.get("date") == anchor_date), None)
        if chosen is None:
            notes.append(f"anchor {anchor_date} not among candidate races; fell back to preference.")
    if chosen is None:
        by_cat: dict[str, dict] = {}
        for c in candidates:
            cat = c["category"]
            if cat not in by_cat or c["_vdot"] > by_cat[cat]["_vdot"]:
                by_cat[cat] = c
        for cat in _VDOT_PREFERENCE:
            if cat in by_cat:
                chosen = by_cat[cat]
                break

    considered = [f"{c['date']} {c['category']} (VDOT {c['_vdot']})" for c in candidates]
    if chosen is None:
        notes.append("No race survived the directives; cannot set fitness from races.")
        return FitnessSelection(None, "no eligible race", None, None, break_days, considered, dropped, notes)

    race_vdot = chosen["_vdot"]
    eff = adjusted_vdot(race_vdot, break_days, cross_trained)
    src = f"{chosen['category']} {chosen.get('date')}"
    if chosen.get("_est"):
        src += " (coach estimate)"
    if anchor_date == chosen.get("date"):
        src += " (anchored)"
    if break_days > 5:
        notes.append(f"Detrained {break_days} d → ×{break_adjustment_factor(break_days, cross_trained)} (Table 15.1).")
    return FitnessSelection(chosen.get("date"), src, race_vdot, eff, break_days, considered, dropped, notes)


@dataclass
class Freshness:
    """Whether to trust a race VDOT as the athlete's current fitness."""

    trust_race_vdot: bool
    race_age_days: int | None
    break_days: int
    cross_training: str            # "leg_aerobic" | "strength_mobility" | "none"
    fvdot: float
    notes: list[str] = field(default_factory=list)


def assess_freshness(
    race_vdot: float,
    race_age_days: int | None,
    break_days: int = 0,
    cross_training: str = "none",
) -> Freshness:
    """Decide whether ``race_vdot`` still reflects current fitness (Daniels p.219 recency +
    Table 15.1 break). ``break_days`` is the longest gap of *not running* since the race."""
    notes: list[str] = []
    crossed = cross_training == "leg_aerobic"
    fvdot = break_adjustment_factor(break_days, crossed)

    stale_race = race_age_days is not None and race_age_days > FRESH_RACE_MAX_AGE_DAYS
    broke = break_days > 5
    if stale_race:
        notes.append(
            f"VDOT source race is {race_age_days} d old (> {FRESH_RACE_MAX_AGE_DAYS} d); "
            "confirm with a tune-up race before trusting paces."
        )
    if broke:
        col = "with cross-training (FVDOT-2)" if crossed else "no cross-training (FVDOT-1)"
        notes.append(
            f"{break_days}-day running break → Table 15.1 factor {fvdot} {col}; "
            "adjust VDOT before setting paces."
        )
    elif cross_training == "strength_mobility":
        notes.append("Cross-training is strength/mobility only — does not offset detraining (Daniels p.284).")

    return Freshness(
        trust_race_vdot=not stale_race and not broke,
        race_age_days=race_age_days,
        break_days=break_days,
        cross_training=cross_training,
        fvdot=fvdot,
        notes=notes,
    )


OFF_WEEK_MILES = 1.0


def longest_running_break_days(
    weeks: list[dict],
    since: date,
    today: date,
    *,
    off_week_miles: float = OFF_WEEK_MILES,
) -> int:
    """Longest streak of ISO weeks with ``< off_week_miles`` running since ``since`` (×7 days).

    Daniels Table 15.1 keys on days *not running*, not mileage dips."""
    from engine.analyze import _filter_weeks, summarize

    summ = summarize(_filter_weeks(weeks, since, today))
    weekly = sorted(summ.weekly_run_miles.items(), key=lambda kv: kv[0])
    longest = run = 0
    for _, miles in weekly:
        run = run + 1 if (miles or 0.0) < off_week_miles else 0
        longest = max(longest, run)
    return longest * 7


def cross_training_during_break(
    activities: list[dict], since: date, today: date
) -> tuple[bool, str | None]:
    """Whether leg-aerobic cross-training occurred during ``[since, today]`` (FVDOT-2)."""
    counts: dict[str, int] = {}
    for a in activities:
        sport = str(a.get("sport_type") or a.get("type") or "")
        if sport in ("Run", "TrailRun", "VirtualRun", ""):
            continue
        ds = str(a.get("start_date") or a.get("start_date_local") or "")[:10]
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if since <= d <= today:
            counts[sport] = counts.get(sport, 0) + 1
    if not counts:
        return False, None
    bucket = classify_cross_training(list(counts))
    total = sum(counts.values())
    summary = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    return bucket == "leg_aerobic", f"{summary} ({total} acts; {bucket})"


@dataclass
class MergeVdotResolution:
    """Book-faithful VDOT for merge: pick fitness race, best break window, freshness trust."""

    vdot: float                     # plan-facing number (raw if trusted, else Table 15.1)
    raw_vdot: float
    fitness: FitnessSelection
    break_days: int
    break_window: str               # "fitness_race" | "marathon"
    cross_trained: bool
    cross_training_note: str | None
    freshness: Freshness
    notes: list[str] = field(default_factory=list)


def resolve_merge_vdot(
    races: list[dict],
    weeks: list[dict],
    *,
    marathon_date: date | None,
    today: date,
    activities: list[dict] | None = None,
    excluded_dates: set[str] | None = None,
    effort_quality: dict[str, str] | None = None,
    time_overrides: dict[str, int] | None = None,
    anchor_date: str | None = None,
) -> MergeVdotResolution | None:
    """Choose fitness race, measure break since fitness (vs marathon), maximize effective VDOT.

    1. ``select_fitness_vdot`` with ``break_days=0`` picks the race (Daniels preference).
    2. Compare break windows anchored at the fitness race vs last marathon; keep the window
       that yields the higher Table 15.1-adjusted VDOT (break is days not running since anchor).
    3. ``assess_freshness`` (Daniels p.219 + Table 15.1): trust raw race VDOT when the source
       race is ≤60 d old and break ≤5 d; otherwise apply ``adjusted_vdot``.
    """
    fitness = select_fitness_vdot(
        races,
        excluded_dates=excluded_dates,
        effort_quality=effort_quality,
        time_overrides=time_overrides,
        anchor_date=anchor_date,
        break_days=0,
        cross_trained=False,
    )
    if fitness.race_vdot is None or not fitness.chosen_date:
        return None

    raw_vdot = float(fitness.race_vdot)
    fitness_date = date.fromisoformat(fitness.chosen_date[:10])
    windows: list[tuple[str, date]] = [("fitness_race", fitness_date + timedelta(days=1))]
    if marathon_date is not None and marathon_date != fitness_date:
        windows.append(("marathon", marathon_date + timedelta(days=1)))

    best: tuple[float, int, bool, str | None, str] | None = None
    for label, since in windows:
        bd = longest_running_break_days(weeks, since, today)
        crossed, cross_note = (
            cross_training_during_break(activities, since, today)
            if activities
            else (False, None)
        )
        eff = adjusted_vdot(raw_vdot, bd, crossed)
        if best is None or eff > best[0]:
            best = (eff, bd, crossed, cross_note, label)

    assert best is not None
    eff_vdot, break_days, cross_trained, cross_note, break_window = best
    race_age_days = (today - fitness_date).days
    cross_str = "leg_aerobic" if cross_trained else "none"
    fresh = assess_freshness(raw_vdot, race_age_days, break_days, cross_str)
    plan_vdot = raw_vdot if fresh.trust_race_vdot else adjusted_vdot(raw_vdot, break_days, cross_trained)

    notes: list[str] = list(fitness.notes)
    notes.append(
        f"break window {break_window} ({break_days} d not running) → "
        f"effective {eff_vdot} vs raw {raw_vdot}"
    )
    if len(windows) > 1 and break_window != "fitness_race":
        notes.append(f"chose {break_window} window (higher effective VDOT than fitness_race)")
    notes += fresh.notes
    if fresh.trust_race_vdot:
        notes.append("freshness: trust race VDOT (≤60 d, break ≤5 d)")
    else:
        notes.append(f"freshness: plan VDOT {plan_vdot} (Table 15.1)")

    return MergeVdotResolution(
        vdot=plan_vdot,
        raw_vdot=raw_vdot,
        fitness=fitness,
        break_days=break_days,
        break_window=break_window,
        cross_trained=cross_trained,
        cross_training_note=cross_note,
        freshness=fresh,
        notes=notes,
    )


# ============================================================================
# Volume clock — safe progression, re-entry start, and recommended peak
# ============================================================================
DANIELS_MILEAGE_CEILING = 80.0  # Daniels p.219: "no need to go over 80 miles per week"


def safe_weekly_step(days_per_week: int, runs_per_week: int | None = None) -> int:
    """Daniels p.219: raise weekly mileage by 1 mi per *running session*, capped at +10 mi —
    and only "about every 4th week". ``runs_per_week`` defaults to one run per day; doubles
    raise it (still capped at 10)."""
    runs = runs_per_week if runs_per_week is not None else days_per_week
    return max(1, min(int(runs), 10))


def recommended_reentry_volume(
    w_now: float,
    p_history: float,
    *,
    recent_sustained_mpw: float | None = None,
    race_fit: bool = True,
    injury_prone: bool = False,
    days_per_week: int = 5,
) -> tuple[float, str]:
    """Where the ramp should *start* — the re-entry volume (see athlete-readiness §4).

    - ``recent_sustained_mpw`` (a real recent multi-week high) is the best signal; use it.
    - else, a **race-fit** athlete whose demonstrated peak is well above an off-season
      ``w_now`` re-enters near the midpoint of capacity, not raw ``w_now`` (which would write
      an absurdly small week 1) and not the untrained peak (injury risk).
    - else (base-from-scratch / not race-fit) start at ``w_now`` and slow-build.

    Returns (start_mpw, rationale). Injury-prone caps the jump to one safe step over ``w_now``.
    """
    if recent_sustained_mpw is not None:
        start, why = float(recent_sustained_mpw), "recent sustained weekly volume (best signal)"
    elif race_fit and p_history > w_now + 1.0:
        start, why = round(0.5 * p_history, 1), "race-fit but low-volume → midpoint re-entry off demonstrated peak"
    else:
        start, why = float(w_now), "building base from current volume"

    if injury_prone:
        capped = round(w_now + safe_weekly_step(days_per_week), 1)
        if start > capped:
            start, why = capped, why + "; injury-prone cap (one safe step over current)"
    return max(start, float(w_now)), why


def recommended_peak_mileage(
    p_history: float,
    days_per_week: int,
    *,
    injury_prone: bool = False,
    goal_demanding: bool = False,
) -> tuple[float, str]:
    """Recommend a **P** (planned peak weekly mileage) for the block — the athlete/coach's
    choice in Daniels' framing (p.232), which the engine only *advises*.

    Anchored on demonstrated capacity (``p_history``). A demanding goal justifies at most one
    safe step above it (Principle 6: don't chase volume the body hasn't shown); injury-prone
    holds at demonstrated; everything is clamped to Daniels' 80-mpw practical ceiling (p.219).
    """
    p = float(p_history)
    why = "demonstrated peak (p_history)"
    if goal_demanding and not injury_prone:
        p = p_history + safe_weekly_step(days_per_week)
        why = "demonstrated peak + one safe step (demanding goal)"
    if injury_prone:
        why = "held at demonstrated peak (injury-prone)"
    if p > DANIELS_MILEAGE_CEILING:
        p, why = DANIELS_MILEAGE_CEILING, why + f"; clamped to Daniels' {DANIELS_MILEAGE_CEILING:g}-mpw ceiling"
    return round(p, 1), why


def injury_volume_factor(injury_prone: bool) -> float:
    """Multiplier applied to an *aggressive* volume recommendation when injury-prone.
    Conservative house rule grounded in Accelerating Setbacks (Daniels p.36, fig 2.3): the
    cost of overshooting volume rises non-linearly, so we hold injury-prone athletes to
    demonstrated capacity rather than projecting beyond it."""
    return 0.9 if injury_prone else 1.0


# ============================================================================
# Goal feasibility — the coach realism call
# ============================================================================
@dataclass
class GoalAssessment:
    distance: str
    goal_time_s: int
    required_vdot: float | None    # VDOT a runner needs to hit the goal at this distance
    current_vdot: float
    projected_vdot: float          # realistic race-day VDOT (current + diminishing-return gain)
    gap_vdot: float | None         # required - current
    verdict: str                   # "within_current" | "in_reach" | "stretch" | "unrealistic"
    realistic_time_s: int | None   # equivalent time at projected_vdot (a defensible target)
    notes: list[str] = field(default_factory=list)


def goal_feasibility(
    current_vdot: float,
    goal_time_s: int,
    distance_m: float = RACE_METERS["Marathon"],
    *,
    build_weeks: int = 15,
    consistency: float = 1.0,
) -> GoalAssessment:
    """Is ``goal_time_s`` realistic from ``current_vdot`` over a build? Gives the coach a
    verdict, the VDOT gap, and a defensible alternative time (the equivalent of *projected*
    fitness). All judgement here is advisory (diminishing-return heuristic, see above)."""
    dist_label = next((k for k, v in RACE_METERS.items() if abs(v - distance_m) < 1.0), "Marathon")
    required = vdot_from_race(distance_m, goal_time_s)
    proj = projected_vdot(current_vdot, build_weeks, consistency)
    realistic = predict_race_time(proj, distance_m)
    notes: list[str] = []

    if required is None:
        return GoalAssessment(dist_label, goal_time_s, None, current_vdot, proj, None, "unrealistic", realistic,
                              ["could not compute required VDOT for goal"])

    gap = round(required - current_vdot, 1)
    if gap <= 0:
        verdict = "within_current"
        notes.append("Goal is at or below current race fitness — already in reach; protect it, don't over-reach.")
    elif required <= proj:
        verdict = "in_reach"
        notes.append(f"Goal needs VDOT {required}; {gap} above current {current_vdot}, within the ~{projected_vdot_gain(current_vdot, build_weeks, consistency)}-pt gain realistic in {build_weeks} wk.")
    elif required <= proj + _GOAL_STRETCH_BUFFER_VDOT:
        verdict = "stretch"
        notes.append(f"Goal needs VDOT {required}; reachable only on a near-perfect block (above the ~{proj} projection). Frame as a stretch / B-goal.")
    else:
        verdict = "unrealistic"
        notes.append(f"Goal needs VDOT {required}, but {build_weeks} wk realistically reaches ~{proj}. Recommend re-anchoring near the projected-fitness equivalent.")

    return GoalAssessment(dist_label, goal_time_s, required, current_vdot, proj, gap, verdict, realistic, notes)


# ============================================================================
# Tune-up result outcome — the on-track / behind verdict once a race has been run
# ============================================================================
# A landed tune-up result maps to a glance-level status by projecting the *measured* fitness over the
# weeks left to race day (same heuristic as goal_feasibility): a goal still within/in-reach is on
# track, a stretch is worth watching, an unrealistic gap is the signal to re-anchor.
_VERDICT_TO_STATUS = {
    "within_current": "on_track",
    "in_reach": "on_track",
    "stretch": "watch",
    "unrealistic": "behind",
}


@dataclass
class TuneUpOutcome:
    status: str                    # "on_track" | "watch" | "behind"
    verdict: str                   # underlying goal_feasibility verdict
    measured_vdot: float
    realistic_time_s: int | None   # defensible re-anchor target if behind/stretch


def tune_up_outcome(measured_vdot: float, goal_time_s: int, *, weeks_remaining: int) -> TuneUpOutcome:
    """Turn a run tune-up (its ``measured_vdot``) into an on-track/behind status for the marathon
    goal, projecting over the weeks left. Advisory — same projection heuristic as ``goal_feasibility``."""
    ga = goal_feasibility(measured_vdot, goal_time_s, build_weeks=max(1, weeks_remaining))
    return TuneUpOutcome(
        status=_VERDICT_TO_STATUS.get(ga.verdict, "watch"),
        verdict=ga.verdict,
        measured_vdot=measured_vdot,
        realistic_time_s=ga.realistic_time_s,
    )


# ============================================================================
# Tune-up race ladder — forward-looking VDOT feedback loop
# ============================================================================
@dataclass
class TuneUpCheckpoint:
    label: str                  # distance label, e.g. "10K"
    distance_m: float
    week: int                   # build week the tune-up lands in (1-based)
    weeks_before_race: int      # how many weeks out from race day
    date: str | None            # ISO date, when the race date is known
    on_track_vdot: float        # interim VDOT on a straight line to the goal-required VDOT
    on_track_time_s: int | None # target time to stay on the A-goal trajectory
    projected_vdot: float       # realistic interim VDOT (diminishing-return curve)
    projected_time_s: int | None
    note: str = ""


@dataclass
class TuneUpLadder:
    current_vdot: float
    goal_time_s: int
    required_vdot: float | None
    projected_vdot: float
    realistic_time_s: int | None
    verdict: str
    checkpoints: list[TuneUpCheckpoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# Default ladder: a short, sharp 5K early, a 10K mid-block, and a second 10K in race prep — each at a
# fraction of the build so the buffer is sampled as fitness (should be) rising. We deliberately do NOT
# put a half marathon late: both Pfitzinger (ch.8 caps late tune-ups at 8-10K) and Higdon (his half
# sits ~9-10 wk out, never near the taper) keep the closest-in races short so they don't cost the
# recovery a peak long-run block needs. A 10K gives nearly the same fitness read at a fraction of the cost.
_DEFAULT_TUNE_UP_LADDER: tuple[tuple[str, float], ...] = (("5K", 0.30), ("10K", 0.55), ("10K", 0.80))


def _fmt_clock(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def tune_up_ladder(
    current_vdot: float,
    goal_time_s: int,
    *,
    build_weeks: int = 15,
    taper_weeks: int = 3,
    race_date: str | None = None,
    ladder: tuple[tuple[str, float], ...] = _DEFAULT_TUNE_UP_LADDER,
    consistency: float = 1.0,
) -> TuneUpLadder:
    """Forward-looking tune-up race checkpoints that turn an aggressive marathon goal into a
    measured feedback loop. The default ladder is short/sharp (5K → 10K → 10K) and keeps the
    closest-in race at 10K — a half marathon that late would cost the recovery a peak long-run
    block needs (cf. Pfitzinger ch.8, Higdon). For each checkpoint we give two target times at
    that distance:

    - **on-track-for-goal** — the time that says fitness is rising on a straight line toward the
      VDOT the goal *requires* (the A-goal trajectory).
    - **realistic / projected** — the time at the diminishing-return projection (``projected_vdot``).

    A result at/under the on-track time keeps the A-goal alive; between the two suggests a B-goal;
    slower than projected is the signal to re-anchor the goal to the equivalent marathon time. All
    advisory (same heuristics as ``goal_feasibility``); nothing here mutates state."""
    ga = goal_feasibility(current_vdot, goal_time_s, build_weeks=build_weeks, consistency=consistency)
    required = ga.required_vdot
    total_weeks = build_weeks + max(0, taper_weeks)
    race_d = date.fromisoformat(race_date) if race_date else None

    checks: list[TuneUpCheckpoint] = []
    for label, frac in ladder:
        dist = RACE_METERS.get(label)
        if dist is None:
            continue
        week = max(1, round(frac * build_weeks))
        weeks_before = max(1, total_weeks - week)
        on_track_v = round(current_vdot + (required - current_vdot) * frac, 1) if required else current_vdot
        proj_v = projected_vdot(current_vdot, week, consistency)
        on_track_t = predict_race_time(on_track_v, dist)
        proj_t = predict_race_time(proj_v, dist)
        date_iso = (race_d - timedelta(weeks=weeks_before)).isoformat() if race_d else None
        note = (
            f"Run \u2264 {_fmt_clock(on_track_t)} to stay on pace for {_fmt_clock(goal_time_s)}; "
            f"{_fmt_clock(proj_t)} is the realistic mark. Slower than that \u2192 re-anchor the goal."
        )
        checks.append(
            TuneUpCheckpoint(label, dist, week, weeks_before, date_iso,
                             on_track_v, on_track_t, proj_v, proj_t, note)
        )

    notes = list(ga.notes)
    if required:
        notes.insert(
            0,
            f"Goal needs VDOT {required}; you're at {current_vdot} (projected ~{ga.projected_vdot}). The "
            "tune-ups below tell you, mid-block, whether the goal is tracking or needs re-anchoring.",
        )
    return TuneUpLadder(
        current_vdot, goal_time_s, required, ga.projected_vdot, ga.realistic_time_s, ga.verdict, checks, notes
    )


# ============================================================================
# Top-level coach report
# ============================================================================
@dataclass
class ReadinessAssessment:
    name: str
    current_vdot: float
    freshness: Freshness
    equivalent_times: dict[str, int]      # race-day predictions across distances at current VDOT
    projected_vdot: float
    reentry_start_mpw: float
    reentry_rationale: str
    recommended_peak_mpw: float
    peak_rationale: str
    goal: GoalAssessment
    notes: list[str] = field(default_factory=list)


def assess_readiness(
    inputs,
    *,
    race_age_days: int | None = None,
    build_weeks: int | None = None,
    consistency: float = 1.0,
    recent_sustained_mpw: float | None = None,
    race_fit: bool = True,
) -> ReadinessAssessment:
    """Build the full coach-facing readiness report for an ``AthleteInputs``.

    Reads break/cross-training context from the athlete fields when present
    (``recent_break_days``, ``cross_trained_during_break``), and projects realistic fitness,
    a safe ramp start, a recommended peak, and a verdict on the A-goal. The coach uses this to
    confirm or correct the numbers fed to ``engine/plan.build_plan``.
    """
    break_days = int(getattr(inputs, "recent_break_days", None) or 0)
    crossed = bool(getattr(inputs, "cross_trained_during_break", False))
    cross = "leg_aerobic" if crossed else ("strength_mobility" if break_days > 5 else "none")

    fresh = assess_freshness(inputs.vdot, race_age_days, break_days, cross)
    current_vdot = inputs.vdot if fresh.trust_race_vdot else adjusted_vdot(inputs.vdot, break_days, crossed)

    n_build = build_weeks if build_weeks is not None else max(1, inputs.block_weeks - 3)
    goal = goal_feasibility(
        current_vdot, inputs.goal_marathon_s, RACE_METERS["Marathon"],
        build_weeks=n_build, consistency=consistency,
    )
    goal_demanding = goal.verdict in ("stretch", "unrealistic")

    start, start_why = recommended_reentry_volume(
        inputs.w_now, inputs.p_history,
        recent_sustained_mpw=recent_sustained_mpw, race_fit=race_fit,
        injury_prone=inputs.injury_prone, days_per_week=inputs.days_per_week,
    )
    peak, peak_why = recommended_peak_mileage(
        inputs.p_history, inputs.days_per_week,
        injury_prone=inputs.injury_prone, goal_demanding=goal_demanding,
    )

    notes: list[str] = []
    notes += fresh.notes
    notes.append(
        f"Re-entry start ≈ {start:g} mpw ({start_why}); recommended peak P ≈ {peak:g} mpw ({peak_why}). "
        f"Ramp safely: hold ~3-4 wk, then +{safe_weekly_step(inputs.days_per_week)} mpw (Daniels p.219)."
    )

    return ReadinessAssessment(
        name=inputs.name,
        current_vdot=current_vdot,
        freshness=fresh,
        equivalent_times=race_equivalent_times(current_vdot),
        projected_vdot=goal.projected_vdot,
        reentry_start_mpw=start,
        reentry_rationale=start_why,
        recommended_peak_mpw=peak,
        peak_rationale=peak_why,
        goal=goal,
        notes=notes,
    )
