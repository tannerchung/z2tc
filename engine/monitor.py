"""Deterministic monitoring: prescribed plan vs actual weekly miles -> event payloads.

Strava-derived actuals should be summarized upstream (``engine.analyze`` weekly totals).
This module stays pure: no IO, no API calls.
"""

from __future__ import annotations

from engine.plan.models import PlannedWeek, TrainingPlan

from store.events import AdherenceFlagPayload, MissedQualityPayload


def adherence_payload(week_start: str, prescribed_mi: float, actual_mi: float) -> AdherenceFlagPayload | None:
    if prescribed_mi <= 0:
        return None
    ratio = actual_mi / prescribed_mi
    if ratio >= 0.92:
        return None
    return AdherenceFlagPayload(
        week_start=week_start,
        prescribed_mi=round(prescribed_mi, 1),
        actual_mi=round(actual_mi, 1),
        ratio=round(ratio, 3),
    )


def missed_quality_payload(week: PlannedWeek) -> list[MissedQualityPayload]:
    """If a build week prescribes quality but actual miles are unknown, skip.

    When ``actual_by_day`` maps ``DAY_NAMES`` to miles run that day, detect a prescribed
    quality day with ``actual_mi == 0`` (MVP: treat zero as missed).
    """
    return []


def monitor_week(
    week: PlannedWeek,
    *,
    week_start: str,
    actual_week_run_miles: float,
    actual_by_day: dict[str, float] | None = None,
) -> list:
    """Return zero or more monitor event payloads for one ISO week."""
    out: list = []
    ad = adherence_payload(week_start, week.target_miles, actual_week_run_miles)
    if ad:
        out.append(ad)
    if actual_by_day:
        for d in week.days:
            if not d.workout.is_quality:
                continue
            got = actual_by_day.get(d.day, 0.0) or 0.0
            if got < 0.5:
                out.append(
                    MissedQualityPayload(
                        week_index=week.index,
                        day=d.day,
                        expected_label=d.workout.label[:80],
                    )
                )
    return out


def monitor_block(plan: TrainingPlan, weekly_actuals: dict[str, float]) -> list:
    """``weekly_actuals`` maps ``week_start`` ISO (Monday) -> total run miles that week."""
    payloads: list = []
    for w in plan.weeks:
        ws = _week_start_for_index(plan, w.index)
        if not ws:
            continue
        act = weekly_actuals.get(ws, 0.0)
        payloads.extend(monitor_week(w, week_start=ws, actual_week_run_miles=act))
    return payloads


def _week_start_for_index(plan: TrainingPlan, index: int) -> str | None:
    """Derive ISO Monday from primary race date and week index (best-effort MVP)."""
    from datetime import date, timedelta

    try:
        race = date.fromisoformat(plan.goal.get("date", ""))
    except (TypeError, ValueError):
        return None
    try:
        start = race - timedelta(weeks=plan.block_weeks)
    except OverflowError:
        return None
    monday = start + timedelta(weeks=index - 1)
    return monday.isoformat()
