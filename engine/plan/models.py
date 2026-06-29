"""Shared data model for the plan engine.

One vocabulary that the Daniels, Pfitzinger, and Higdon generators all emit, so a renderer
(and the regression tests) only ever deal with one shape. ``AthleteInputs`` is the engine's
contract; everything else is output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MARATHON_M = 42195.0

# Calendar week Mon..Sun. Long run day is Saturday (see ``common.LONG_RUN_DAY``).
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class MarathonRace:
    """A marathon on the athlete calendar (primary = plan anchor: block length + taper)."""

    name: str
    date: str                      # ISO YYYY-MM-DD


@dataclass(frozen=True)
class TuneUpRace:
    """A shorter race scheduled inside the build as a fitness checkpoint (e.g. 5K/10K). The club
    post-process (`place_tune_up_races`) seats it on the long-run day of ``week`` (a mini-cutback
    week so it's run fresh); ``target_time_s`` is the advisory on-track time for the marathon goal
    (display only — it never changes the prescribed paces). Built by the club engine from the
    readiness tune-up ladder, or set explicitly by a coach. See engine/plan/club.py and
    engine/readiness.tune_up_ladder."""

    week: int                      # 1-based plan week the race lands in (long-run slot)
    distance_m: float              # 5000 / 10000 / 21097.5 ...
    label: str                     # short distance label, e.g. "10K"
    target_time_s: int | None = None  # on-track-for-goal time at this distance (advisory)


class WorkoutKind(str, Enum):
    REST = "rest"
    EASY = "easy"
    LONG = "long"
    MARATHON_PACE = "marathon_pace"
    THRESHOLD = "threshold"
    INTERVAL = "interval"
    REP = "rep"
    MEDIUM_LONG = "medium_long"
    GENERAL_AEROBIC = "general_aerobic"
    RECOVERY = "recovery"
    STRIDES = "strides"
    RACE = "race"
    CROSS = "cross"  # non-running cross-training (minutes only; 0 running miles)


# Kinds that count as a "quality" (hard) session for structural checks.
QUALITY_KINDS = frozenset(
    {
        WorkoutKind.THRESHOLD,
        WorkoutKind.INTERVAL,
        WorkoutKind.REP,
        WorkoutKind.MARATHON_PACE,
        WorkoutKind.RACE,
    }
)


@dataclass(frozen=True)
class AthleteInputs:
    """Everything the engine needs. Sourcing these (Strava, a form, a config file) is a
    separate concern; the engine only sees this typed shape."""

    name: str
    vdot: float
    goal_marathon_s: int           # goal finish time for the **primary** marathon (seconds) -> MP
    w_now: float                   # current weekly mileage (last ~4 wk avg) — often from Strava
    p_history: float               # max mpw last marathon block — often from Strava
    longest_run_mi: float          # recent long run — often from Strava
    days_per_week: int
    race_date: str                 # **primary** A-race date, ISO "YYYY-MM-DD" (drives the block)
    injury_prone: bool = False
    returning_marathoner: bool = False
    last_marathon_date: str | None = None       # ISO; anchor block from Strava latest marathon
    last_marathon_time_s: int | None = None     # chip or Strava time at that marathon
    decayed_peak_mpw: float | None = None       # p_history after volume-capacity decay (advisory)
    # Fitness-clock / break context (Strava-derived at merge time). Feed the freshness +
    # Table 15.1 model in ``engine/readiness`` — they do NOT change the deterministic plan.
    recent_break_days: int | None = None        # longest gap of *not running* in the lead-up
    cross_trained_during_break: bool = False     # leg-aerobic cross-training during that gap (FVDOT-2)
    cross_training_note: str | None = None       # human summary, e.g. "Pilates/Swim/Ride (475 acts)"
    # Standing weekly cross-training (Pfitzinger ch.4, pp.203-204): non-running aerobic work seated
    # on these weekdays where they're otherwise rest. Adds cardiovascular fitness without the impact
    # of more mileage; running miles are unchanged (CROSS days carry 0 mi).
    cross_training_days: tuple[str, ...] = ()    # e.g. ("Fri",)
    cross_training_minutes: int = 45
    # Ramp start + observed pace. A race-fit returner re-enters *above* an off-season ``w_now``
    # (readiness Table 15.2), so the ramp doesn't start at an absurdly low week 1 — see
    # ``engine/readiness.recommended_reentry_volume`` and docs/architecture/athlete-readiness.md §4.
    race_fit: bool = True                        # returning/race-fit (re-enter above w_now) vs base-from-scratch
    recent_sustained_mpw: float | None = None    # a real recent multi-week mileage high (best re-entry signal)
    reentry_start_mpw: float | None = None       # explicit ramp-start override; None -> readiness recommendation
    observed_long_pace_s: int | None = None      # measured long-run pace s/mi (Strava); sizes the time-on-feet long run — VDOT still drives prescribed E/M/T/I
    # Coach/event override for easy pace (s/mi). When set, ``build_plan`` narrows Daniels easy
    # band around this midpoint so all generators share one easy reference without per-engine forks.
    easy_pace_override_s: int | None = None
    # Peak / comeback overrides (Daniels ramp + scenario generator).
    coach_floor_mpw: float | None = None         # raises fast-regain ceiling toward demonstrated capacity
    coach_target_mpw: float | None = None        # explicit peak target for volume ramp (overrides inferred peak)
    # Per-athlete coach overrides (set via ManualOverride events; default keeps book behavior).
    aggressive_volume_ramp: bool | None = None   # tri-state: None = unset (club resolves), True/False = explicit coach choice. When True, +1 mi/running-day EVERY week to peak (vs Daniels' 3-wk hold). The z2tc club engine resolves this from ClubPolicy.allow_aggressive_ramp — see engine/plan/club.py
    long_run_cap_mi: float | None = None         # let the long run build to this distance, over the 3 h / share caps (monitored)
    long_run_peak_weeks: int | None = None       # weeks held at long_run_cap_mi (default 3); ramps up to it before then
    quality_long_runs_race_prep_only: bool = False  # keep threshold long runs easy; quality longs only in race-prep (4-day load)
    strides_per_phase: int | None = None         # cap on stride weeks per phase (default common.STRIDES_PER_PHASE)
    weekday_quality_sessions: int | None = None  # midweek quality sessions in a build week (None/1 = pure Daniels 2Q single midweek quality; 2 adds a midweek race-pace run, except down weeks / weeks the long run is itself quality). The z2tc club engine defaults this to 2 — see engine/plan/club.py
    base_quality_ramp: bool | None = None  # tri-state: None = unset (club resolves), True/False = explicit coach choice. When True, ease a second quality into the Base phase (1 -> 2). Pure Daniels keeps Base aerobic; the club engine enables this for two-quality athletes
    long_run_share_cap: float | None = None  # max long-run fraction of the week (None = textbook 0.30/0.25; club raises to ~0.50 so low-mileage/3-day athletes still reach a real long run). Bounded by the time-on-feet / 18-mi caps regardless. See engine/plan/club.py
    tune_up_races: tuple[TuneUpRace, ...] | None = None  # tri-state: None = unset (club builds the readiness ladder), () = explicitly none, non-empty = coach-set checkpoints. Pure generator places each on its week's long-run slot. See engine/plan/club.py
    # Optional program keys for single-author engines (None -> engine default / recommender).
    higdon_program: str | None = None            # novice1 | novice2 | intermediate1 | intermediate2
    hanson_program: str | None = None            # just_finish | beginner | advanced
    append_post_marathon_recovery: bool = False  # append 5-wk Pfitz-style recovery after race week when True
    emit_peak_scenarios: bool = False            # when True, build_plan returns primary + 3 peak variants (Daniels)
    method: str | None = None      # force "daniels"/"pfitzinger"/"higdon"/"hanson"; None -> auto-assign
    block_weeks: int = 18
    race_name: str = "Marathon"
    # Other marathons the same season (e.g. NYC then Chicago). Block/taper still follow
    # ``race_date`` / ``race_name`` as the primary goal; secondaries are surfaced for UI/coach.
    secondary_races: tuple[MarathonRace, ...] = ()
    # ---------------------------------------------------------------------------
    # Google Form + coach intake (optional unless noted). Blank optional answers are
    # resolved by ``intake.resolve_intake_defaults`` — see docs/intake-and-engine.md.
    # ---------------------------------------------------------------------------
    email: str | None = None
    birthday: str | None = None                      # ISO YYYY-MM-DD
    instagram_handle: str | None = None
    strava_profile_url: str | None = None
    marathons_selected: tuple[str, ...] = ()         # checkbox labels from the form
    goal_marathon_b_s: int | None = None             # B goal seconds (parsed HH:MM)
    goal_marathon_c_s: int | None = None             # C goal seconds
    latest_half_race_text: str | None = None
    latest_half_time_s: int | None = None
    latest_marathon_race_text: str | None = None
    latest_marathon_time_s: int | None = None
    intake_training_start_date: str | None = None    # ISO; athlete-chosen block start
    intake_injury_notes: str | None = None           # raw form text; coach/merge sets injury_prone
    training_philosophy: str | None = None           # funsies | steady | all_out
    hard_quality_sessions_pref: str | None = None    # one | one_or_two | two | auto
    hard_session_intensity_pref: str | None = None  # easy | normal | hard
    long_run_frequency_pref: str | None = None       # minimal | weekly | extra_aerobic
    long_run_difficulty_pref: str | None = None      # easy | club | aggressive
    marathon_arrival_date: str | None = None         # ISO date for primary race travel
    marathon_departure_date: str | None = None
    marathon_stay_description: str | None = None
    social_carb_load: str | None = None              # yes | maybe | unknown
    social_shakeout: str | None = None
    # Closing-form free text (see docs/intake-and-engine.md). Engine ignores; merge/coach
    # uses for scheduling tips, deliverables, and secondary-race context.
    intake_races_vacations_notes: str | None = None  # races/vacations during the block
    intake_coaching_extras_notes: str | None = None  # nutrition, playlist, shoes, other tips
    secondary_marathon_notes: str | None = None      # extra context for B/secondary marathon
    free_notes: str | None = None                    # catch-all “anything else?”


def training_plan_goal_payload(inputs: AthleteInputs) -> dict:
    """Shape stored on ``TrainingPlan.goal`` (flat primary keys for simple readers).

    ``date`` is the goal (primary) race; ``final_race_date`` is the last race on the calendar
    (the later of primary and any secondary), which is what the renderer/execution use to anchor
    week dates. For a single race the two are equal."""
    secondary = [{"name": r.name, "date": r.date} for r in inputs.secondary_races]
    all_dates = [inputs.race_date] + [r.date for r in inputs.secondary_races if r.date]
    final = max((d for d in all_dates if d), default=inputs.race_date)
    return {
        "name": inputs.race_name,
        "date": inputs.race_date,
        "distance": "Marathon",
        "goal_time_s": inputs.goal_marathon_s,
        "secondary_marathons": secondary,
        "final_race_date": final,
    }


def secondary_marathon_flags(inputs: AthleteInputs) -> list[str]:
    """Ordering hints vs the primary A-race (block length still follows ``race_date``)."""
    from datetime import date

    flags: list[str] = []
    try:
        primary = date.fromisoformat(inputs.race_date)
    except ValueError:
        return ["invalid_primary_race_date"]
    for r in inputs.secondary_races:
        try:
            rd = date.fromisoformat(r.date)
        except ValueError:
            flags.append(f"invalid_secondary_race_date:{r.name}")
            continue
        if rd < primary:
            flags.append(
                f"secondary_before_primary: {r.name} ({r.date}) is before primary "
                f"{inputs.race_name} ({inputs.race_date}) — schedule recovery between races; "
                "generated block still keys off the primary race only."
            )
        elif rd > primary:
            flags.append(
                f"secondary_after_primary: {r.name} ({r.date}) follows primary "
                f"{inputs.race_name} ({inputs.race_date})."
            )
        else:
            flags.append(f"secondary_same_day_as_primary:{r.name}")
    return flags


@dataclass
class Segment:
    """A structured chunk of a workout, e.g. 5 x 1000 m @ I w/ 2:00 jog."""

    reps: int
    pace_label: str                # "T", "I", "R", "M", "E"
    pace_s: int | None = None      # per-mile seconds for the work pace
    distance_m: float | None = None
    duration_s: int | None = None
    recovery: str | None = None


@dataclass
class Workout:
    kind: WorkoutKind
    label: str
    distance_mi: float | None = None
    duration_min: int | None = None
    pace: str | None = None        # formatted per-mile "m:ss"
    pace_s: int | None = None
    segments: list[Segment] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def is_quality(self) -> bool:
        return self.kind in QUALITY_KINDS


@dataclass(frozen=True)
class GridCell:
    kind: WorkoutKind
    miles: float | None = None
    text: str | None = None
    segment_hints: list[dict] = field(default_factory=list)

    def to_workout(self, paces: dict, mp_s: int, mp_str: str, easy_s: int, easy_str: str) -> Workout:
        pace_s = None
        pace_str = None
        
        if self.kind == WorkoutKind.REST:
            return Workout(WorkoutKind.REST, self.text or "Rest")
        elif self.kind == WorkoutKind.CROSS:
            return Workout(WorkoutKind.CROSS, self.text or "Cross training (60 min)", duration_min=60)
        
        if self.kind in (WorkoutKind.EASY, WorkoutKind.LONG, WorkoutKind.RECOVERY, WorkoutKind.MEDIUM_LONG, WorkoutKind.GENERAL_AEROBIC, WorkoutKind.STRIDES):
            pace_s = easy_s
            pace_str = easy_str
        elif self.kind == WorkoutKind.MARATHON_PACE:
            pace_s = mp_s
            pace_str = mp_str
        elif self.kind == WorkoutKind.THRESHOLD:
            pace_s = paces.get("threshold_s")
            pace_str = paces.get("threshold")
        elif self.kind == WorkoutKind.INTERVAL:
            pace_s = paces.get("interval_s")
            pace_str = paces.get("interval")
        elif self.kind == WorkoutKind.REP:
            pace_s = paces.get("rep_s")
            pace_str = paces.get("rep")
        
        segments = []
        for hint in self.segment_hints:
            seg_pace_label = hint.get("pace_label", "E")
            seg_pace_s = None
            if seg_pace_label == "T":
                seg_pace_s = paces.get("threshold_s")
            elif seg_pace_label == "I":
                seg_pace_s = paces.get("interval_s")
            elif seg_pace_label == "R":
                seg_pace_s = paces.get("rep_s")
            elif seg_pace_label == "M":
                seg_pace_s = mp_s
            elif seg_pace_label == "E":
                seg_pace_s = easy_s
                
            segments.append(
                Segment(
                    reps=hint.get("reps", 1),
                    pace_label=seg_pace_label,
                    pace_s=seg_pace_s,
                    distance_m=hint.get("distance_m"),
                    duration_s=hint.get("duration_s"),
                    recovery=hint.get("recovery"),
                )
            )
            
        return Workout(
            kind=self.kind,
            label=self.text or f"{self.kind.value.capitalize()} run",
            distance_mi=self.miles,
            pace=pace_str,
            pace_s=pace_s,
            segments=segments,
        )


@dataclass(frozen=True)
class PlanScenarioMeta:
    """When a plan is one of several peak-mileage scenarios (e.g. P+0 / P+5 / P+10)."""

    scenario_id: str              # e.g. "P+0", "P+5", "P+10"
    target_peak_mpw: float
    reachable: bool = True
    flags: tuple[str, ...] = ()


@dataclass
class PlannedDay:
    day: str                       # one of DAY_NAMES
    workout: Workout

    @property
    def miles(self) -> float:
        return self.workout.distance_mi or 0.0

    @property
    def running_miles(self) -> float:
        """Exclude cross-training minutes-only days from weekly running totals."""
        if self.workout.kind == WorkoutKind.CROSS:
            return 0.0
        return self.workout.distance_mi or 0.0


@dataclass
class PlannedWeek:
    index: int                     # 1-based week number within the block
    phase: str
    label: str
    target_miles: float
    is_down_week: bool = False
    days: list[PlannedDay] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def planned_miles(self) -> float:
        return round(sum(d.miles for d in self.days), 1)

    @property
    def planned_running_miles(self) -> float:
        return round(sum(d.running_miles for d in self.days), 1)

    @property
    def quality_days(self) -> list[PlannedDay]:
        return [d for d in self.days if d.workout.is_quality]

    @property
    def long_run(self) -> PlannedDay | None:
        long_kinds = {WorkoutKind.LONG, WorkoutKind.MARATHON_PACE, WorkoutKind.MEDIUM_LONG}
        longs = [d for d in self.days if d.workout.kind in long_kinds]
        return max(longs, key=lambda d: d.miles) if longs else None


@dataclass
class TrainingPlan:
    athlete: str
    method: str
    goal: dict                     # primary keys + optional secondary_marathons (see training_plan_goal_payload)
    vdot: float
    paces: dict
    peak_miles: float
    block_weeks: int
    weeks: list[PlannedWeek] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # informational rationale/citations (not warnings)
    generated_at: str | None = None
    scenario: PlanScenarioMeta | None = None       # set when this plan is one of a peak scenario set
    sibling_scenarios: tuple["TrainingPlan", ...] = ()  # other scenarios from same build (empty for single)
