"""Deterministic marathon plan engine.

``build_plan(inputs)`` turns an athlete's race-derived fitness (VDOT) and history into a
week-by-week ``TrainingPlan`` using either Daniels' 2Q structure or Pfitzinger's
mesocycles. Pure functions only: same inputs always yield the same plan, no IO, no LLM.

The numeric rules live in ``common.py`` (transcribed from the project's Training Plan
Formula Reference); the two generators assemble weeks from those building blocks.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ..paces import training_paces
from . import common
from .daniels import build_daniels_plan
from .hanson import build_hanson_plan
from .higdon import build_higdon_plan
from .intake import resolve_intake_defaults
from .models import AthleteInputs, MarathonRace, PlanScenarioMeta, TrainingPlan
from .pfitzinger import build_pfitzinger_plan

__all__ = ["build_plan", "AthleteInputs", "MarathonRace", "TrainingPlan", "resolve_intake_defaults"]


def _finalize(plan: TrainingPlan, inputs: AthleteInputs, paces: dict) -> TrainingPlan:
    if inputs.append_post_marathon_recovery:
        easy_s, easy_str = common.easy_pace(paces)
        plan = common.append_post_marathon_recovery(plan, easy_pace_s=easy_s, easy_str=easy_str)
    plan.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return plan


def _daniels_peak_scenarios(inputs: AthleteInputs, paces: dict) -> TrainingPlan:
    """Primary Daniels plan plus sibling plans at P+5 and P+10 peak targets (see plan-engine.md)."""
    base_peak = round(max(inputs.p_history, inputs.w_now), 1)
    extras = [(base_peak + 5.0, "P+5"), (base_peak + 10.0, "P+10")]

    siblings: list[TrainingPlan] = []
    for target_peak, sid in extras:
        alt = build_daniels_plan(
            replace(
                inputs,
                coach_target_mpw=target_peak,
                emit_peak_scenarios=False,
                append_post_marathon_recovery=False,
            ),
            paces,
        )
        max_b = max(w.target_miles for w in alt.weeks[: max(1, len(alt.weeks) - 3)])
        reachable = max_b + 1.5 >= target_peak
        alt = replace(
            alt,
            scenario=PlanScenarioMeta(scenario_id=sid, target_peak_mpw=target_peak, reachable=reachable, flags=()),
            sibling_scenarios=(),
        )
        if not reachable:
            alt = replace(
                alt,
                flags=list(alt.flags)
                + [f"peak scenario {sid}: block may not reach {target_peak:g} mpw without coach_floor / more weeks"],
            )
        siblings.append(alt)

    primary = build_daniels_plan(
        replace(inputs, emit_peak_scenarios=False, append_post_marathon_recovery=False), paces
    )
    primary = replace(
        primary,
        scenario=PlanScenarioMeta(
            scenario_id="primary",
            target_peak_mpw=round(common.peak_mileage(inputs), 1),
            reachable=True,
            flags=(),
        ),
        sibling_scenarios=tuple(siblings),
    )
    return _finalize(primary, inputs, paces)


def build_plan(inputs: AthleteInputs) -> TrainingPlan:
    """Resolve the method, compute paces from VDOT, and dispatch to a generator."""
    inputs = resolve_intake_defaults(inputs)
    if inputs.reentry_start_mpw is None:
        from ..readiness import recommended_reentry_volume

        start, _ = recommended_reentry_volume(
            inputs.w_now,
            inputs.p_history,
            recent_sustained_mpw=inputs.recent_sustained_mpw,
            race_fit=inputs.race_fit,
            injury_prone=inputs.injury_prone,
            days_per_week=inputs.days_per_week,
        )
        inputs = replace(inputs, reentry_start_mpw=start)
    method = common.assign_method(inputs)
    paces = dict(training_paces(inputs.vdot))
    if inputs.easy_pace_override_s is not None:
        o = max(240, min(1200, int(inputs.easy_pace_override_s)))
        band = 8
        lo, hi = max(200, o - band), o + band
        m1, s1 = divmod(lo, 60)
        m2, s2 = divmod(hi, 60)
        paces["easy_low_s"] = lo
        paces["easy_high_s"] = hi
        paces["easy"] = f"{m1}:{s1:02d}-{m2}:{s2:02d}"

    if inputs.emit_peak_scenarios and method == common.DANIELS:
        return _daniels_peak_scenarios(inputs, paces)

    builder = {
        common.PFITZINGER: build_pfitzinger_plan,
        common.HIGDON: build_higdon_plan,
        common.HANSON: build_hanson_plan,
    }.get(method, build_daniels_plan)
    plan = builder(inputs, paces)
    return _finalize(plan, inputs, paces)
