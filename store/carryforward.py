"""Seed the next season's baseline from the prior season's ending state.

A new marathon block shouldn't restart from cold intake. It carries the athlete forward:
the calibrated VDOT and demonstrated volume from the season they just finished become the
starting fitness for the next one, cross-checked against their race history (Daniels Table
15.1 detraining via ``engine.readiness.select_fitness_vdot``). Everything seeded here is a
defensible default the coach can still edit before the first ``build_plan``.
"""

from __future__ import annotations

from engine.plan.models import AthleteInputs, TrainingPlan
from engine.readiness import select_fitness_vdot

from .models import SurveyInputs

# Post-marathon athletes re-enter below their prior peak. This recovered-base fraction only
# seeds ``w_now`` (current mileage); the readiness re-entry model still sizes week 1 from
# ``recent_sustained_mpw`` + ``race_fit``. Editable by the coach.
DEFAULT_RECOVERY_FACTOR = 0.6


def build_next_season_survey(
    prior_survey: SurveyInputs,
    resolved_inputs: AthleteInputs,
    prior_plan: TrainingPlan,
    *,
    label: str,
    race_name: str,
    race_date: str,
    goal_marathon_s: int,
    block_weeks: int | None = None,
    completed_marathon_time_s: int | None = None,
    races: list[dict] | None = None,
    break_days: int = 0,
    cross_trained: bool = False,
    recovery_factor: float = DEFAULT_RECOVERY_FACTOR,
) -> tuple[SurveyInputs, dict]:
    """Return ``(new_survey, provenance)`` for the next season.

    ``resolved_inputs`` is the prior season's folded ``AthleteInputs`` (baseline + events) —
    i.e. the calibrated ending state. ``prior_plan`` supplies the demonstrated peak mileage.
    ``races`` (optional) are extra fitness candidates in ``select_fitness_vdot`` shape
    (``category`` / ``date`` / ``duration_s``); the just-completed marathon is added
    automatically when ``completed_marathon_time_s`` is given. Provenance is returned for the
    season's ``meta`` so the seeding is auditable.
    """
    notes: list[str] = []

    ending_vdot = float(resolved_inputs.vdot)

    candidates: list[dict] = list(races or [])
    if completed_marathon_time_s and prior_survey.race_date:
        candidates.append(
            {
                "category": "Marathon",
                "date": prior_survey.race_date,
                "duration_s": int(completed_marathon_time_s),
                "name": prior_survey.race_name,
            }
        )

    history_vdot: float | None = None
    vdot_source = "prior season calibrated VDOT"
    if candidates:
        sel = select_fitness_vdot(candidates, break_days=break_days, cross_trained=cross_trained)
        if sel.effective_vdot is not None:
            history_vdot = float(sel.effective_vdot)
            notes.append(f"race-history scan: {sel.source} → effective VDOT {history_vdot}")
            for d in sel.dropped:
                notes.append(f"dropped {d}")

    seed_vdot = ending_vdot
    if history_vdot is not None and history_vdot > ending_vdot:
        seed_vdot = history_vdot
        vdot_source = "race history (higher than prior calibrated)"
    notes.append(f"seed VDOT {seed_vdot} ({vdot_source}); prior calibrated {ending_vdot}")

    demonstrated_peak = round(
        max(prior_plan.peak_miles, prior_survey.p_history, float(resolved_inputs.p_history)), 1
    )
    seed_w_now = round(prior_plan.peak_miles * recovery_factor, 1)
    notes.append(
        f"demonstrated peak {demonstrated_peak} mpw; seed w_now {seed_w_now} "
        f"(×{recovery_factor} recovered base, editable)"
    )

    last_time = completed_marathon_time_s or prior_survey.goal_marathon_s

    new_survey = prior_survey.model_copy(
        update={
            "vdot": seed_vdot,
            "goal_marathon_s": goal_marathon_s,
            "w_now": seed_w_now,
            "p_history": demonstrated_peak,
            "recent_sustained_mpw": round(prior_plan.peak_miles, 1),
            "reentry_start_mpw": None,
            "longest_run_mi": float(resolved_inputs.longest_run_mi),
            "race_name": race_name,
            "race_date": race_date,
            "block_weeks": block_weeks or prior_survey.block_weeks,
            "returning_marathoner": True,
            "race_fit": True,
            "last_marathon_date": prior_survey.race_date,
            "last_marathon_time_s": last_time,
            # New-block context resets (carry coach prefs + overrides + personal fields).
            "secondary_races": [],
            "decayed_peak_mpw": None,
            "recent_break_days": None,
            "cross_trained_during_break": False,
            "cross_training_note": None,
            "marathon_arrival_date": None,
            "marathon_departure_date": None,
            "marathon_stay_description": None,
        }
    )

    provenance = {
        "carried_from_race": f"{prior_survey.race_name} {prior_survey.race_date}",
        "ending_vdot": ending_vdot,
        "history_effective_vdot": history_vdot,
        "seed_vdot": seed_vdot,
        "vdot_source": vdot_source,
        "demonstrated_peak_mpw": demonstrated_peak,
        "seed_w_now": seed_w_now,
        "notes": notes,
    }
    return new_survey, provenance
