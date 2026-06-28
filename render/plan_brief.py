"""Coach-facing plan preamble: method choice, P, paces, flags."""

from __future__ import annotations

from engine.plan import common
from engine.plan.models import AthleteInputs, TrainingPlan
from engine.plan.recommend import recommend_coaches
from engine.readiness import recommended_peak_mileage, recommended_reentry_volume
from render.workout_glossary import PACE_LEGEND


def _fmt_goal_time(seconds: int | None) -> str:
    if not seconds:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _method_skip_lines(inputs: AthleteInputs, chosen: str) -> list[str]:
    lines: list[str] = []
    auto_pfitz = inputs.p_history >= 40 and inputs.days_per_week >= 5
    if chosen != common.PFITZINGER:
        why = []
        if inputs.days_per_week < 5:
            why.append(f"{inputs.days_per_week} d/wk < 5")
        if inputs.p_history < 40:
            why.append(f"p_history {inputs.p_history:g} < 40 mpw")
        lines.append(
            f"Pfitzinger skipped: needs 5+ days and ~40 mpw demonstrated"
            + (f" ({'; '.join(why)})" if why else "")
            + f". Auto-route would be {'Pfitz' if auto_pfitz else 'Daniels'}."
        )
    if chosen != common.HANSON:
        lines.append(
            f"Hansons skipped: 6-day cumulative-fatigue model; athlete runs {inputs.days_per_week} d/wk."
        )
    if chosen != common.HIGDON:
        rec = next((r for r in recommend_coaches(inputs) if r.method == common.HIGDON), None)
        lines.append(
            f"Higdon skipped: distance-model novice/intermediate grid; club default is Daniels 2Q"
            + (f" ({rec.notes})" if rec else "")
            + "."
        )
    if chosen != common.DANIELS and chosen == common.PFITZINGER:
        lines.append("Daniels skipped: athlete meets Pfitzinger base (5+ days, p_history ≥ 40).")
    return lines


def build_coach_brief_rows(plan: TrainingPlan, inputs: AthleteInputs) -> list[list[str]]:
    """Deterministic rows for the COACH BRIEF block (two columns: label, value)."""
    chosen = plan.method
    start, start_why = recommended_reentry_volume(
        inputs.w_now,
        inputs.p_history,
        recent_sustained_mpw=inputs.recent_sustained_mpw,
        race_fit=inputs.race_fit,
        injury_prone=inputs.injury_prone,
        days_per_week=inputs.days_per_week,
    )
    p_rec, p_why = recommended_peak_mileage(
        inputs.p_history,
        inputs.days_per_week,
        injury_prone=inputs.injury_prone,
        goal_demanding=False,
    )
    peak_engine = common.peak_mileage(inputs)

    rows: list[list[str]] = [
        ["COACH BRIEF", ""],
        ["Athlete", plan.athlete],
        ["Primary goal", f"{plan.goal.get('name', '')} on {plan.goal.get('date', '')}"],
        ["A-goal time", _fmt_goal_time(plan.goal.get("goal_time_s"))],
        ["Plan method", chosen],
        ["VDOT (plan)", f"{plan.vdot:g}"],
        ["Days per week", str(inputs.days_per_week)],
        ["w_now", f"{inputs.w_now:g} mpw"],
        ["p_history (demonstrated peak)", f"{inputs.p_history:g} mpw"],
        ["Re-entry start", f"{start:g} mpw — {start_why}"],
        ["P (peak target)", f"{plan.peak_miles:g} mpw"],
        ["P rationale (engine)", f"peak_mileage = max(p_history, w_now) = {peak_engine:g} mpw"],
        ["P rationale (readiness)", f"{p_rec:g} mpw — {p_why}"],
        ["Block weeks", str(plan.block_weeks)],
        ["Generated", str(plan.generated_at or "")],
    ]
    if inputs.returning_marathoner:
        rows.append(["Returning marathoner", "yes — block anchored on last marathon + volume decay"])
    if inputs.recent_break_days:
        rows.append(["Recent break", f"{inputs.recent_break_days} d not running (Table 15.1 at merge)"])

    rows.append(["", ""])
    rows.append(["WHY THIS METHOD", ""])
    rows.append(["Selected", f"{chosen} — assign_method(inputs) after intake defaults"])
    for line in _method_skip_lines(inputs, chosen):
        rows.append(["", line])

    if plan.flags:
        rows.append(["", ""])
        rows.append(["PLAN FLAGS", ""])
        for f in plan.flags:
            rows.append(["", f])

    return rows


def build_pace_rows(plan: TrainingPlan) -> list[list[str]]:
    p = plan.paces or {}
    return [
        ["DANIELS PACES", f"VDOT {plan.vdot:g}"],
        ["Zone", "Pace / mi", "Meaning"],
        ["Easy (E)", str(p.get("easy", "")), PACE_LEGEND["E"]],
        ["Marathon (M)", str(p.get("marathon", "")), "VDOT marathon pace (fitness); goal MP may differ."],
        ["Threshold (T)", str(p.get("threshold", "")), PACE_LEGEND["T"]],
        ["Interval (I)", str(p.get("interval", "")), PACE_LEGEND["I"]],
        ["Repetition (R)", str(p.get("rep", "")), PACE_LEGEND["R"]],
    ]
