"""Deterministic marathon plan engine.

``build_plan(inputs)`` turns an athlete's race-derived fitness (VDOT) and history into a
week-by-week ``TrainingPlan`` using either Daniels' 2Q structure or Pfitzinger's
mesocycles. Pure functions only: same inputs always yield the same plan, no IO, no LLM.

The numeric rules live in ``common.py`` (transcribed from the project's Training Plan
Formula Reference); the two generators assemble weeks from those building blocks.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..paces import training_paces
from . import common
from .daniels import build_daniels_plan
from .intake import resolve_intake_defaults
from .models import AthleteInputs, MarathonRace, TrainingPlan
from .pfitzinger import build_pfitzinger_plan

__all__ = ["build_plan", "AthleteInputs", "MarathonRace", "TrainingPlan", "resolve_intake_defaults"]


def build_plan(inputs: AthleteInputs) -> TrainingPlan:
    """Resolve the method, compute paces from VDOT, and dispatch to a generator."""
    inputs = resolve_intake_defaults(inputs)
    method = common.assign_method(inputs)
    paces = training_paces(inputs.vdot)
    builder = build_pfitzinger_plan if method == common.PFITZINGER else build_daniels_plan
    plan = builder(inputs, paces)
    plan.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return plan
