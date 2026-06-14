"""Fold append-only events into ``AthleteInputs``, then run ``build_plan``."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from engine.plan import build_plan
from engine.plan.models import AthleteInputs, TrainingPlan

from store.events import (
    AdherenceFlagPayload,
    DifficultyPayload,
    EasyPaceDriftPayload,
    FatigueFlagPayload,
    InjuryPayload,
    LongRunIncompletePayload,
    ManualOverridePayload,
    MissedQualityPayload,
    OverreachFlagPayload,
    SetDaysPayload,
    SetGoalPayload,
    SetRaceDatePayload,
    TuneUpResultPayload,
    UnavailablePayload,
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
    if isinstance(
        payload,
        (
            AdherenceFlagPayload,
            EasyPaceDriftPayload,
            MissedQualityPayload,
            LongRunIncompletePayload,
            FatigueFlagPayload,
            OverreachFlagPayload,
        ),
    ):
        return inputs
    return inputs


def replan(baseline: AthleteInputs, store: Store, athlete_id: str) -> TrainingPlan:
    """Load events for ``athlete_id``, fold into baseline, ``build_plan``."""
    rows = store.list_events(athlete_id)
    parsed: list[tuple[str, Any]] = []
    for r in rows:
        if r["status"] == "proposed":
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
        cur = _apply_payload(cur, payload)

    plan = build_plan(cur)
    plan.flags = list(plan.flags) + extra_flags
    return plan
