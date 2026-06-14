"""Pydantic models for the SQLite store (baseline survey, artifacts, athletes)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from engine.plan.models import AthleteInputs, MarathonRace


class MarathonRaceIn(BaseModel):
    name: str
    date: str  # ISO YYYY-MM-DD


class SurveyInputs(BaseModel):
    """Baseline merge payload; maps 1:1 to ``AthleteInputs`` after coercion."""

    name: str
    vdot: float
    goal_marathon_s: int
    w_now: float
    p_history: float
    longest_run_mi: float
    days_per_week: int
    race_date: str
    injury_prone: bool = False
    method: str | None = None
    block_weeks: int = 18
    race_name: str = "Marathon"
    secondary_races: list[MarathonRaceIn] = Field(default_factory=list)
    email: str | None = None
    birthday: str | None = None
    instagram_handle: str | None = None
    strava_profile_url: str | None = None
    marathons_selected: tuple[str, ...] = ()
    goal_marathon_b_s: int | None = None
    goal_marathon_c_s: int | None = None
    latest_half_race_text: str | None = None
    latest_half_time_s: int | None = None
    latest_marathon_race_text: str | None = None
    latest_marathon_time_s: int | None = None
    intake_training_start_date: str | None = None
    intake_injury_notes: str | None = None
    training_philosophy: str | None = None
    hard_quality_sessions_pref: str | None = None
    hard_session_intensity_pref: str | None = None
    long_run_frequency_pref: str | None = None
    long_run_difficulty_pref: str | None = None
    marathon_arrival_date: str | None = None
    marathon_departure_date: str | None = None
    marathon_stay_description: str | None = None
    social_carb_load: str | None = None
    social_shakeout: str | None = None
    intake_races_vacations_notes: str | None = None
    intake_coaching_extras_notes: str | None = None
    secondary_marathon_notes: str | None = None
    free_notes: str | None = None

    def to_athlete_inputs(self) -> AthleteInputs:
        d = self.model_dump()
        sec = d.pop("secondary_races") or []
        races = tuple(MarathonRace(r["name"], r["date"]) for r in sec)
        d["secondary_races"] = races
        allowed = set(AthleteInputs.__dataclass_fields__)
        filtered = {k: v for k, v in d.items() if k in allowed}
        return AthleteInputs(**filtered)


class Athlete(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strava_athlete_id: str | None = None
    name: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta: dict[str, Any] = Field(default_factory=dict)


class Activity(BaseModel):
    """One logged activity row (future: normalized from Strava scrape)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    activity_id: str | None = None
    start_date: str | None = None
    sport_type: str = "Run"
    payload: dict[str, Any] = Field(default_factory=dict)


class RaceResult(BaseModel):
    athlete_id: str
    distance_m: float
    time_s: int
    race_date: str
    name: str | None = None


class PlanArtifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inputs_hash: str
    plan_json: dict[str, Any]
