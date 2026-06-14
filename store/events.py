"""Typed event vocabulary for append-only event sourcing (see docs/architecture/event-sourcing.md)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

EventSource = Literal["coach", "strava", "sheet", "llm"]
EventStatus = Literal["proposed", "approved", "applied"]


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
    }
    cls = table.get(kind or "")
    if cls is None:
        raise ValueError(f"unknown event kind: {kind!r}")
    return cls.model_validate(data)  # type: ignore[return-value]
