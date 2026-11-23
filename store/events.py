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
    race_date: str | None = None  # ISO date the tune-up was run; freshens the dossier fitness anchor


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


class FuelingLogPayload(BaseModel):
    """Per-activity intra-run & pre-run fueling telemetry parsed from Strava notes or Kip chat."""

    kind: Literal["FuelingLog"] = "FuelingLog"
    activity_id: str | None = None
    run_date: str = ""
    pre_run_carbs_g: float | None = Field(default=None, ge=0)
    gels_count: float | None = Field(default=None, ge=0)
    carbs_g_per_hr: float | None = Field(default=None, ge=0)
    total_carbs_g: float | None = Field(default=None, ge=0)
    sodium_mg: float | None = Field(default=None, ge=0)
    fluid_oz: float | None = Field(default=None, ge=0)
    caffeine_mg: float | None = Field(default=None, ge=0)
    gi_distress_1_to_5: int | None = Field(default=None, ge=1, le=5)
    bonk_mile: float | None = Field(default=None, ge=0)
    products_used: list[str] = Field(default_factory=list)
    note: str = ""


class BiomechanicsBlockPayload(BaseModel):
    """Deterministic 1 Hz block forensics summary (Chicago Marathon 4-signature diagnostic model).
    Gracefully handles missing sensor channels across Tier 1 (Pace+HR), Tier 2 (Wrist Power+Dynamics),
    and Tier 3 (Chest Strap / Footpod Lab)."""

    kind: Literal["BiomechanicsBlock"] = "BiomechanicsBlock"
    activity_id: str
    run_date: str = ""
    distance_mi: float | None = Field(default=None, ge=0)
    avg_pace_s_per_mi: int | None = Field(default=None, ge=180, le=1800)
    avg_hr_bpm: float | None = Field(default=None, ge=40, le=240)
    avg_power_w: float | None = Field(default=None, ge=0, le=1000)
    avg_cadence_spm: float | None = Field(default=None, ge=100, le=260)
    avg_gct_ms: float | None = Field(default=None, ge=120, le=450)
    gct_balance_left_pct: float | None = Field(default=None, ge=40.0, le=60.0)
    avg_stride_length_m: float | None = Field(default=None, ge=0.4, le=2.5)
    avg_vertical_ratio_pct: float | None = Field(default=None, ge=2.0, le=20.0)
    pw_hr_decoupling_pct: float | None = None
    pa_hr_decoupling_pct: float | None = None
    late_run_gct_delta_ms: float | None = None
    late_run_cadence_delta_spm: float | None = None
    diagnostic_signature: Literal[
        "optimal_steady",
        "glycogen_depletion",
        "neuromuscular_form_fade",
        "thermal_cardiac_drift",
        "asymmetric_guarding",
        "insufficient_sensors",
    ] = "optimal_steady"
    sensor_tier: Literal[
        "tier1_pace_hr",
        "tier2_wrist_power_dynamics",
        "tier3_chest_pod_lab",
    ] = "tier1_pace_hr"
    note: str = ""


class HardwareSensorProfilePayload(BaseModel):
    """Tracks athlete watch, heart rate sensor, and footpod capabilities so coaching prescriptions
    and forensic scripts know which telemetry channels exist vs. require subjective RPE fallbacks."""

    kind: Literal["HardwareSensorProfile"] = "HardwareSensorProfile"
    watch_ecosystem: Literal["garmin", "coros", "apple_watch", "polar", "suunto", "phone_strava"] = "garmin"
    watch_model: str = ""
    hr_sensor_type: Literal["wrist_optical", "chest_strap_ecg", "armband_optical", "none"] = "wrist_optical"
    power_source: Literal["garmin_wrist", "coros_wrist", "apple_wrist", "stryd_footpod", "none"] = "none"
    has_gct_and_stride: bool = False
    has_gct_lr_balance: bool = False
    has_overnight_hrv: bool = False
    has_workout_fit_push: bool = True
    note: str = ""


class DailyMacroHydrationPayload(BaseModel):
    """Daily or pre-long-run carb-load & hydration summary synced from MacroFactor, MyFitnessPal,
    Cronometer, Apple Health, or athlete self-report."""

    kind: Literal["DailyMacroHydration"] = "DailyMacroHydration"
    log_date: str = ""
    source_app: Literal["macrofactor", "myfitnesspal", "cronometer", "apple_health", "manual"] = "manual"
    calories_kcal: int | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    carbs_g_per_kg: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fluid_oz: float | None = Field(default=None, ge=0)
    sodium_mg: float | None = Field(default=None, ge=0)
    alcohol_drinks: float | None = Field(default=None, ge=0)
    note: str = ""


class AutonomicReadinessPayload(BaseModel):
    """Morning autonomic nervous system (HRV rMSSD / RHR / sleep) gate for dynamic workout modulation."""

    kind: Literal["AutonomicReadiness"] = "AutonomicReadiness"
    log_date: str = ""
    hrv_rmssd_ms: float | None = Field(default=None, ge=5, le=300)
    hrv_7d_baseline_ms: float | None = Field(default=None, ge=5, le=300)
    rhr_bpm: float | None = Field(default=None, ge=30, le=120)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_score: int | None = Field(default=None, ge=0, le=100)
    cycle_phase: Literal["follicular", "ovulatory", "luteal", "menstrual", "unspecified"] = "unspecified"
    readiness_gate: Literal["green", "yellow", "red"] = "green"
    note: str = ""


class ShoeRotationGearPayload(BaseModel):
    """Tracks shoe mileage and foam category (daily trainer vs. carbon race shoe) to separate
    dead-foam calf/GCT degradation from physiological fatigue."""

    kind: Literal["ShoeRotationGear"] = "ShoeRotationGear"
    strava_gear_id: str = ""
    brand_model: str = ""
    shoe_category: Literal["daily_trainer", "super_trainer", "carbon_race", "trail", "recovery"] = "daily_trainer"
    cumulative_miles: float = Field(default=0.0, ge=0)
    retire_threshold_miles: float = Field(default=350.0, ge=50)
    is_retired: bool = False
    note: str = ""


class EnvironmentalContextPayload(BaseModel):
    """Per-activity weather, WBGT/dew point, wind, and bridge/surface context."""

    kind: Literal["EnvironmentalContext"] = "EnvironmentalContext"
    activity_id: str | None = None
    run_date: str = ""
    temp_f: float | None = None
    dew_point_f: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    wbgt_f: float | None = None
    wind_mph: float | None = Field(default=None, ge=0)
    surface_type: Literal["road", "track", "treadmill", "trail", "bridges_hills"] = "road"
    heat_pace_adjustment_s_per_mi: int = Field(default=0, ge=0, le=180)
    note: str = ""


class SetCoachingScopePayload(BaseModel):
    """Progressively enables or updates informal coaching modules (fueling, hydration, biomechanics,
    readiness, limiter focus) without bombarding the athlete during Week 1 onboarding."""

    kind: Literal["SetCoachingScope"] = "SetCoachingScope"
    enable_fueling_guidance: bool | None = None
    enable_hydration_weather: bool | None = None
    enable_biomechanics_forensics: bool | None = None
    enable_readiness_gates: bool | None = None
    sweat_sodium_tier: Literal["low", "moderate", "salty"] | None = None
    sweat_rate_ml_per_hr: int | None = Field(default=None, ge=200, le=3000)
    preferred_gel: str | None = None
    fuel_comfort_profile: str | None = None
    workout_limiter_focus: Literal["balanced", "form_stiffness", "lactate_shuttle", "hill_strength"] | None = None
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
        FuelingLogPayload,
        BiomechanicsBlockPayload,
        HardwareSensorProfilePayload,
        DailyMacroHydrationPayload,
        AutonomicReadinessPayload,
        ShoeRotationGearPayload,
        EnvironmentalContextPayload,
        SetCoachingScopePayload,
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
        "FuelingLog": FuelingLogPayload,
        "BiomechanicsBlock": BiomechanicsBlockPayload,
        "HardwareSensorProfile": HardwareSensorProfilePayload,
        "DailyMacroHydration": DailyMacroHydrationPayload,
        "AutonomicReadiness": AutonomicReadinessPayload,
        "ShoeRotationGear": ShoeRotationGearPayload,
        "EnvironmentalContext": EnvironmentalContextPayload,
        "SetCoachingScope": SetCoachingScopePayload,
    }
    cls = table.get(kind or "")
    if cls is None:
        raise ValueError(f"unknown event kind: {kind!r}")
    return cls.model_validate(data)  # type: ignore[return-value]
