"""Fold append-only events into ``AthleteInputs``, then run ``build_plan``."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from engine.plan import build_plan
from engine.plan.models import AthleteInputs, TrainingPlan

from store.events import (
    AdherenceFlagPayload,
    CoachNotePayload,
    DataExcludePayload,
    DifficultyPayload,
    EffortQualityPayload,
    FitnessAnchorPayload,
    EasyPaceDriftPayload,
    FatigueFlagPayload,
    InjuryPayload,
    LongRunIncompletePayload,
    ManualOverridePayload,
    MissedQualityPayload,
    OverreachFlagPayload,
    RaceEstimatePayload,
    SetDaysPayload,
    SetGoalPayload,
    SetRaceDatePayload,
    TuneUpResultPayload,
    UnavailablePayload,
    WeeklyEvaluationPayload,
    parse_event_payload,
)

if TYPE_CHECKING:
    from store.db import Store


def _parse_payload_json(raw: str) -> Any:
    d = json.loads(raw)
    try:
        return parse_event_payload(d)
    except ValueError:
        return d


def _apply_payload(inputs: AthleteInputs, payload: Any) -> AthleteInputs:
    if isinstance(payload, dict):
        return inputs
    if isinstance(payload, SetDaysPayload):
        return replace(inputs, days_per_week=payload.n)
    if isinstance(payload, SetGoalPayload):
        return replace(inputs, goal_marathon_s=payload.goal_marathon_s)
    if isinstance(payload, SetRaceDatePayload):
        return replace(inputs, race_date=payload.race_date)
    if isinstance(payload, TuneUpResultPayload):
        return replace(inputs, vdot=payload.new_vdot)
    if isinstance(payload, RaceEstimatePayload):
        return replace(inputs, vdot=payload.effective_vdot)
    if isinstance(payload, FitnessAnchorPayload):
        return replace(inputs, vdot=payload.vdot) if payload.vdot is not None else inputs
    if isinstance(payload, InjuryPayload):
        return replace(inputs, injury_prone=True)
    if isinstance(payload, DifficultyPayload):
        factor = 1.0 + 0.05 * min(0, payload.delta) + 0.03 * max(0, payload.delta)
        factor = max(0.85, min(1.09, factor))
        return replace(inputs, w_now=round(inputs.w_now * factor, 1))
    if isinstance(payload, ManualOverridePayload):
        if payload.field not in AthleteInputs.__dataclass_fields__:
            return inputs
        return replace(inputs, **{payload.field: payload.value})
    if isinstance(payload, UnavailablePayload):
        return inputs
    if isinstance(payload, WeeklyEvaluationPayload):
        updates: dict[str, object] = {}
        if payload.calibrated_vdot is not None:
            updates["vdot"] = round(float(payload.calibrated_vdot), 1)
        if payload.estimated_mpw is not None:
            mpw = round(float(payload.estimated_mpw), 1)
            updates["w_now"] = mpw
            updates["reentry_start_mpw"] = mpw
        if payload.easy_pace_override_s is not None:
            updates["easy_pace_override_s"] = int(payload.easy_pace_override_s)
        return replace(inputs, **updates) if updates else inputs
    if isinstance(
        payload,
        (
            AdherenceFlagPayload,
            EasyPaceDriftPayload,
            MissedQualityPayload,
            LongRunIncompletePayload,
            FatigueFlagPayload,
            OverreachFlagPayload,
            CoachNotePayload,
            EffortQualityPayload,
            DataExcludePayload,
        ),
    ):
        return inputs
    return inputs


def fold_events_to_inputs(baseline: AthleteInputs, store: Store, athlete_id: str) -> tuple[AthleteInputs, list[str]]:
    """Apply approved/applied events to ``baseline``; return working inputs + provenance flags."""
    rows = store.list_events(athlete_id)
    parsed: list[tuple[str, Any]] = []
    for r in rows:
        if r["status"] == "proposed" or r["status"] == "rejected":
            continue
        parsed.append((r["ts"], _parse_payload_json(r["payload_json"])))
    parsed.sort(key=lambda x: x[0])
    cur = baseline
    extra_flags: list[str] = []
    for _, payload in parsed:
        if isinstance(payload, UnavailablePayload):
            extra_flags.append(
                f"replan_note: Unavailable {payload.start}..{payload.end} "
                "(week reshuffle not automated in MVP)"
            )
            continue
        if isinstance(payload, InjuryPayload):
            extra_flags.append(
                "replan_note: injury / time-off — after 3–4 days missed, ease back slowly (Hanson p.145); "
                "longer layoffs: Daniels Table 15.2 return bands (33/50/75% prior volume) before full load."
            )
            continue
        if isinstance(payload, MissedQualityPayload):
            extra_flags.append(
                f"replan_note: missed quality wk{payload.week_index} {payload.day} ({payload.expected_label}) — "
                "do not silently redistribute; repeat or slide when coach approves."
            )
            continue
        if isinstance(payload, CoachNotePayload):
            extra_flags.append(f"coach_note: {payload.text}")
            continue
        if isinstance(payload, EffortQualityPayload):
            extra_flags.append(f"coach_note: {payload.race_date} effort={payload.quality}")
            continue
        if isinstance(payload, DataExcludePayload):
            extra_flags.append(f"coach_note: exclude {payload.race_date} ({payload.reason})")
            continue
        if isinstance(payload, RaceEstimatePayload):
            extra_flags.append(
                f"coach_note: race-estimate {payload.race_name} "
                f"→ effective VDOT {payload.effective_vdot}"
                + (f" ({payload.note})" if payload.note else "")
            )
        if isinstance(payload, FitnessAnchorPayload):
            extra_flags.append(
                f"coach_note: fitness-anchor → VDOT {payload.vdot}"
                + (f" [{payload.source}]" if payload.source else "")
            )
        if isinstance(payload, WeeklyEvaluationPayload):
            parts = [f"week={payload.week_start}"]
            if payload.calibrated_vdot is not None:
                parts.append(f"vdot={payload.calibrated_vdot}")
            if payload.estimated_mpw is not None:
                parts.append(f"mpw={payload.estimated_mpw}")
            if payload.easy_pace_override_s is not None:
                parts.append(f"easy_s/mi={payload.easy_pace_override_s}")
            tail = f" ({payload.note})" if payload.note else ""
            extra_flags.append("coach_note: weekly-evaluation " + " ".join(parts) + tail)
        cur = _apply_payload(cur, payload)
    return cur, extra_flags


def replan(baseline: AthleteInputs, store: Store, athlete_id: str) -> TrainingPlan:
    """Load events for ``athlete_id``, fold into baseline, ``build_plan``."""
    cur, extra_flags = fold_events_to_inputs(baseline, store, athlete_id)
    plan = build_plan(cur)
    plan.flags = list(plan.flags) + extra_flags
    return plan
