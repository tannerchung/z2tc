"""JSON-safe (de)serialization for ``TrainingPlan`` and nested dataclasses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from engine.plan.models import (
    AthleteInputs,
    MarathonRace,
    PlannedDay,
    PlannedWeek,
    PlanScenarioMeta,
    Segment,
    TrainingPlan,
    TuneUpRace,
    Workout,
    WorkoutKind,
)


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


def _scenario_to_dict(s: PlanScenarioMeta | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "scenario_id": s.scenario_id,
        "target_peak_mpw": s.target_peak_mpw,
        "reachable": s.reachable,
        "flags": list(s.flags),
    }


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
    scen = d.get("scenario")
    scenario = (
        PlanScenarioMeta(
            scenario_id=str(scen["scenario_id"]),
            target_peak_mpw=float(scen["target_peak_mpw"]),
            reachable=bool(scen.get("reachable", True)),
            flags=tuple(scen.get("flags", [])),
        )
        if isinstance(scen, dict)
        else None
    )
    sibs_raw = d.get("sibling_scenarios") or []
    sibling_scenarios = tuple(training_plan_from_dict(x) for x in sibs_raw if isinstance(x, dict))
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
        notes=list(d.get("notes", [])),
        generated_at=d.get("generated_at"),
        scenario=scenario,
        sibling_scenarios=sibling_scenarios,
    )


def athlete_inputs_to_dict(inputs: AthleteInputs) -> dict[str, Any]:
    """JSON-safe snapshot of the resolved ``AthleteInputs`` that built a plan.

    Tuple fields (``secondary_races``, ``marathons_selected``) become lists so the dict
    round-trips through JSON; ``athlete_inputs_from_dict`` restores the dataclass.
    """
    d = asdict(inputs)
    d["secondary_races"] = [{"name": r["name"], "date": r["date"]} for r in d.get("secondary_races", [])]
    d["marathons_selected"] = list(d.get("marathons_selected", []))
    return d


def athlete_inputs_from_dict(d: dict[str, Any]) -> AthleteInputs:
    """Inverse of :func:`athlete_inputs_to_dict`; ignores unknown keys for forward-compat."""
    data = dict(d)
    data["secondary_races"] = tuple(
        MarathonRace(name=str(r["name"]), date=str(r["date"])) for r in data.get("secondary_races", [])
    )
    data["marathons_selected"] = tuple(data.get("marathons_selected", []))
    # Tri-state tune-up list: None (unset) stays None; a stored list rebuilds the dataclasses.
    tune_ups = data.get("tune_up_races")
    if tune_ups is not None:
        data["tune_up_races"] = tuple(
            TuneUpRace(
                week=int(r["week"]), distance_m=float(r["distance_m"]),
                label=str(r["label"]), target_time_s=r.get("target_time_s"),
            )
            for r in tune_ups
        )
    allowed = set(AthleteInputs.__dataclass_fields__)
    return AthleteInputs(**{k: v for k, v in data.items() if k in allowed})


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
