"""JSON-safe (de)serialization for ``TrainingPlan`` and nested dataclasses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from engine.plan.models import PlannedDay, PlannedWeek, Segment, TrainingPlan, Workout, WorkoutKind


def _workout_from_dict(d: dict[str, Any]) -> Workout:
    kind = WorkoutKind(d["kind"]) if isinstance(d["kind"], str) else d["kind"]
    segs = [
        Segment(
            reps=int(s["reps"]),
            pace_label=str(s["pace_label"]),
            pace_s=s.get("pace_s"),
            distance_m=s.get("distance_m"),
            duration_s=s.get("duration_s"),
            recovery=s.get("recovery"),
        )
        for s in d.get("segments", [])
    ]
    return Workout(
        kind=kind,
        label=str(d["label"]),
        distance_mi=d.get("distance_mi"),
        duration_min=d.get("duration_min"),
        pace=d.get("pace"),
        pace_s=d.get("pace_s"),
        segments=segs,
        flags=list(d.get("flags", [])),
    )


def _planned_day_from_dict(d: dict[str, Any]) -> PlannedDay:
    return PlannedDay(day=str(d["day"]), workout=_workout_from_dict(d["workout"]))


def _planned_week_from_dict(d: dict[str, Any]) -> PlannedWeek:
    return PlannedWeek(
        index=int(d["index"]),
        phase=str(d["phase"]),
        label=str(d["label"]),
        target_miles=float(d["target_miles"]),
        is_down_week=bool(d.get("is_down_week", False)),
        days=[_planned_day_from_dict(x) for x in d.get("days", [])],
        flags=list(d.get("flags", [])),
    )


def training_plan_to_dict(plan: TrainingPlan) -> dict[str, Any]:
    def walk(obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if is_dataclass(obj):
            return {k: walk(v) for k, v in asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [walk(x) for x in obj]
        return obj

    return walk(plan)


def training_plan_from_dict(d: dict[str, Any]) -> TrainingPlan:
    weeks = [_planned_week_from_dict(w) for w in d.get("weeks", [])]
    return TrainingPlan(
        athlete=str(d["athlete"]),
        method=str(d["method"]),
        goal=dict(d.get("goal", {})),
        vdot=float(d["vdot"]),
        paces=dict(d.get("paces", {})),
        peak_miles=float(d["peak_miles"]),
        block_weeks=int(d["block_weeks"]),
        weeks=weeks,
        flags=list(d.get("flags", [])),
        generated_at=d.get("generated_at"),
    )


def athlete_inputs_fingerprint(inputs: Any) -> str:
    """Stable short hash for provenance (not cryptographic)."""
    import hashlib
    import json

    from dataclasses import asdict

    if is_dataclass(inputs):
        raw = json.dumps(asdict(inputs), sort_keys=True, default=str)
    else:
        raw = str(inputs)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
