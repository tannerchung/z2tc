"""Typed event vocabulary for append-only event sourcing (see docs/architecture/event-sourcing.md)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

EventSource = Literal["coach", "strava", "sheet", "llm"]
EventStatus = Literal["proposed", "approved", "applied", "rejected"]


class InjuryPayload(BaseModel):
    kind: Literal["Injury"] = "Injury"
    area: str
    severity: int = Field(ge=1, le=5)
    days_off: int | None = None


class UnavailablePayload(BaseModel):
    kind: Literal["Unavailable"] = "Unavailable"
    start: str  # ISO date
    end: str
    reason: str = ""


class SetDaysPayload(BaseModel):
    kind: Literal["SetDays"] = "SetDays"
    n: int = Field(ge=3, le=7)
    preferred: str | None = None  # e.g. "Sat" long run preference (future)


class DifficultyPayload(BaseModel):
    kind: Literal["Difficulty"] = "Difficulty"
    delta: int = Field(ge=-2, le=2)


class SetGoalPayload(BaseModel):
    kind: Literal["SetGoal"] = "SetGoal"
    goal_marathon_s: int = Field(gt=0)


class SetRaceDatePayload(BaseModel):
    kind: Literal["SetRaceDate"] = "SetRaceDate"
    race_date: str


class ManualOverridePayload(BaseModel):
    kind: Literal["ManualOverride"] = "ManualOverride"
    field: str
    value: Any


class AdherenceFlagPayload(BaseModel):
    kind: Literal["AdherenceFlag"] = "AdherenceFlag"
    week_start: str
    prescribed_mi: float
    actual_mi: float
    ratio: float


class EasyPaceDriftPayload(BaseModel):
    kind: Literal["EasyPaceDrift"] = "EasyPaceDrift"
    week_start: str
    drift_s_per_mi: float


class MissedQualityPayload(BaseModel):
    kind: Literal["MissedQuality"] = "MissedQuality"
    week_index: int
    day: str
    expected_label: str


class LongRunIncompletePayload(BaseModel):
    kind: Literal["LongRunIncomplete"] = "LongRunIncomplete"
    week_index: int
    prescribed_mi: float
    actual_mi: float


class FatigueFlagPayload(BaseModel):
    kind: Literal["FatigueFlag"] = "FatigueFlag"
    week_start: str
    reason: str


class OverreachFlagPayload(BaseModel):
    kind: Literal["OverreachFlag"] = "OverreachFlag"
    week_start: str
    reason: str


class TuneUpResultPayload(BaseModel):
    kind: Literal["TuneUpResult"] = "TuneUpResult"
    distance_m: float
    time_s: int
    new_vdot: float


class CoachNotePayload(BaseModel):
    """Free-text coach observation attached to an athlete (provenance only — surfaces as a
    plan flag, never changes the numbers on its own)."""

    kind: Literal["CoachNote"] = "CoachNote"
    text: str
    tags: list[str] = Field(default_factory=list)


class RaceEstimatePayload(BaseModel):
    """Coach's effort-corrected read of a known race (e.g. a marathon run sick, or a
    submaximal tune-up). ``estimated_vdot`` is the fitness that race *really* showed;
    ``effective_vdot`` is that estimate detrained to today (Daniels Table 15.1) and is what a
    replan folds into ``vdot``. Both VDOTs are computed by the coach-note command at write
    time so the plan engine stays pure."""

    kind: Literal["RaceEstimate"] = "RaceEstimate"
    race_name: str
    race_date: str               # ISO date of the race
    distance_m: float
    actual_time_s: int | None = None   # as recorded on Strava, if known
    estimated_time_s: int              # coach's effort-corrected finish time
    estimated_vdot: float              # VDOT at estimated_time_s (the trained-peak read)
    effective_vdot: float              # estimated_vdot detrained to now (current fitness)
    break_days: int = 0                # days-off used for the detraining factor
    note: str = ""


class EffortQualityPayload(BaseModel):
    """Coach tag on a known race: how hard was it actually run. Non-``max`` efforts are
    dropped from VDOT selection (a submaximal tune-up shouldn't set fitness)."""

    kind: Literal["EffortQuality"] = "EffortQuality"
    race_date: str                                          # ISO date of the race
    quality: Literal["max", "submaximal", "compromised"]
    note: str = ""


class DataExcludePayload(BaseModel):
    """Coach directive to ignore a data point in fitness/volume reads (bad GPS, mismeasure,
    a casual jog logged as a race)."""

    kind: Literal["DataExclude"] = "DataExclude"
    race_date: str
    reason: str = ""


class FitnessAnchorPayload(BaseModel):
    """The resolved fitness read for the block. Either pins a race (``race_date``) or carries
    the resolved ``vdot`` (already detrained to today). The ``fitness-select`` resolver writes
    one of these from the candidate races + directives; ``replan`` folds ``vdot`` into the
    baseline."""

    kind: Literal["FitnessAnchor"] = "FitnessAnchor"
    race_date: str | None = None
    vdot: float | None = None
    source: str = ""        # human-readable provenance, e.g. "Marathon 2025-10-11 (estimate)"
    note: str = ""


class WeeklyEvaluationPayload(BaseModel):
    """Coach weekly calibration: optional overrides folded into ``AthleteInputs`` before
    ``build_plan``. All fields optional so the event can carry a ``note`` only, or tune
    VDOT, coach-estimated current mpw (``w_now`` + ``reentry_start_mpw``), and easy pace."""

    kind: Literal["WeeklyEvaluation"] = "WeeklyEvaluation"
    week_start: str  # ISO Monday of the evaluation week
    calibrated_vdot: float | None = None
    estimated_mpw: float | None = None
    easy_pace_override_s: int | None = Field(default=None, ge=240, le=1200)
    note: str = ""


EventPayload = Annotated[
    Union[
        InjuryPayload,
        UnavailablePayload,
        SetDaysPayload,
        DifficultyPayload,
        SetGoalPayload,
        SetRaceDatePayload,
        ManualOverridePayload,
        AdherenceFlagPayload,
        EasyPaceDriftPayload,
        MissedQualityPayload,
        LongRunIncompletePayload,
        FatigueFlagPayload,
        OverreachFlagPayload,
        TuneUpResultPayload,
        CoachNotePayload,
        RaceEstimatePayload,
        EffortQualityPayload,
        DataExcludePayload,
        FitnessAnchorPayload,
        WeeklyEvaluationPayload,
    ],
    Field(discriminator="kind"),
]


class EventRecord(BaseModel):
    """One row in ``events`` — use ``Store.append_event`` with flattened fields."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: EventSource
    status: EventStatus = "applied"
    payload: EventPayload


def event_type_name(payload: EventPayload) -> str:
    return payload.kind


def parse_event_payload(data: dict) -> EventPayload:
    """Validate a JSON object into a discriminated payload."""
    kind = data.get("kind")
    table: dict[str, type[BaseModel]] = {
        "Injury": InjuryPayload,
        "Unavailable": UnavailablePayload,
        "SetDays": SetDaysPayload,
        "Difficulty": DifficultyPayload,
        "SetGoal": SetGoalPayload,
        "SetRaceDate": SetRaceDatePayload,
        "ManualOverride": ManualOverridePayload,
        "AdherenceFlag": AdherenceFlagPayload,
        "EasyPaceDrift": EasyPaceDriftPayload,
        "MissedQuality": MissedQualityPayload,
        "LongRunIncomplete": LongRunIncompletePayload,
        "FatigueFlag": FatigueFlagPayload,
        "OverreachFlag": OverreachFlagPayload,
        "TuneUpResult": TuneUpResultPayload,
        "CoachNote": CoachNotePayload,
        "RaceEstimate": RaceEstimatePayload,
        "EffortQuality": EffortQualityPayload,
        "DataExclude": DataExcludePayload,
        "FitnessAnchor": FitnessAnchorPayload,
        "WeeklyEvaluation": WeeklyEvaluationPayload,
    }
    cls = table.get(kind or "")
    if cls is None:
        raise ValueError(f"unknown event kind: {kind!r}")
    return cls.model_validate(data)  # type: ignore[return-value]
