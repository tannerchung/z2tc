"""Workout catalog + purposeful rotation (deterministic).

The **z2tc rotation catalog** — the named, varied sessions the Daniels generator rotates
through so a block is not three workouts on repeat (cruise intervals / VO2max / "marathon
long run"). Each entry is a small builder over a :class:`WeekContext`, grouped into ordered
per-phase rotations. "Rotate with purpose" means the order is **deterministic and
phase-appropriate**, not random: the Threshold phase cycles T-pace formats (same lactate
stimulus, different feel); Race Prep cycles VO2max/Rep sharpeners; and the long run climbs in
specificity (Daniels' E/M/T blend → marathon-pace blocks → fast finish). The generator owns
*when* to call a rotation (e.g. deferring VO2max off mileage step-up weeks); this module owns
*what* the rotation contains. Keeping the catalog here (not inline in ``daniels.py``) means the
sheet's Workout Dictionary is generated from the same source the engine runs (no drift).

The grid methods (Pfitzinger / Hansons / Higdon) don't use this rotation — they emit their own
verbatim labels — but every label any generator produces decodes through
``render.workout_glossary.explain_workout_label`` (cross-method coverage is locked by tests).

Sources behind the variety: Daniels' T (tempo vs cruise vs broken-T), I (intervals, pyramid,
descending) and R menus (Running Formula ch.4 / Table 4.2), plus the standard marathon long-run
family — marathon-pace blocks, fast-finish, and thirds progression (McMillan; Humphrey "Long Run
Variations"; SF Marathon "M-pace workouts"), all at Daniels paces.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import common
from .models import Workout


# --- Rotation catalog ------------------------------------------------------------
@dataclass(frozen=True)
class WeekContext:
    """Everything a catalog builder needs for one week, resolved by the generator."""

    caps: dict[str, float]   # session_caps(): T / M / I / R single-session mileage ceilings
    paces: dict              # training_paces(): threshold_s/threshold, interval_s/interval, rep_s/rep
    mp_s: int                # goal marathon pace, s/mi
    mp_str: str
    easy_s: int
    easy_str: str
    long_mi: float = 0.0     # the day's long-run distance (for long-run builders)


@dataclass(frozen=True)
class CatalogWorkout:
    key: str
    name: str                # athlete-facing name (matches the label prefix the engine emits)
    role: str                # "T" | "I" | "R" | "M" | "long"
    purpose: str             # what it's for (the Workout Dictionary definition)
    generation: str          # how the engine sizes/paces it (mileage cap + VDOT/goal pace)
    build: Callable[[WeekContext], Workout]


def _cruise_mile(c: WeekContext) -> Workout:
    return common.threshold_workout(c.caps["T"], c.paces["threshold_s"], c.paces["threshold"], style="cruise", rep_mi=1.0)


def _tempo(c: WeekContext) -> Workout:
    return common.threshold_workout(c.caps["T"], c.paces["threshold_s"], c.paces["threshold"], style="tempo")


def _broken_t(c: WeekContext) -> Workout:
    return common.threshold_workout(c.caps["T"], c.paces["threshold_s"], c.paces["threshold"], style="cruise", rep_mi=0.5)


def _over_unders(c: WeekContext) -> Workout:
    return common.over_under_workout(c.caps["T"], c.paces["threshold_s"], c.paces["threshold"], c.mp_s, c.mp_str)


def _tempo_ladder(c: WeekContext) -> Workout:
    return common.threshold_ladder_workout(c.caps["T"], c.paces["threshold_s"], c.paces["threshold"])


def _vo2_intervals(c: WeekContext) -> Workout:
    return common.interval_workout(c.caps["I"], c.paces["interval_s"], c.paces["interval"])


def _vo2_1200(c: WeekContext) -> Workout:
    return common.interval_workout(c.caps["I"], c.paces["interval_s"], c.paces["interval"], rep_m=1200)


def _vo2_pyramid(c: WeekContext) -> Workout:
    return common.interval_ladder_workout(c.caps["I"], c.paces["interval_s"], c.paces["interval"])


def _descending_i(c: WeekContext) -> Workout:
    return common.descending_intervals_workout(c.caps["I"], c.paces["interval_s"], c.paces["interval"])


def _drop_set(c: WeekContext) -> Workout:
    return common.drop_set_workout(c.caps["I"], c.paces["interval_s"], c.paces["interval"])


def _speed_reps(c: WeekContext) -> Workout:
    return common.rep_workout(c.caps["R"], c.paces["rep_s"], c.paces["rep"])


def _short_reps(c: WeekContext) -> Workout:
    return common.rep_workout(c.caps["R"], c.paces["rep_s"], c.paces["rep"], rep_m=200)


def _rolling_400s(c: WeekContext) -> Workout:
    return common.rolling_reps_workout(c.caps["R"], c.paces["rep_s"], c.paces["rep"])


def _mp_reps(c: WeekContext) -> Workout:
    # Trim hard for a low-fatigue taper/race-week sharpener (~3 mi of goal pace, like Runna's
    # "Race Pace Practice Half Miles") — never a workout that needs recovering from.
    return common.mp_reps_workout(min(c.caps["M"], 3.0), c.mp_s, c.mp_str)


def _mp_run(c: WeekContext) -> Workout:
    return common.marathon_pace_run(c.caps["M"], c.mp_s, c.mp_str)


def _mp_blend(c: WeekContext) -> Workout:
    return common.marathon_q1_workout(
        c.long_mi, c.caps["M"], c.mp_s, c.mp_str,
        c.paces["threshold_s"], c.paces["threshold"], c.easy_s, c.easy_str,
    )


def _progression(c: WeekContext) -> Workout:
    return common.progression_long_run(c.long_mi, c.easy_s, c.easy_str, c.mp_s, c.mp_str)


def _mp_blocks(c: WeekContext) -> Workout:
    return common.mp_blocks_long_run(c.long_mi, c.caps["M"], c.mp_s, c.mp_str, c.easy_s, c.easy_str)


def _fast_finish(c: WeekContext) -> Workout:
    return common.fast_finish_long_run(c.long_mi, c.caps["M"], c.easy_s, c.easy_str, c.mp_s, c.mp_str)


def _race_practice(c: WeekContext) -> Workout:
    return common.race_practice_long_run(c.long_mi, c.caps["M"], c.mp_s, c.mp_str, c.easy_s, c.easy_str)


def _long_easy(c: WeekContext) -> Workout:
    return common.long_run_easy(c.long_mi, c.easy_s, c.easy_str)


def _long_fartlek(c: WeekContext) -> Workout:
    return common.long_run_fartlek(c.long_mi, c.easy_s, c.easy_str)


CATALOG_WORKOUTS: tuple[CatalogWorkout, ...] = (
    # --- Threshold (T): comfortably-hard, lactate-clearance. Pace = VDOT T; volume ≤ 10% week.
    CatalogWorkout("cruise_mile", "Cruise intervals", "T",
                   "Mile threshold repeats with short 60 s jogs that bank T volume above a 20-min tempo (Daniels p.67).",
                   "reps = (10%-week T cap) ÷ 1 mi, at VDOT threshold pace, 60 s jog between.", _cruise_mile),
    CatalogWorkout("tempo", "Tempo run", "T",
                   "One continuous comfortably-hard effort at threshold for confidence and lactate clearance (Daniels).",
                   "single block capped at ~20 min (T cap if shorter), at VDOT threshold pace.", _tempo),
    CatalogWorkout("broken_t", "Broken-T intervals", "T",
                   "Half-mile threshold repeats for more reps at the same T stimulus with a sharper feel (Daniels).",
                   "reps = T cap ÷ 0.5 mi, at VDOT threshold pace, 60 s jog.", _broken_t),
    CatalogWorkout("over_unders", "Over/unders", "T",
                   "Alternate threshold (over) and marathon pace (under), nonstop, for rhythm changes at race paces (Runna).",
                   "≈ T-cap reps of 0.5 mi @ T / 0.5 mi @ goal MP, nonstop.", _over_unders),
    CatalogWorkout("tempo_ladder", "Threshold ladder", "T",
                   "Descending threshold blocks (long to short) with 60 s jogs for the same T effort in a varied shape (Runna 2-1-1).",
                   "T cap split 50/25/25 into 3 blocks at VDOT threshold pace, 60 s jog.", _tempo_ladder),
    # --- Interval (I): VO2max / aerobic power. Pace = VDOT I; volume ≤ 8% week (≤10 km).
    CatalogWorkout("vo2_intervals", "VO2max intervals", "I",
                   "1000 m reps at about 5K effort with equal-time jog for VO2max and aerobic power (Daniels I).",
                   "reps = (8%-week I cap) ÷ 1000 m, at VDOT interval pace, equal-time jog.", _vo2_intervals),
    CatalogWorkout("vo2_1200", "VO2max intervals (1200s)", "I",
                   "1200 m reps at I pace, Daniels' preferred VO2max rep for slower runners (3 to 5 min work).",
                   "reps = I cap ÷ 1200 m, at VDOT interval pace, equal-time jog.", _vo2_1200),
    CatalogWorkout("vo2_pyramid", "VO2max pyramid", "I",
                   "400-800-1200-800-400 m pyramid at I pace for the same VO2max stimulus in varied rep lengths.",
                   "fixed pyramid (~3.6 km work) at VDOT interval pace, equal-time jog; wu/cd absorbs cap.", _vo2_pyramid),
    CatalogWorkout("descending_i", "Descending intervals", "I",
                   "1200-1000-800-600-400 m at I pace, where shortening reps keep pace honest as fatigue builds.",
                   "fixed descending set at VDOT interval pace, equal-time jog.", _descending_i),
    CatalogWorkout("drop_set", "Drop set", "I",
                   "1000-800-600-400-200 m descending ladder at I pace, short and sharp with a fast finish (Runna).",
                   "fixed drop ladder at VDOT interval pace, equal-time jog.", _drop_set),
    # --- Repetition (R): speed + economy. Pace = VDOT R; volume ≤ 5% week (≤5 mi).
    CatalogWorkout("speed_reps", "Speed reps", "R",
                   "Short fast 400 m reps at Rep pace with full recovery for speed and running economy (Daniels R).",
                   "reps = (5%-week R cap) ÷ 400 m, at VDOT rep pace, full 400 m jog.", _speed_reps),
    CatalogWorkout("short_reps", "Speed reps (200s)", "R",
                   "200 m reps at Rep pace for pure turnover and neuromuscular work (Daniels p.135).",
                   "reps = R cap ÷ 200 m (≥8), at VDOT rep pace, full 200 m jog.", _short_reps),
    CatalogWorkout("rolling_400s", "Rolling 400s", "R",
                   "400 m reps at Rep pace with only a 200 m jog float for continuous rhythm and turnover (Runna).",
                   "reps = R cap ÷ 400 m, at VDOT rep pace, short 200 m jog (no full recovery).", _rolling_400s),
    # --- Marathon pace (M): goal-pace rehearsal. Pace = goal MP (from A-goal time).
    CatalogWorkout("mp_reps", "Race-pace reps", "M",
                   "Short half-mile reps at goal marathon pace with 60 s jog, a low-fatigue race-rhythm rehearsal for the taper (Runna).",
                   "reps = (trimmed M cap, ≤3 mi) ÷ 0.5 mi, at goal MP, 60 s jog.", _mp_reps),
    CatalogWorkout("mp_run", "Race-pace run", "M",
                   "Continuous goal-marathon-pace miles, a midweek race-practice run for goal pace, rhythm and fueling (Pfitzinger MP; Higdon pace run).",
                   "min(M cap, 6 mi) continuous at goal MP, with an easy warm-up and cool-down.", _mp_run),
    # --- Long runs: sized by daniels_long_run (time-on-feet / 30-25% share / 18-mi cap).
    CatalogWorkout("long_easy", "Long run (easy)", "long",
                   "Steady aerobic long run for time on feet and durability (all four authors' staple).",
                   "distance = min(3 h time-on-feet at observed long pace, 18 mi, 30–25% of week); all easy.", _long_easy),
    CatalogWorkout("long_fartlek", "Long run w/ fartlek", "long",
                   "Easy long run with brief ~1 min surges sprinkled in for light turnover that breaks up the run (Humphrey).",
                   "same easy long-run distance; ~one 1-min surge per 1.5 mi (stays an aerobic day).", _long_fartlek),
    CatalogWorkout("mp_blend", "Marathon long run", "long",
                   "Daniels 2Q nonstop E/M/(T)/M/E blend that banks race-pace volume inside the long run (Table 14.3).",
                   "long-run distance; ~half at goal MP (≤ M cap) with a 1-mi T surge, rest easy.", _mp_blend),
    CatalogWorkout("progression", "Progression long run", "long",
                   "Thirds that build easy to steady to marathon pace for pacing discipline and a low-risk strong finish (Humphrey/Higdon 3/1).",
                   "long-run distance split in thirds, easy then steady (E↔MP midpoint) then goal MP.", _progression),
    CatalogWorkout("mp_blocks", "Marathon-pace blocks", "long",
                   "Two MP blocks split by an easy float for race rhythm, fueling rehearsal and more banked MP (Runna 'Block').",
                   "long-run distance; 2 × (≈25%, ≤ M cap/2) blocks at goal MP, 1-mi easy float, easy wu/cd.", _mp_blocks),
    CatalogWorkout("fast_finish", "Fast-finish long run", "long",
                   "Mostly easy and closed at marathon pace for late-race grit, kept controlled (McMillan; Humphrey).",
                   "long-run distance; final block (≤ M cap, ≤40%) at goal MP, rest easy.", _fast_finish),
    CatalogWorkout("race_practice", "Race-practice long run", "long",
                   "A dress rehearsal with one sustained MP block (the build's longest) for goal pace, fueling and kit (Pfitzinger; Runna).",
                   "long-run distance; one continuous MP block = min(M cap, distance − 3 mi), easy wu/cd.", _race_practice),
)

_BY_KEY = {w.key: w for w in CATALOG_WORKOUTS}

# Ordered, deterministic rotations. Phase decides the menu; an occurrence counter (kept by the
# generator) decides the position — so the same week always yields the same session. Q1 (long run)
# only ever pulls from the "long" role; Q2 (midweek) pulls T in the Threshold phase and the
# I/R sharpeners in Race Prep.
# Base-phase midweek quality, eased in: lead with low-fatigue Reps (R — speed/economy, full
# recovery; Daniels' Phase II staple) before a short Threshold, so the first quality of the block
# is gentle on a rebuilding aerobic base.
BASE_Q2: tuple[str, ...] = ("speed_reps", "cruise_mile", "tempo")
THRESHOLD_Q2: tuple[str, ...] = ("cruise_mile", "tempo", "broken_t", "over_unders", "tempo_ladder")
RACE_PREP_Q2: tuple[str, ...] = ("vo2_intervals", "drop_set", "vo2_pyramid", "vo2_1200",
                                 "descending_i", "rolling_400s", "speed_reps")
TAPER_Q2: tuple[str, ...] = ("cruise_mile", "mp_reps")  # short T touch, then a race-pace sharpener
BASE_LONG: tuple[str, ...] = ("long_easy", "long_fartlek")
LONG_RUN: dict[str, tuple[str, ...]] = {
    # Build specificity through the block: a race-pace blend early, then split MP blocks and a
    # controlled fast finish as race day nears (Threshold rotates blend ↔ progression). The final
    # Race-Prep long run is the dress rehearsal (race_practice), selected by the generator.
    "Threshold": ("mp_blend", "progression"),
    "Race Prep": ("mp_blocks", "fast_finish", "mp_blend"),
}


def base_q2(occ: int, ctx: WeekContext) -> Workout:
    return _BY_KEY[BASE_Q2[occ % len(BASE_Q2)]].build(ctx)


def threshold_q2(occ: int, ctx: WeekContext) -> Workout:
    return _BY_KEY[THRESHOLD_Q2[occ % len(THRESHOLD_Q2)]].build(ctx)


def race_prep_q2(occ: int, ctx: WeekContext) -> Workout:
    return _BY_KEY[RACE_PREP_Q2[occ % len(RACE_PREP_Q2)]].build(ctx)


def taper_q2(occ: int, ctx: WeekContext) -> Workout:
    return _BY_KEY[TAPER_Q2[occ % len(TAPER_Q2)]].build(ctx)


def base_long(occ: int, ctx: WeekContext) -> Workout:
    return _BY_KEY[BASE_LONG[occ % len(BASE_LONG)]].build(ctx)


def long_run_for_phase(phase: str, occ: int, ctx: WeekContext) -> Workout:
    keys = LONG_RUN[phase]
    return _BY_KEY[keys[occ % len(keys)]].build(ctx)


def named(key: str, ctx: WeekContext) -> Workout:
    """Build one catalog session by key (e.g. the final ``race_practice`` dress rehearsal)."""
    return _BY_KEY[key].build(ctx)
