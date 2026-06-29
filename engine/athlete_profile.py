"""Athlete dossier — a deterministic, read-only analysis of an athlete's *past* that turns their
training history and race results into the personalization signals a coach reasons about before
building a block.

This is the repeatable version of the manual investigation a coach does by hand: where did the last
block actually start, what volume can they sustain, how has fitness (VDOT) moved over time and does it
respond to mileage, is the goal realistic, and how stale is the fitness anchor. It is **pure**: given
the same parsed history it always yields the same `AthleteDossier`, computes nothing it can't defend
from the data, and **mutates no state** — it only *recommends*: human-readable strings plus structured
`ProposedInput`s (defensible `AthleteInputs` changes). The CLI (`athlete-report --propose`) turns those
into `proposed` events for coach review; nothing here ever applies them.

Inputs are plain parsed structures (weekly volume + races + the current VDOT/goals), so the core is
trivially testable; the CLI (`main.py athlete-report`) is the impure adapter that loads them from the
store and the `output/marathon/` artifacts. See `docs/architecture/athlete-readiness.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import mean

from engine import readiness as rd
from engine.plan import common
from engine.pronouns import Pronouns
from engine.pronouns import resolve as resolve_pronouns
from engine.vdot import RACE_METERS, vdot_from_race

# Semantic version of the dossier signal math. Bump when responder thresholds, FRESH_ANCHOR_DAYS,
# or the volume/fitness derivations change, so persisted `dossier_snapshots` stay attributable to the
# logic that produced them (mirrors engine.plan.ENGINE_VERSION for plans).
DOSSIER_VERSION = "1"

# A VDOT read older than this should be re-confirmed before trusting paces (Daniels notes fitness
# drifts within a couple of months; the merge layer already warns past ~60 d).
FRESH_ANCHOR_DAYS = 60
# A short-race VDOT this far above the marathon VDOT marks an endurance-limited / speed-dominant
# profile (the engine is there, the aerobic durability isn't yet).
_ENDURANCE_GAP_VDOT = 3.0
# VDOT span below which fitness reads as "flat" across the race history (no real movement to explain).
_FLAT_VDOT_SPAN = 2.0


@dataclass
class WeeklyVolume:
    """One training week's volume (from a capacity profile or the raw feed)."""

    week_start: str           # ISO Monday
    miles: float
    run_days: int = 0
    long_pct: float = 0.0     # long run as a share of the week (0–100)
    race_week: bool = False


@dataclass
class RacePerformance:
    date: str
    name: str
    category: str             # "5K" | "10K" | "Half Marathon" | "Marathon" | other
    distance_m: float
    time_s: int
    vdot: float
    trailing_4wk_mpw: float | None = None   # avg weekly volume in the 4 wk before the race


@dataclass
class VolumeProfile:
    demonstrated_opener_mpw: float    # how the last block actually opened (median of its first weeks)
    sustainable_low_mpw: float        # 25th pct of active weeks
    sustainable_high_mpw: float       # 75th pct of active weeks
    peak_mpw: float
    avg_active_mpw: float
    long_run_dominance_pct: float     # mean long-run share across active weeks
    active_weeks: int
    notes: list[str] = field(default_factory=list)


@dataclass
class FitnessTimeline:
    current_vdot: float
    races: list[RacePerformance]
    vdot_min: float | None
    vdot_max: float | None
    volume_vdot_corr: float | None    # Pearson r of trailing volume vs race VDOT
    responder: str                    # see classify; advisory
    endurance_gap: float | None       # best short-race VDOT − marathon VDOT
    notes: list[str] = field(default_factory=list)


@dataclass
class GoalRealism:
    label: str
    goal_time_s: int
    required_vdot: float
    verdict: str                      # goal_feasibility verdict
    realistic_time_s: int | None


@dataclass
class AnchorConfidence:
    current_vdot: float
    source_date: str | None
    age_days: int | None
    stale: bool
    note: str


@dataclass
class ProposedInput:
    """A concrete, data-backed change to an `AthleteInputs` field the dossier *recommends* — never
    applies. The CLI turns each into a `proposed` `ManualOverride` event so the coach approves it
    through `review` before any replan folds it in (no silent mutation; see docs/event-sourcing)."""

    field: str                 # an AthleteInputs field name
    value: object              # proposed value
    rationale: str             # coach-facing why, drawn from the dossier evidence
    current: object | None = None   # the value in play today, for the diff the coach reviews


@dataclass
class AthleteDossier:
    name: str
    volume: VolumeProfile
    fitness: FitnessTimeline
    goals: list[GoalRealism]
    anchor: AnchorConfidence
    recommendations: list[str] = field(default_factory=list)
    proposed_inputs: list[ProposedInput] = field(default_factory=list)


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0,1]); empty → 0.0."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None when <3 points or either series has no variance."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return round(cov / (sx ** 0.5 * sy ** 0.5), 2)


def build_volume_profile(weeks: list[WeeklyVolume]) -> VolumeProfile:
    """Characterize demonstrated volume: how the block opened, the sustainable band, the peak, and how
    long-run-dominant the athlete is. ``weeks`` should be one training block in chronological order."""
    active = [w for w in weeks if w.miles > 0]
    if not active:
        return VolumeProfile(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, ["no active training weeks on file"])

    opener_weeks = active[: min(3, len(active))]
    opener = round(sorted(m.miles for m in opener_weeks)[len(opener_weeks) // 2], 1)
    miles_sorted = sorted(w.miles for w in active)
    long_pcts = [w.long_pct for w in active if w.long_pct]
    notes: list[str] = []
    dominance = round(mean(long_pcts), 0) if long_pcts else 0.0
    if dominance >= 70:
        notes.append(
            f"long-run-dominant: the long run is ~{dominance:g}% of weekly volume on average — "
            "training is essentially one big run a week, so total mileage understates the long-run load"
        )
    return VolumeProfile(
        demonstrated_opener_mpw=opener,
        sustainable_low_mpw=round(_percentile(miles_sorted, 0.25), 1),
        sustainable_high_mpw=round(_percentile(miles_sorted, 0.75), 1),
        peak_mpw=round(max(miles_sorted), 1),
        avg_active_mpw=round(mean(miles_sorted), 1),
        long_run_dominance_pct=dominance,
        active_weeks=len(active),
        notes=notes,
    )


def attach_trailing_volume(
    races: list[RacePerformance], weekly: list[WeeklyVolume], *, window_days: int = 28
) -> None:
    """Fill each race's ``trailing_4wk_mpw`` from the weekly feed (mutates the race objects)."""
    series = []
    for w in weekly:
        try:
            series.append((date.fromisoformat(w.week_start), w.miles))
        except (ValueError, TypeError):
            continue
    for r in races:
        try:
            rd_ = date.fromisoformat(r.date)
        except (ValueError, TypeError):
            continue
        vals = [mi for ws, mi in series if 0 <= (rd_ - ws).days < window_days]
        if vals:
            r.trailing_4wk_mpw = round(mean(vals), 1)


def _classify_responder(
    races: list[RacePerformance], corr: float | None, span: float | None, endurance_gap: float | None
) -> tuple[str, list[str]]:
    notes: list[str] = []
    rated = [r for r in races if r.vdot]
    if len(rated) < 3:
        return "insufficient-data", ["fewer than 3 rated races — responder profile not yet defensible"]

    if corr is not None and corr >= 0.5 and (span or 0) >= _FLAT_VDOT_SPAN:
        notes.append(f"VDOT rises with trailing volume (r={corr}) — responds to mileage")
        return "volume-sensitive", notes
    if endurance_gap is not None and endurance_gap >= _ENDURANCE_GAP_VDOT:
        notes.append(
            f"short-race VDOT runs ~{endurance_gap:g} above the marathon — speed is ahead of aerobic "
            "durability; mileage should buy endurance, not a higher VDOT ceiling"
        )
        if corr is not None and corr < 0.3:
            notes.append(f"and VDOT barely tracks volume (r={corr}) — don't over-index on peak mpw")
        return "speed-dominant", notes
    if span is not None and span < _FLAT_VDOT_SPAN:
        notes.append(
            f"VDOT has held within ~{span:g} points across the race history — fitness is stable and "
            "not strongly volume-driven in the observed range; consistency matters more than peak mileage"
        )
        return "stable", notes
    return "mixed", ["no clear volume→VDOT pattern; treat tune-ups as the source of truth"]


def build_fitness_timeline(races: list[RacePerformance], current_vdot: float) -> FitnessTimeline:
    """VDOT over time from the race history + a (advisory) responder classification."""
    rated = sorted((r for r in races if r.vdot), key=lambda r: r.date)
    vdots = [r.vdot for r in rated]
    vmin = round(min(vdots), 1) if vdots else None
    vmax = round(max(vdots), 1) if vdots else None
    span = (vmax - vmin) if (vmin is not None and vmax is not None) else None

    pairs = [(r.trailing_4wk_mpw, r.vdot) for r in rated if r.trailing_4wk_mpw is not None]
    corr = _pearson([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 3 else None

    short = [r.vdot for r in rated if r.category in ("5K", "10K")]
    mara = [r.vdot for r in rated if r.category == "Marathon"]
    endurance_gap = round(max(short) - min(mara), 1) if short and mara else None

    responder, notes = _classify_responder(rated, corr, span, endurance_gap)
    return FitnessTimeline(
        current_vdot=current_vdot, races=rated, vdot_min=vmin, vdot_max=vmax,
        volume_vdot_corr=corr, responder=responder, endurance_gap=endurance_gap, notes=notes,
    )


def assess_goals(current_vdot: float, goals: list[tuple[str, int]], *, build_weeks: int) -> list[GoalRealism]:
    """Run each (label, marathon goal time) through the readiness feasibility model."""
    out: list[GoalRealism] = []
    for label, time_s in goals:
        if not time_s:
            continue
        ga = rd.goal_feasibility(current_vdot, time_s, build_weeks=build_weeks)
        out.append(GoalRealism(label, time_s, ga.required_vdot, ga.verdict, ga.realistic_time_s))
    return out


def anchor_confidence(current_vdot: float, source_date: str | None, *, today: date) -> AnchorConfidence:
    age = None
    stale = False
    note = "no dated fitness source on file"
    if source_date:
        try:
            age = (today - date.fromisoformat(source_date[:10])).days
            stale = age > FRESH_ANCHOR_DAYS
            note = (
                f"fitness anchored on a race {age} d ago (> {FRESH_ANCHOR_DAYS} d) — confirm with a "
                "tune-up before trusting paces" if stale
                else f"fitness anchor is fresh ({age} d old)"
            )
        except (ValueError, TypeError):
            pass
    return AnchorConfidence(current_vdot, source_date, age, stale, note)


def _recommendations(
    vol: VolumeProfile, fit: FitnessTimeline, goals: list[GoalRealism], anchor: AnchorConfidence,
    *, injury_prone: bool, current_opener_mpw: float | None, pronouns: Pronouns,
) -> list[str]:
    recs: list[str] = []

    # Opener — anchor the re-entry on what the athlete has actually opened a block at.
    if vol.demonstrated_opener_mpw > 0:
        rec = (
            f"Open near {pronouns.possessive} demonstrated ~{vol.demonstrated_opener_mpw:g} mpw "
            f"(set reentry_start_mpw ≈ {round(vol.demonstrated_opener_mpw)})"
        )
        if current_opener_mpw is not None and current_opener_mpw + 1.5 < vol.demonstrated_opener_mpw:
            rec += f" — the current plan opens at only {current_opener_mpw:g} mpw"
        if injury_prone:
            rec += "; ramp cautiously given injury history"
        recs.append(rec)

    # Responder → how to spend the block.
    if fit.responder == "speed-dominant":
        recs.append(
            "Speed-dominant: spend the block on aerobic durability and consistency, not chasing peak "
            f"mileage — {pronouns.possessive} VDOT ceiling hasn't moved with volume historically"
        )
    elif fit.responder == "stable":
        recs.append("Fitness is stable and not volume-driven — protect consistency over peak mileage")
    elif fit.responder == "volume-sensitive":
        recs.append("Volume-sensitive: mileage has paid off in VDOT before — a real ramp is justified")

    # Goal realism → which goal to anchor on.
    on_track = [g for g in goals if g.verdict in ("within_current", "in_reach")]
    stretch = [g for g in goals if g.verdict in ("stretch", "unrealistic")]
    if on_track:
        best = min(on_track, key=lambda g: g.goal_time_s)  # fastest in-reach time = most ambitious defensible
        recs.append(f"Most ambitious defensible goal: {best.label} ({rd._fmt_clock(best.goal_time_s)})")
    if stretch:
        s = min(stretch, key=lambda g: g.goal_time_s)  # surface the toughest (fastest) stretch goal
        recs.append(
            f"{s.label} ({rd._fmt_clock(s.goal_time_s)}) is a {s.verdict} — needs VDOT {s.required_vdot} "
            f"(realistic ~{rd._fmt_clock(s.realistic_time_s)}); confirm with the early tune-ups before committing paces"
        )

    if anchor.stale:
        recs.append(
            "Fitness anchor is stale — the scheduled tune-up ladder is the instrument to re-measure VDOT; "
            "treat current paces as provisional until the first result lands"
        )
    return recs


def proposed_inputs(
    vol: VolumeProfile,
    *,
    current_opener_mpw: float | None,
    injury_prone: bool,
) -> list[ProposedInput]:
    """Turn the dossier's defensible signals into concrete `AthleteInputs` changes for coach review.

    Conservative on purpose: it only proposes what the data backs cleanly. Today that's the re-entry
    opener — anchoring `reentry_start_mpw` on the volume the athlete has actually opened a block at,
    when the current plan opens meaningfully lower. Goal re-anchoring stays a coach conversation (we
    never auto-propose changing someone's goal), and responder framing is advisory prose, not a field
    flip. Extend here as more signals earn a clean field mapping."""
    out: list[ProposedInput] = []
    if vol.demonstrated_opener_mpw > 0 and current_opener_mpw is not None and (
        current_opener_mpw + 1.5 < vol.demonstrated_opener_mpw
    ):
        why = (
            f"Last block opened near ~{vol.demonstrated_opener_mpw:g} mpw, but the current plan opens at "
            f"only {current_opener_mpw:g} mpw — anchor the re-entry on demonstrated volume."
        )
        if injury_prone:
            why += " Ramp from there cautiously given injury history."
        out.append(
            ProposedInput(
                field="reentry_start_mpw",
                value=round(vol.demonstrated_opener_mpw),
                rationale=why,
                current=round(current_opener_mpw, 1),
            )
        )
    return out


def build_dossier(
    name: str,
    *,
    volume_weeks: list[WeeklyVolume],
    races: list[RacePerformance],
    feed_weeks: list[WeeklyVolume] | None,
    current_vdot: float,
    goals: list[tuple[str, int]],
    source_date: str | None,
    build_weeks: int,
    today: date,
    injury_prone: bool = False,
    current_opener_mpw: float | None = None,
    pronouns: str | None = None,
) -> AthleteDossier:
    """Assemble the full dossier from parsed history. Pure — same inputs always yield the same dossier.

    ``pronouns`` (e.g. ``"she/her"``) only shapes the coach-facing recommendation prose; unset falls
    back to gender-neutral ``they/their``.
    """
    if feed_weeks:
        attach_trailing_volume(races, feed_weeks)
    vol = build_volume_profile(volume_weeks)
    fit = build_fitness_timeline(races, current_vdot)
    goal_rows = assess_goals(current_vdot, goals, build_weeks=max(1, build_weeks))
    anchor = anchor_confidence(current_vdot, source_date, today=today)
    recs = _recommendations(
        vol, fit, goal_rows, anchor, injury_prone=injury_prone,
        current_opener_mpw=current_opener_mpw, pronouns=resolve_pronouns(pronouns),
    )
    proposals = proposed_inputs(vol, current_opener_mpw=current_opener_mpw, injury_prone=injury_prone)
    return AthleteDossier(
        name=name, volume=vol, fitness=fit, goals=goal_rows, anchor=anchor,
        recommendations=recs, proposed_inputs=proposals,
    )


def race_from_detected(row: dict) -> RacePerformance | None:
    """Build a `RacePerformance` from an `all_races_detected` row (computes VDOT). None if unusable."""
    try:
        dist_m = float(row["distance_mi"]) * common.METERS_PER_MILE
        time_s = int(row["duration_s"])
    except (KeyError, ValueError, TypeError):
        return None
    if dist_m <= 0 or time_s <= 0:
        return None
    v = vdot_from_race(dist_m, time_s)
    if v is None:
        return None
    return RacePerformance(
        date=str(row.get("date") or "")[:10],
        name=str(row.get("name") or "race"),
        category=str(row.get("category") or _nearest_category(dist_m)),
        distance_m=round(dist_m, 1),
        time_s=time_s,
        vdot=round(v, 1),
    )


def race_from_tune_up(
    distance_m: float, time_s: int, vdot: float, race_date: str, *, name: str = "tune-up"
) -> RacePerformance | None:
    """Build a `RacePerformance` from a recorded ``TuneUpResult`` event. The VDOT is the one the
    coach command already measured at write time, so this stays pure (no recompute). None if the
    inputs are unusable. Used to fold real tune-up results into the dossier's fitness timeline so a
    fresh tune-up resolves a stale anchor."""
    try:
        dist_m = float(distance_m)
        t_s = int(time_s)
        v = float(vdot)
    except (ValueError, TypeError):
        return None
    if dist_m <= 0 or t_s <= 0 or v <= 0:
        return None
    return RacePerformance(
        date=str(race_date or "")[:10],
        name=name,
        category=_nearest_category(dist_m),
        distance_m=round(dist_m, 1),
        time_s=t_s,
        vdot=round(v, 1),
    )


def _nearest_category(distance_m: float) -> str:
    return min(RACE_METERS, key=lambda k: abs(RACE_METERS[k] - distance_m))
