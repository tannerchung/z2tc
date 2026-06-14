"""Resolve optional club-intake answers onto ``AthleteInputs``.

The Google Form marks some questions optional. Policy: **if the athlete left a field
blank**, we fill it using (in order) **Strava-derived signals** when available, else a
**documented default** suitable for the Training Plan Formula Reference. Anything that
still needs human judgment stays on the coach / Sheet — we only encode deterministic
defaults here so the engine always sees concrete preference slugs.

Slugs match ``docs/intake-and-engine.md`` (canonical vocabulary for parsers and UI).
"""

from __future__ import annotations

from dataclasses import replace

from . import common
from .models import AthleteInputs

# --- Canonical slugs (aligned with Google Form export mapping) --------------------

PHILOSOPHY_FUNSIES = "funsies"
PHILOSOPHY_STEADY = "steady"
PHILOSOPHY_ALL_OUT = "all_out"

HARD_Q_ONE = "one"
HARD_Q_ONE_OR_TWO = "one_or_two"
HARD_Q_TWO = "two"
HARD_Q_AUTO = "auto"

INTENSITY_EASY = "easy"
INTENSITY_NORMAL = "normal"
INTENSITY_HARD = "hard"

LR_FREQ_MINIMAL = "minimal"
LR_FREQ_WEEKLY = "weekly"
LR_FREQ_EXTRA_AEROBIC = "extra_aerobic"

LR_DIFF_EASY = "easy"
LR_DIFF_CLUB = "club"
LR_DIFF_AGGRESSIVE = "aggressive"

SOCIAL_YES = "yes"
SOCIAL_MAYBE = "maybe"
SOCIAL_UNKNOWN = "unknown"


def _resolve_hard_quality_auto(method: str) -> str:
    """2Q / Pfitz defaults when the athlete picks *you tell me*."""
    if method == common.PFITZINGER:
        return HARD_Q_TWO
    return HARD_Q_ONE_OR_TWO


def resolve_intake_defaults(inputs: AthleteInputs) -> AthleteInputs:
    """Return a copy of ``inputs`` with any **unset** intake preference fields filled.

    Does not recompute VDOT, ``w_now``, or ``p_history`` — those come from the Strava
    merge layer. Does not parse free-text injury notes into ``injury_prone`` (coach or
    a future rules layer should set the bool when merging the form row).
    """
    method = common.assign_method(inputs)
    updates: dict = {}

    if inputs.training_philosophy is None:
        updates["training_philosophy"] = PHILOSOPHY_STEADY

    hq = inputs.hard_quality_sessions_pref
    if hq is None or hq == HARD_Q_AUTO:
        updates["hard_quality_sessions_pref"] = _resolve_hard_quality_auto(method)

    if inputs.hard_session_intensity_pref is None:
        updates["hard_session_intensity_pref"] = INTENSITY_NORMAL

    if inputs.long_run_frequency_pref is None:
        updates["long_run_frequency_pref"] = LR_FREQ_WEEKLY

    if inputs.long_run_difficulty_pref is None:
        updates["long_run_difficulty_pref"] = LR_DIFF_CLUB

    if inputs.social_carb_load is None:
        updates["social_carb_load"] = SOCIAL_UNKNOWN

    if inputs.social_shakeout is None:
        updates["social_shakeout"] = SOCIAL_UNKNOWN

    if not updates:
        return inputs
    return replace(inputs, **updates)
