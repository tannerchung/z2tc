"""Shared data model for the plan engine.

One vocabulary that both the Daniels and Pfitzinger generators emit, so a renderer (and
golden tests) only ever deal with one shape. ``AthleteInputs`` is the engine's contract;
everything else is output.
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
    method: str | None = None      # force "daniels"/"pfitzinger"; None -> auto-assign
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
    """Shape stored on ``TrainingPlan.goal`` (flat primary keys for simple readers)."""
    return {
        "name": inputs.race_name,
        "date": inputs.race_date,
        "distance": "Marathon",
        "goal_time_s": inputs.goal_marathon_s,
        "secondary_marathons": [{"name": r.name, "date": r.date} for r in inputs.secondary_races],
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


@dataclass
class PlannedDay:
    day: str                       # one of DAY_NAMES
    workout: Workout

    @property
    def miles(self) -> float:
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
    generated_at: str | None = None
