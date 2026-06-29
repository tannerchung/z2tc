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
    returning_marathoner: bool = False
    race_fit: bool = True
    recent_break_days: int | None = None
    cross_trained_during_break: bool = False
    cross_training_note: str | None = None
    cross_training_days: tuple[str, ...] = ()
    cross_training_minutes: int = 45
    last_marathon_date: str | None = None
    last_marathon_time_s: int | None = None
    decayed_peak_mpw: float | None = None
    method: str | None = None
    block_weeks: int = 18
    race_name: str = "Marathon"
    coach_floor_mpw: float | None = None
    coach_target_mpw: float | None = None
    # Per-athlete coach overrides. These have no Google-Form question; they are tuned by the
    # coach and persisted on the baseline so a replan reproduces the plan faithfully (the
    # alternative is one ManualOverride event each). All map 1:1 to AthleteInputs.
    aggressive_volume_ramp: bool | None = None  # None -> club resolves (ClubPolicy.allow_aggressive_ramp); True/False = coach choice
    long_run_share_cap: float | None = None  # None -> club default (0.50); coach raises it for a long-run-dominant athlete
    long_run_cap_mi: float | None = None
    long_run_peak_weeks: int | None = None
    quality_long_runs_race_prep_only: bool = False
    strides_per_phase: int | None = None
    weekday_quality_sessions: int | None = None
    recent_sustained_mpw: float | None = None
    reentry_start_mpw: float | None = None
    observed_long_pace_s: int | None = None
    higdon_program: str | None = None
    hanson_program: str | None = None
    append_post_marathon_recovery: bool = False
    emit_peak_scenarios: bool = False
    easy_pace_override_s: int | None = None
    secondary_races: list[MarathonRaceIn] = Field(default_factory=list)
    email: str | None = None
    birthday: str | None = None
    instagram_handle: str | None = None
    # Presentation only (coach-facing dossier prose). No Google-Form question; the coach marks it.
    # Filtered out by `to_athlete_inputs`, so it never reaches the plan engine. E.g. "she/her".
    pronouns: str | None = None
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


class Season(BaseModel):
    """One marathon block for an athlete: its own baseline, event log, and plan artifacts.

    The athlete is the person; a season is a training cycle keyed to one A-race. Carrying
    fitness forward into the next season seeds a fresh baseline from the prior season's
    ending state (see ``store.carryforward``). ``status``: ``planned`` | ``active`` |
    ``archived``. Exactly one ``active`` season per athlete is the replan/publish target.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    label: str
    race_date: str | None = None
    status: str = "active"
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


class TrainingBlock(BaseModel):
    """A snapshot of a scraped historical marathon training block, kept for athlete profiling.

    This is **descriptive history**, not a plan: the raw week-by-week scrape (``weeks``), the
    derived ``report``, and a computed ``profile`` of demonstrated capacity (run-days/wk, peak
    mileage, longest run, long-run share — see ``engine.analyze.compute_capacity_profile``). It is
    athlete-scoped rather than season-scoped because completed blocks predate the seasons we plan,
    and it is intentionally **not** wired into the engine yet — we store it so we can later reason
    about how hard a given runner can be pushed. ``id`` is deterministic per (athlete, marathon)
    so re-scraping the same block refreshes one row rather than accumulating duplicates; distinct
    marathons accumulate over time.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    strava_athlete_id: str | None = None
    source: str = "strava"
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    marathon_date: str | None = None
    marathon_name: str | None = None
    marathon_time_s: int | None = None
    block_start: str | None = None
    block_end: str | None = None
    weeks: list[dict[str, Any]] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    profile: dict[str, Any] = Field(default_factory=dict)


class PlanArtifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    season_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inputs_hash: str
    plan_json: dict[str, Any]
    # Resolved AthleteInputs (baseline + folded events) that produced ``plan_json``. Makes a
    # plan self-describing/rebuildable even if fold logic later changes. None for legacy rows.
    resolved_inputs: dict[str, Any] | None = None
    # Plan-engine semantic version (``engine.plan.ENGINE_VERSION``) that produced ``plan_json``.
    # None for rows written before engine versioning existed.
    engine_version: str | None = None
    # Club-policy version (``engine.plan.club.ClubPolicy.version``) in force when the plan was built,
    # so a house-rule change is attributable distinctly from an engine change. None for legacy rows.
    club_policy_version: str | None = None


class DossierSnapshot(BaseModel):
    """An append-only capture of an athlete's `AthleteDossier` at a point in time.

    The dossier itself is computed on demand and pure; persisting a snapshot every time we report or
    publish lets the club accumulate the personalization signals (responder profile, demonstrated
    volume band, volume↔VDOT slope, endurance gap, anchor staleness) across seasons, so a pattern
    has to *earn* an engine/policy change by showing up in the data first (see Phase 3 analytics).
    ``full_json`` is the whole dossier; the flattened columns mirror the signals the fleet analytics
    query directly. ``inputs_fingerprint`` ties the snapshot to the inputs that produced it.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    season_id: str | None = None
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dossier_version: str | None = None
    inputs_fingerprint: str = ""
    full_json: dict[str, Any] = Field(default_factory=dict)
    # Flattened query columns (mirror AthleteDossier signals).
    responder: str | None = None
    demonstrated_opener_mpw: float | None = None
    peak_mpw: float | None = None
    sustainable_low_mpw: float | None = None
    sustainable_high_mpw: float | None = None
    volume_vdot_corr: float | None = None
    endurance_gap: float | None = None
    current_vdot: float | None = None
    anchor_age_days: int | None = None
    anchor_stale: bool | None = None
    injury_prone: bool | None = None


class Publication(BaseModel):
    """A record that a specific plan artifact was published to a sheet at a point in time.

    Closes the lineage loop: it ties the published surface back to the exact ``plan_artifact_id``
    (and the engine/template/prompt/model versions in force), so a later reader can answer "which
    plan, built by which engine, with which narrative, did this sheet show?". Append-only.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    athlete_id: str
    season_id: str | None = None
    plan_artifact_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spreadsheet_id: str | None = None
    sheet_title: str | None = None
    url: str | None = None
    engine_version: str | None = None
    template_version: str | None = None
    prompt_version: str | None = None
    llm_model: str | None = None
    narrative_source: str | None = None   # "deterministic" | "llm" | "mixed"
    rows_written: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
