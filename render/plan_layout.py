"""Deterministic plan tab layout mirroring the club's hand-styled athlete tabs.

Shape (top → bottom): title, subtitle, narrative, paces block, then a single
color-coded week table with phase bands, a per-week "Why", recovery shading, and a
race-day row. See ``docs/design/plan-sheet-layout.md``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.athlete_profile import AthleteDossier
from engine.execution import ON_TRACK_RATIO, ExecutionSummary, WeekExecution, week_start_for_index
from engine.plan.common import marathon_pace_s, volume_step_ups
from engine.plan.models import (
    DAY_NAMES,
    AthleteInputs,
    PlannedWeek,
    TrainingPlan,
    WorkoutKind,
)
from render.plan_sheet_theme import PHASE_TAGLINE
from render.workout_cell import format_cell
_LONG_KINDS = {WorkoutKind.LONG, WorkoutKind.MARATHON_PACE, WorkoutKind.MEDIUM_LONG}

# Bump when the *deterministic* narrative templates change (any of `_narrative`,
# `_history_interpretation`, `_plan_caution_block`, `_week_why`, `_execution_note`). Captured on every
# render (`narrative_renders.template_version`) so the distillation analysis can tell whether a wording
# shift came from a template revision vs the optional LLM pass. See docs/architecture/interpretation-layer.md.
NARRATIVE_TEMPLATE_VERSION = "9"

# The sheet reads Monday→Sunday, matching the engine's chronological week order so the weekend
# sits at the end of the row. This matters for a Sunday marathon: the race is the week's trailing
# day, so it lands in the *last* cell, after that week's shakeout — never before its own training.
WEEK_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_FULL = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
    "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}

# What the week as a whole is for — the lead sentence of the "Why".
_PHASE_INTENT = {
    "Base": "This is the Base phase, where you build the aerobic engine with easy volume and durability. Consistency matters more than pace.",
    "Threshold": "This is the Threshold phase, where you raise the lactate threshold so goal marathon pace costs less and start banking goal-pace miles in the long run.",
    "Race Prep": "This is the Race-prep phase, where you sharpen VO2max and lock in goal marathon pace under fatigue. It is the most race-specific block.",
    "Taper": "This is the Taper. You shed accumulated fatigue while keeping the legs sharp, so volume drops but a touch of quality stays and you don't go flat.",
}

# Responder profile → one plain-language framing sentence (no numbers, so it's LLM-smoothable and
# never asserts pace/mileage authority). Sourced from the dossier's race-history read.
_RESPONDER_SUMMARY = {
    "volume-sensitive": "Your race history shows fitness has climbed with mileage before, so this block's volume build is doing real work toward the goal.",
    "speed-dominant": "Your speed sits ahead of your endurance, so this block spends its volume on aerobic durability rather than chasing a faster VDOT.",
    "stable": "Your fitness has held steady across past blocks, so consistency rather than peak mileage is the lever this time.",
}


def _responder_summary_clause(dossier: AthleteDossier | None) -> str | None:
    if dossier is None:
        return None
    return _RESPONDER_SUMMARY.get(dossier.fitness.responder)


def _execution_note(we: WeekExecution) -> str | None:
    """Coach-voice feedback on a week the monitor has already seen (short volume, a missed quality
    day, or a coach note). None when the week was logged on-plan with nothing to flag."""
    parts: list[str] = []
    if we.on_track and we.actual_mi is not None and we.prescribed_mi is not None and we.ratio is not None:
        pct = round(we.ratio * 100)
        parts.append(
            f"You logged about {we.actual_mi:g} of {we.prescribed_mi:g} prescribed miles this week, "
            f"around {pct}%, which is right on plan. That consistency is exactly what builds the engine, "
            "so keep stacking weeks like this."
        )
    elif we.short and we.actual_mi is not None and we.prescribed_mi is not None and we.ratio is not None:
        pct = round(we.ratio * 100)
        on_track_pct = round(ON_TRACK_RATIO * 100)
        parts.append(
            f"You logged about {we.actual_mi:g} of {we.prescribed_mi:g} prescribed miles this week, "
            f"around {pct}%, so the week is flagged short. We measure this from your actual Strava log, "
            f"and a week counts as on plan once you reach about {on_track_pct}% of the prescribed miles. "
            "This one came in under that. It is not a problem on its own. We hold the ramp rather than "
            "chase the miss and build off what you are actually banking. Tell me if a week keeps coming "
            "in short and we will right-size it."
        )
    if we.missed_quality_days:
        days = ", ".join(_DAY_FULL.get(d, d) for d in we.missed_quality_days)
        tie = " (the same week that came in short)" if we.short else ""
        parts.append(
            f"A quality session slipped ({days}){tie}. Those are the workouts that move the needle, so "
            "protect them first when the week gets tight, and tell me if they keep getting crowded out."
        )
    if we.coach_note:
        parts.append(f"Coach note: {we.coach_note}")
    return "\n\n".join(parts) if parts else None


def _is_race_week(week: PlannedWeek) -> bool:
    """The marathon week (its own RACE-DAY band), not a mid-block tune-up. Tune-ups are also
    ``WorkoutKind.RACE`` but far shorter, so gate on marathon distance to keep them as normal rows."""
    return any(d.workout.kind == WorkoutKind.RACE and (d.workout.distance_mi or 0) >= 26.0 for d in week.days)


def _tune_up_day(week: PlannedWeek):
    """The scheduled tune-up race in a build week, if any (a short RACE, not the marathon)."""
    for d in week.days:
        if d.workout.kind == WorkoutKind.RACE and 0 < (d.workout.distance_mi or 0) < 26.0:
            return d
    return None


def _tune_up_outcomes(
    plan: TrainingPlan, tune_up_results: list[tuple[float, int, float]] | None
) -> dict[int, tuple[str, str]]:
    """Pair landed tune-up results (chronological: distance_m, time_s, measured_vdot) to the plan's
    tune-up weeks in order, and compute each week's on-track/behind status + a one-line indicator.
    Returns ``{week_index: (status, indicator_text)}``. Empty when no results or no goal time."""
    if not tune_up_results:
        return {}
    goal_s = (plan.goal or {}).get("goal_time_s")
    if not goal_s:
        return {}
    from engine.readiness import tune_up_outcome

    total_weeks = len(plan.weeks)
    tune_weeks = [w for w in plan.weeks if _tune_up_day(w) is not None]
    out: dict[int, tuple[str, str]] = {}
    for w, (_dist_m, time_s, measured_vdot) in zip(tune_weeks, tune_up_results):
        oc = tune_up_outcome(measured_vdot, goal_s, weeks_remaining=max(1, total_weeks - w.index))
        td = _tune_up_day(w)
        label = _workout_name(td.workout.label) if td else "Tune-up"
        actual = _fmt_goal(time_s)
        if oc.status == "on_track":
            text = f"\u2705 On track. You ran {label} {actual}, and the goal is still in reach, so hold the plan."
        elif oc.status == "watch":
            text = f"\U0001f7e0 B-goal watch. You ran {label} {actual}, and the A-goal is a stretch from here."
        else:
            text = (
                f"\U0001f534 Behind. You ran {label} {actual}, so re-anchor toward ~{_fmt_pred(oc.realistic_time_s)}. "
                "Talk it through before the next block of work."
            )
        out[w.index] = (oc.status, text)
    return out


@dataclass
class Row:
    kind: str                       # title|subtitle|narrative|blank|paces_header|pace|legend|
                                    # table_header|phase|week|week_down|race_band|race_day
    cells: list[str | int | float]
    phase: str | None = None
    long_col: int | None = None     # column index of the long-run cell (week rows)
    quality_cols: tuple[int, ...] = ()  # column indices of quality (Q) workouts this week
    medlong_cols: tuple[int, ...] = ()  # column indices of medium-long easy runs (surfaced like Q)
    over_capacity: bool = False         # week volume exceeds the athlete's demonstrated peak (amber Total)
    short_week: bool = False            # athlete logged under the on-plan threshold this week (slate-blue Wk marker)
    tune_up_status: str | None = None   # "on_track"|"watch"|"behind" once a tune-up result has landed
    tune_up_col: int | None = None      # column of the tune-up race cell to tint by status


@dataclass
class PlanSheetLayout:
    rows: list[Row]
    ncols: int
    column_widths: list[int]
    long_day: str
    quality_day: str
    column_kinds: list[str]         # per column (A..): spacer|wk|date|day|why|total

    @property
    def values(self) -> list[list[str | int | float]]:
        return [r.cells for r in self.rows]


def _fmt_goal(seconds: int | None) -> str:
    if not seconds:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h and s == 0:  # round goal times read cleaner without ":00" (3:45, not 3:45:00)
        return f"{h}:{m:02d}"
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_pred(seconds: int | None) -> str:
    """Predicted/projected finish, rounded to the minute (a prediction isn't second-accurate)."""
    if not seconds:
        return "—"
    h, m = divmod(round(int(seconds) / 60), 60)
    return f"{h}:{m:02d}" if h else f"{m} min"


def _saturday_dates(plan: TrainingPlan) -> list[str]:
    """One reference date per week (the week's Saturday), counting back from the final race day
    (the last race on the calendar; for a marathon double this is the second race, after the build's
    primary)."""
    anchor = plan.goal.get("final_race_date") or plan.goal.get("date")
    try:
        race = date.fromisoformat(str(anchor)[:10])
    except (ValueError, TypeError):
        return ["" for _ in plan.weeks]
    # Saturday on/before race day anchors the final plan week.
    last_sat = race - timedelta(days=(race.weekday() - 5) % 7)
    n = len(plan.weeks)
    out: list[str] = []
    for i in range(n):
        d = last_sat - timedelta(weeks=(n - 1 - i))
        out.append(f"{d:%b} {d.day}")
    return out


def _long_day(plan: TrainingPlan) -> str:
    counts: Counter[str] = Counter()
    for w in plan.weeks:
        lr = w.long_run
        if lr:
            counts[lr.day] += 1
    return counts.most_common(1)[0][0] if counts else "Sat"


def _quality_day(plan: TrainingPlan, long_day: str) -> str | None:
    counts: Counter[str] = Counter()
    for w in plan.weeks:
        for d in w.days:
            if d.day == long_day:
                continue
            if d.workout.is_quality:
                counts[d.day] += 1
    return counts.most_common(1)[0][0] if counts else None


_MEDLONG_MIN_MI = 8.0


def _is_medium_long(day_obj, long_mi: float, long_day: str) -> bool:
    """A non-long *easy* day big enough to be a medium-long run (Pfitzinger's midweek MLR): it
    carries real aerobic load, so it should read as a key session rather than filler. Threshold:
    ≥ 8 mi and either ≥ 10 mi or ≥ 60% of the week's long run."""
    if day_obj is None or day_obj.day == long_day:
        return False
    wo = day_obj.workout
    if wo.kind not in (WorkoutKind.EASY, WorkoutKind.MEDIUM_LONG):
        return False
    d = wo.distance_mi or 0.0
    return d >= _MEDLONG_MIN_MI and (d >= 10.0 or bool(long_mi) and d >= 0.6 * long_mi)


def _workout_name(label: str) -> str:
    """Short session name: the text before the first ':' and before any distance number."""
    head = (label or "").split(":")[0].strip()
    head = re.split(r"\s+\d", head)[0].strip()  # cut "... 13.1 mi (nonstop)" tails
    return head


def _name_lower(name: str) -> str:
    s = name.lower()
    return s.replace("vo2max", "VO2max").replace("mp ", "MP ").replace(" mp", " MP")


def _trains(workout, is_long: bool) -> str:
    """An infinitive/noun phrase naming the metric the session develops and why it helps the
    marathon — phrased so it reads after the session name regardless of singular/plural."""
    k = workout.kind
    label = (workout.label or "").lower()
    if k == WorkoutKind.THRESHOLD:
        return "to raise your lactate threshold, so goal marathon pace costs less"
    if k == WorkoutKind.INTERVAL:
        return "to build VO2max and aerobic power, which makes threshold and marathon pace feel easier"
    if k == WorkoutKind.REP:
        return "for leg speed and running economy (a smoother, cheaper stride at every pace)"
    if k == WorkoutKind.MARATHON_PACE:
        # A marathon-pace long run banks race-pace volume; the short taper reps just rehearse rhythm.
        if is_long:
            return "to bank goal-pace miles and rehearse race fueling on tired legs"
        return "to rehearse goal race rhythm at a low fatigue cost"
    if k in (WorkoutKind.LONG, WorkoutKind.MEDIUM_LONG):
        if "fartlek" in label:
            return "for aerobic endurance, with light surges to keep the legs honest"
        return "for aerobic endurance and time on feet"
    return "to support the week's aerobic work"


def _purpose_key(workout, is_long: bool) -> str:
    """Identity for "have we already explained why this kind of session helps?" — so the rationale
    is spelled out the first time each session type appears and the bullet stays terse thereafter."""
    if workout.kind == WorkoutKind.MARATHON_PACE:
        return f"marathon_pace:{'long' if is_long else 'reps'}"
    return str(workout.kind)


def _session_clause(day: str, workout, is_long: bool, *, explain: bool = True) -> str:
    name = f"{_DAY_FULL.get(day, day)} {_name_lower(_workout_name(workout.label))}"
    return f"{name} {_trains(workout, is_long)}" if explain else name


def _volume_note(
    week: PlannedWeek, peak_mi: float, is_step_up: bool, is_first_peak: bool, is_first_step_up: bool
) -> str:
    if week.phase == "Taper":
        return ""
    t = week.target_miles
    if peak_mi and t >= peak_mi - 0.5:
        # Only narrate the peak the first time it's reached; later peak weeks just hold it.
        return f"Volume reaches the {peak_mi:g}-mile peak, the biggest sustained load of the block." if is_first_peak else ""
    if is_step_up:
        # Spell out the ramp logic once (first step-up); later step-ups just state the new number.
        if is_first_step_up:
            return f"Volume steps up to {t:g} mi (about +1 mile per running day) on the way to the {peak_mi:g}-mile peak."
        return f"Volume steps up to {t:g} mi."
    return ""


def _week_why(
    week: PlannedWeek,
    quality_day: str | None,
    long_day: str,
    peak_mi: float,
    is_step_up: bool,
    *,
    show_phase_intent: bool,
    is_first_peak: bool,
    is_first_step_up: bool,
    explained: set[str],
    show_vo2_note: bool,
    execution: WeekExecution | None = None,
) -> str:
    """Explain the week without repeating boilerplate every row: the phase intention is stated once
    (``show_phase_intent``), each session type's *why* is spelled out only the first time it appears
    (tracked in ``explained``), the VO2-deferral caveat shows once, and the volume ramp is explained
    once — so each week then carries only what's specific to it. When the week has already been run,
    ``execution`` appends what the monitor saw (short volume, a missed quality day, a coach note)."""
    exec_note = _execution_note(execution) if execution is not None else None

    def _with_execution(text: str) -> str:
        return f"{text}\n\n{exec_note}" if exec_note else text

    if week.is_down_week:
        return _with_execution(
            "This is a recovery week, so volume drops about 20% to let the body absorb the previous block.\n"
            "Keep the long run easy and the quality light, because this is where the adaptations consolidate."
        )

    tune_up = _tune_up_day(week)
    if tune_up is not None:
        name = _workout_name(tune_up.workout.label)
        return _with_execution(
            f"This is a tune-up race week. {name} replaces the long run, on a cut-back week so you race it "
            "fresh. It is the mid-block fitness check, and it tells you whether your goal pace is on "
            "track or needs re-anchoring. Race it hard, then recover, because it's the week's only quality."
        )

    by_day = {d.day: d for d in week.days}
    # Each section is its own block (separated by a blank line) so the cell scans top-to-bottom:
    # phase intent → this week's quality (one bullet per session) → any caveats → the volume story.
    parts: list[str] = []
    if show_phase_intent:
        parts.append(_PHASE_INTENT.get(week.phase, f"{week.phase} week."))

    clauses: list[str] = []
    # List every midweek quality session this week (a week can carry two — e.g. Tue + Thu), in
    # calendar order, so a two-quality week reads as two efforts rather than hiding the second.
    for d in WEEK_ORDER:
        if d == long_day:
            continue
        wd = by_day.get(d)
        if wd is not None and wd.workout.is_quality:
            key = _purpose_key(wd.workout, is_long=False)
            clauses.append(_session_clause(d, wd.workout, is_long=False, explain=key not in explained))
            explained.add(key)
    lr = by_day.get(long_day)
    if lr is not None and lr.workout.kind != WorkoutKind.REST:
        if week.phase == "Taper" and not lr.workout.is_quality:
            clauses.append(f"{_DAY_FULL.get(long_day, long_day)} a shortened, easy long run to stay loose without adding fatigue")
        else:
            key = _purpose_key(lr.workout, is_long=True)
            clauses.append(_session_clause(long_day, lr.workout, is_long=True, explain=key not in explained))
            explained.add(key)
    if clauses:
        parts.append("Here is your quality this week.\n" + "\n".join(f"• {c}." for c in clauses))

    if show_vo2_note and any("VO2max deferred" in f for f in week.flags):
        parts.append(
            "VO2max is held at threshold this week because the mileage is stepping up, and we don't "
            "stack hard intervals on a volume increase."
        )
        explained.add("vo2_threshold")
    if lr is not None and "Race-practice" in (lr.workout.label or ""):
        parts.append(
            "This is the dress rehearsal, so hold the sustained block at goal pace and practise fueling, "
            "kit and pacing exactly as on race day."
        )

    note = _volume_note(week, peak_mi, is_step_up, is_first_peak, is_first_step_up)
    if note:
        parts.append(note)
    if exec_note:
        parts.append(exec_note)
    return "\n\n".join(parts)


def _cell_label(day_obj) -> str:
    if day_obj is None or day_obj.workout.kind == WorkoutKind.REST:
        return "—"
    wo = day_obj.workout
    label = (wo.label or "").replace("\n", " ").strip()
    if wo.distance_mi is not None and f"{wo.distance_mi:g} mi" not in label:
        label = f"{label} ({wo.distance_mi:g} mi)"
    return label


def _day_cell(day_obj) -> str:
    """Calendar-grid cell: spell out rest days ("Rest Day") rather than blanking them, so the
    week reads as a full Mon→Sun rhythm. Structured sessions are stacked (title, then a blank
    line, then warm-up / main set / cool-down) via :func:`render.workout_cell.format_cell`."""
    if day_obj is None or day_obj.workout.kind == WorkoutKind.REST:
        return "Rest Day"
    return format_cell(_cell_label(day_obj), pace=day_obj.workout.pace)


def _phase_spans(plan: TrainingPlan) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for w in plan.weeks:
        if _is_race_week(w):
            continue  # race week is rendered as its own band, not a training phase
        if spans and spans[-1][0] == w.phase:
            spans[-1] = (w.phase, spans[-1][1], w.index)
        else:
            spans.append((w.phase, w.index, w.index))
    return spans


# Two halves of the athlete-facing "approach" sentence: the coach's *philosophy* (the WHY — how that
# coach thinks about training, paraphrased from the source book) and the *spine* (WHAT this block does).
# We name the method and embed the philosophy so it's clear how the plan was determined.
_METHOD_PHILOSOPHY = {
    "daniels": "intensity dialed to your VDOT fitness score so every pace matches your current "
               "physiology",
    "pfitzinger": "marathon-specific endurance built from higher volume and runs that rehearse race "
                  "demands",
    "higdon": "sustainable, steady mileage aimed at a healthy finish",
    "hanson": "cumulative-fatigue training so you practice the late marathon miles on tired legs",
}
_METHOD_APPROACH = {
    "daniels": "an easy aerobic base, threshold work midweek to lift the lactate ceiling, "
               "marathon-pace volume built into the long run, VO2max sharpeners in race prep, "
               "and a two-week taper",
    "pfitzinger": "medium-long midweek runs, marathon-pace blocks inside the long run, "
                  "lactate-threshold tempos, and VO2max sharpening into a two-week taper",
    "higdon": "steady mileage across a manageable number of days, a weekly long run that climbs "
              "gradually, and a measured taper",
    "hanson": "cumulative-fatigue training with moderate long runs, sustained marathon-pace and "
              "strength work, and a short taper",
}


def _friendly_date(iso: object) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d:%B} {d.day}, {d.year}"
    except (ValueError, TypeError):
        return str(iso or "race day")


def _join_clauses(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _realism_sentences(plan: TrainingPlan, goal_s: int | None) -> list[str]:
    """Predicted finish + goal-realism verdict, grounded in the readiness model (same engine the
    coach report uses), so the summary matches the hand-curated tabs' realism paragraph."""
    from engine.readiness import goal_feasibility
    from engine.vdot import RACE_METERS, predict_race_time

    out: list[str] = []
    predicted = predict_race_time(plan.vdot, RACE_METERS["Marathon"])
    if predicted:
        out.append(f"Current fitness predicts a marathon around {_fmt_pred(predicted)}.")
    if not goal_s:
        return out

    build_weeks = sum(1 for w in plan.weeks if w.phase != "Taper" and not _is_race_week(w)) or 15
    ga = goal_feasibility(plan.vdot, goal_s, build_weeks=build_weeks)
    goal_str = _fmt_goal(goal_s)
    realistic = _fmt_pred(ga.realistic_time_s) if ga.realistic_time_s else None

    if ga.verdict == "within_current":
        s = (f"Your {goal_str} goal is at or below current race fitness, so treat it as a controlled "
             "primary rather than a reach.")
        if predicted and predicted + 180 < goal_s:
            stretch_s = (predicted + goal_s) // 2
            s += (f" The fitness you already have points faster, so if the mid-block tune-ups land "
                  f"strong there is a stretch toward ~{_fmt_pred(stretch_s)}; let those results decide "
                  "before you commit to the quicker pace.")
        else:
            s += " Protect it rather than over-reach."
        out.append(s)
    elif ga.verdict == "in_reach":
        s = f"Your {goal_str} goal is in reach (about {ga.gap_vdot:g} VDOT above current)"
        if realistic and ga.realistic_time_s and ga.realistic_time_s < goal_s:
            s += f", and a strong block projects toward ~{realistic}, a sensible primary with upside."
        else:
            s += "."
        out.append(s)
    elif ga.verdict == "stretch":
        out.append(f"A {goal_str} goal needs VDOT {ga.required_vdot:g}, a stretch even on a "
                   f"near-perfect block, so a realistic target off this build is closer to {realistic}.")
        out.append("A tune-up 5K/10K mid-block will confirm whether the faster end is on the table.")
    else:  # unrealistic
        out.append(f"A {goal_str} goal needs VDOT {ga.required_vdot:g}, but this build realistically "
                   f"reaches about VDOT {ga.projected_vdot:g} (~{realistic}); consider re-anchoring the target.")
        out.append("A tune-up 5K/10K mid-block will set real paces before committing.")
    return out


def _approach_paragraph(plan: TrainingPlan, inputs: AthleteInputs, *, include_tailoring: bool = True) -> str:
    method_key = (plan.method or "").lower()
    spine = _METHOD_APPROACH.get(
        method_key,
        "a progressive build with a weekly long run, midweek quality, and a taper",
    )
    why = _METHOD_PHILOSOPHY.get(method_key)
    extras: list[str] = []
    if include_tailoring:
        if inputs.long_run_cap_mi:
            extras.append(f"the long run ramps progressively to {inputs.long_run_cap_mi:g} mi")
        if (inputs.weekday_quality_sessions or 1) >= 2:
            extras.append("two midweek quality runs (a threshold session plus a goal-pace race-practice run)")
        if inputs.quality_long_runs_race_prep_only:
            extras.append("threshold long runs kept easy, with quality long runs saved for race prep")
    tail = f" It is tailored to you with {_join_clauses(extras)}." if extras else ""
    # Name the method, embed the coach's philosophy (the why), then the block's shape (the what).
    lead = f"The plan follows the {plan.method.title()} approach"
    if why:
        return f"{lead} — {why} — built around {spine}.{tail}"
    return f"{lead}, built around {spine}.{tail}"


def _vdot_provenance_clause(plan: TrainingPlan, dossier: AthleteDossier | None) -> str:
    """HOW the paces were determined, in plain words: where the VDOT came from (the dated race that
    anchored it, when the dossier knows it) and that every pace is read from the Daniels VDOT tables
    for that number. Number-safe — every digit here (the VDOT, the source date) is deterministic."""
    source = ""
    if dossier is not None and dossier.anchor.source_date:
        race = next(
            (r for r in dossier.fitness.races if r.date == dossier.anchor.source_date), None
        )
        when = _friendly_date(dossier.anchor.source_date)
        if race is not None:
            source = f", read from your {race.category} on {when}"
        else:
            source = f", anchored on your fitness as of {when}"
    return (
        f"Every pace in the card below comes from the Daniels VDOT tables for VDOT {plan.vdot:g}{source}."
    )


def _narrative(
    plan: TrainingPlan, inputs: AthleteInputs, *, include_tailoring: bool = True,
    dossier: AthleteDossier | None = None,
) -> str:
    goal_s = plan.goal.get("goal_time_s")
    para1 = [
        f"This {plan.block_weeks}-week {plan.method.title()} plan targets "
        f"{plan.goal.get('name', 'the marathon')} on {_friendly_date(plan.goal.get('date'))} "
        f"at a {_fmt_goal(goal_s)} goal, off VDOT {plan.vdot:g}."
    ]
    para1 += _realism_sentences(plan, goal_s)
    # The opener is the plan's first week, not raw ``w_now``: an off-season backoff (e.g. 2.5 mpw) is
    # resolved up to a real re-entry start by the engine, so quote the week the athlete actually runs.
    opening_mi = round(plan.weeks[0].planned_miles) if plan.weeks else round(inputs.w_now)
    para1.append(
        f"It opens near {opening_mi:g} mpw and builds toward a {plan.peak_miles:g} mpw peak, "
        "climbing gradually at roughly a mile per running day each step, with recovery weeks built in "
        "so the body absorbs each jump before the next."
    )
    if inputs.returning_marathoner:
        para1.append("Paces are anchored on your last marathon block and detrained to today.")
    para1.append(_vdot_provenance_clause(plan, dossier))
    responder = _responder_summary_clause(dossier)
    if responder:
        para1.append(responder)
    return "\n\n".join([" ".join(para1), _approach_paragraph(plan, inputs, include_tailoring=include_tailoring)])


def _fitness_trajectory_clause(dossier: AthleteDossier | None) -> str | None:
    """How fitness has actually moved across the athlete's races — the dossier's responder read,
    which goes beyond raw volume stats (does VDOT track mileage; is speed ahead of endurance)."""
    if dossier is None:
        return None
    fit = dossier.fitness
    if fit.responder in (None, "insufficient-data"):
        return None
    bits: list[str] = []
    if fit.volume_vdot_corr is not None:
        if fit.volume_vdot_corr >= 0.5:
            bits.append(f"your fitness has tracked mileage closely (correlation r={fit.volume_vdot_corr:g})")
        elif fit.volume_vdot_corr < 0.3:
            bits.append(f"your fitness has barely moved with mileage (r={fit.volume_vdot_corr:g})")
    if fit.endurance_gap is not None and fit.endurance_gap >= 3.0:
        bits.append(f"your short-race speed sits about {fit.endurance_gap:g} VDOT above your marathon")
    if not bits:
        return None
    lever = (
        "so the block leans on aerobic durability and consistency rather than chasing peak mileage"
        if fit.responder in ("speed-dominant", "stable")
        else "so a real volume build is justified here"
    )
    # Name the read's provenance: this is judged from race *results* over time, not just mileage.
    return (
        "Reading your race results over time rather than just your mileage, "
        + _join_clauses(bits) + f", {lever}."
    )


def _history_interpretation(
    history: dict | None, inputs: AthleteInputs, plan: TrainingPlan, dossier: AthleteDossier | None = None
) -> str | None:
    """Transparency block: what the athlete's *demonstrated* history shows, and how this plan was
    personalized in response. Sourced from the stored training-block ``capacity_profile`` (see
    ``engine.analyze.compute_capacity_profile``); returns ``None`` when no history is available."""
    prof = (history or {}).get("profile") or {}
    if not prof.get("weeks_with_runs"):
        return _baseline_interpretation(inputs, plan, dossier)

    name = (history or {}).get("marathon_name") or inputs.latest_marathon_race_text or "your last marathon block"
    finish = ""
    mt = (history or {}).get("marathon_time_s")
    if mt:
        finish = f" ({_fmt_goal(mt)})"
    avg_days = prof.get("avg_run_days_per_week") or 0
    max_days = prof.get("max_run_days_per_week") or 0
    peak = prof.get("peak_weekly_miles") or 0
    longest = prof.get("longest_run_excl_race_mi") or 0
    avg_pct = prof.get("avg_long_run_pct") or 0
    max_pct = prof.get("max_long_run_pct") or 0

    shows = (
        f"From your {name} build{finish}, your Strava data shows ~{avg_days:g} run-days per week "
        f"(peaking at {max_days}), a peak of {peak:g} miles per week, and a longest run of {longest:g} "
        f"miles. Your long run averaged {avg_pct:g}% of weekly mileage, sometimes reaching {max_pct:g}%."
    )

    moves: list[str] = []
    if inputs.long_run_cap_mi:
        if longest and inputs.long_run_cap_mi < longest:
            moves.append(f"reduces peak long-run distance to {inputs.long_run_cap_mi:g} miles to lower injury risk")
        else:
            moves.append(f"holds peak long-run distance at {inputs.long_run_cap_mi:g} miles")
    moves.append("adds more consistent aerobic volume and recovery spacing")
    reflects = (
        f"The plan keeps your {inputs.days_per_week}-day structure but improves how the workload is "
        f"distributed. It " + _join_clauses(moves) + ". This is a safer, more sustainable version of "
        "what you have already done."
    )
    trajectory = _fitness_trajectory_clause(dossier)
    return f"{shows}\n\n{reflects}" + (f"\n\n{trajectory}" if trajectory else "")


def _baseline_interpretation(
    inputs: AthleteInputs | None, plan: TrainingPlan, dossier: AthleteDossier | None = None
) -> str | None:
    """Personalization fallback when no Strava training block has been ingested: ground the note in
    the athlete's *self-reported* baseline (last marathon + time, demonstrated peak mpw, day count)
    rather than a scraped capacity profile, so a survey-only athlete still gets a tailored block.
    Returns ``None`` only when even the baseline is empty."""
    if inputs is None:
        return None
    last_text = (inputs.latest_marathon_race_text or "").strip()
    if not last_text:  # the self-reported last marathon is the anchor for this block
        return None
    peak_hist = inputs.p_history or 0.0

    finish = f" in {_fmt_goal(inputs.latest_marathon_time_s)}" if inputs.latest_marathon_time_s else ""
    shows_bits: list[str] = [f"you last raced {last_text}{finish}"]
    if peak_hist:
        shows_bits.append(f"built to about {peak_hist:g} miles per week in your last marathon block")
    shows = "From what you shared, " + _join_clauses(shows_bits) + "."

    peak = plan.peak_miles or 0.0
    moves: list[str] = []
    if inputs.long_run_cap_mi:
        moves.append(f"caps your long run at {inputs.long_run_cap_mi:g} miles")
    moves.append(f"rebuilds steadily toward a {peak:g} mpw peak with recovery spacing" if peak
                 else "rebuilds aerobic volume steadily with recovery spacing")
    tail = ", easing you back from your last build" if inputs.returning_marathoner else ""
    reflects = (
        f"The plan keeps your {inputs.days_per_week}-day structure and " + _join_clauses(moves) + tail +
        ". Once you've logged a few weeks on Strava, this note refreshes to your demonstrated training data."
    )
    trajectory = _fitness_trajectory_clause(dossier)
    return f"{shows}\n\n{reflects}" + (f"\n\n{trajectory}" if trajectory else "")


def _double_sentence(plan: TrainingPlan) -> str | None:
    """Coach-to-athlete line for a two-marathon cycle: how the block is split between the races."""
    secondary = plan.goal.get("secondary_marathons") or []
    primary_date = plan.goal.get("date")
    final_date = plan.goal.get("final_race_date")
    if not secondary or not primary_date or not final_date:
        return None
    races = {primary_date: plan.goal.get("name") or "your goal race"}
    for s in secondary:
        if s.get("date"):
            races[s["date"]] = s.get("name") or "your second marathon"
    if len(races) < 2:
        return None
    first_date = min(races)
    try:
        gap = round((date.fromisoformat(final_date[:10]) - date.fromisoformat(first_date[:10])).days / 7)
    except (ValueError, TypeError):
        return None
    first_name, later_name = races[first_date], races[final_date]
    if primary_date == final_date:  # the goal race is the later one — peak lands on the earlier race
        return (
            f"You're racing two marathons {gap} week(s) apart. Because {first_name} comes first, the "
            f"block peaks for it; {later_name} then runs on residual fitness, so we should talk about "
            "which one you truly want to target."
        )
    return (
        f"You're racing {later_name} {gap} week(s) after {first_name}. The plan builds and tapers to "
        f"{first_name}, then a recovery-and-sharpen bridge carries you into {later_name}, which you'll "
        "run by effort off the fitness you already banked."
    )


def _plan_caution_block(
    history: dict | None, inputs: AthleteInputs, plan: TrainingPlan,
    *, execution: ExecutionSummary | None = None, dossier: AthleteDossier | None = None,
) -> str | None:
    """Coach-to-athlete disclaimer (first person, coach = "I", athlete = "you"): this is a textbook
    method *customized* to the individual, so it deliberately deviates from the formulas. Lists what
    I tailored and the watch-outs that should prompt the athlete to tell me (aggressive goal pace,
    new-territory volume, etc.). Derived deterministically from coach overrides + the goal-vs-fitness
    gap, the dossier responder profile, and what the monitor has seen in execution so far."""
    prof = (history or {}).get("profile") or {}
    demonstrated_peak = prof.get("peak_weekly_miles") or 0.0
    longest_hist = prof.get("longest_run_excl_race_mi") or 0.0
    peak = plan.peak_miles or 0.0

    tailored: list[str] = []
    double = _double_sentence(plan)
    if double:
        tailored.append(double)
    if dossier is not None and dossier.fitness.responder == "speed-dominant":
        tailored.append(
            "Because your speed is ahead of your endurance, I'm biasing this block toward aerobic "
            "durability over peak mileage, so the long run and easy volume are the priority."
        )
    if inputs.aggressive_volume_ramp:
        tailored.append(
            f"I'm ramping your mileage faster than the standard plan, about +1 mile per running day each "
            f"week, to reach a {peak:g} mpw peak."
        )
    if inputs.long_run_cap_mi:
        clause = f"I've capped your long run at {inputs.long_run_cap_mi:g} mi"
        if longest_hist and inputs.long_run_cap_mi < longest_hist:
            clause += f" (your longest run was {longest_hist:g} mi in your last marathon training block) to protect your legs"
        tailored.append(clause + ".")
    if demonstrated_peak and peak > demonstrated_peak + 0.5:
        tailored.append(
            f"This block peaks at {peak:g} mpw, above the ~{demonstrated_peak:g} mpw you reached last "
            "build, so the final weeks are new territory for you."
        )
    if inputs.quality_long_runs_race_prep_only:
        tailored.append("I'm keeping your threshold-phase long runs easy; the hard long runs are saved for race prep.")

    cautions: list[str] = []
    th_s = plan.paces.get("threshold_s")
    mp_s = plan.paces.get("marathon_goal_s") or marathon_pace_s(inputs.goal_marathon_s)
    vdot_mp_s = plan.paces.get("marathon_s")
    goal_s = plan.goal.get("goal_time_s")
    if th_s and mp_s and mp_s <= th_s + 10:
        realistic = ""
        if goal_s:
            from engine.readiness import goal_feasibility

            build_weeks = sum(1 for w in plan.weeks if w.phase != "Taper" and not _is_race_week(w)) or 15
            ga = goal_feasibility(plan.vdot, goal_s, build_weeks=build_weeks)
            if ga.realistic_time_s:
                realistic = f" (a realistic finish off this block is ~{_fmt_pred(ga.realistic_time_s)})"
        cautions.append(
            f"Your goal marathon pace ({_fmt(mp_s)}) is right at or faster than your current threshold "
            f"pace ({_fmt(th_s)}), so {_fmt_goal(goal_s)} is a real stretch{realistic}. Run marathon-pace "
            "segments by effort rather than the clock. If they feel like a hard tempo you couldn't hold for "
            "hours, ease off and tell me, and we'll use a tune-up race to set your real paces."
        )
    elif vdot_mp_s and mp_s and mp_s < vdot_mp_s - 10:
        cautions.append(
            "Your goal pace is faster than your current fitness predicts, so treat marathon-pace work by "
            "effort and let a mid-block tune-up race set your real paces."
        )
    if inputs.aggressive_volume_ramp or inputs.long_run_cap_mi or (demonstrated_peak and peak > demonstrated_peak + 0.5):
        cautions.append(
            "This is more load than your recent history. If a hard day leaves you flat, a long run wrecks "
            "you for days, or you pick up a tweak, that's your signal to tell me, and I'll dial it back."
        )
    if execution is not None and execution.weeks_flagged_short:
        worst = f" (lowest about {round(execution.worst_ratio * 100)}%)" if execution.worst_ratio is not None else ""
        cautions.append(
            f"So far {execution.weeks_flagged_short} week(s) have come in under prescribed volume{worst}. "
            "That's why I'm keeping the ramp conservative rather than pushing, building off what you're "
            "actually banking rather than the ideal. If it's becoming the pattern, tell me and we'll right-size the plan."
        )
    if execution is not None and execution.missed_quality_count:
        cautions.append(
            "Some quality sessions have slipped. Those are the workouts that actually move fitness, so when "
            "a week gets tight, protect the quality day and trim the easy miles instead."
        )

    # Positive reinforcement — only honest when we scored every elapsed week (not just absence of a flag).
    praise: str | None = None
    if execution is not None and execution.scored_full_block and execution.weeks_on_track:
        total = execution.weeks_logged
        on = execution.weeks_on_track
        mean = (
            f", averaging about {round(execution.mean_adherence * 100)}% of prescribed volume"
            if execution.mean_adherence is not None else ""
        )
        if on == total:
            praise = (
                f"You've hit prescribed volume in all {total} week(s) logged so far"
                f"{mean}, and that consistency is the whole game. It's what lets me keep building on schedule."
            )
        else:
            praise = (
                f"You've hit prescribed volume in {on} of {total} week(s) logged so far"
                f"{mean}, which is a solid base. Keep stacking weeks like your best ones."
            )

    if not tailored and not cautions and praise is None:
        return None
    parts: list[str] = [
        f"This is a customized {plan.method.title()} plan. Train to effort as much as to the paces, "
        "and tell me if anything feels like too much."
    ]
    if praise:
        parts.append(praise)
    if tailored:
        parts.append("Here is what I tailored for you.\n" + "\n".join(f"• {c}" for c in tailored))
    if cautions:
        parts.append("Watch out for these, and tell me if any of them happen.\n" + "\n".join(f"• {c}" for c in cautions))
    return "\n\n".join(parts)


def _fmt(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _maybe_smooth(
    summary: str, personalized: str | None, notes: str | None,
    *, dossier: AthleteDossier | None, enabled: bool,
) -> tuple[str, str | None, str | None, bool]:
    """Optionally rephrase the three paragraph surfaces via the LLM boundary (number-safe). Returns
    the (summary, personalized, notes, llm_applied) tuple; ``llm_applied`` is True only when the LLM
    output passed the guard and produced the final text. Returns the deterministic text unchanged
    (llm_applied False) when disabled, no API key, or the guard rejects — rendering stays
    deterministic by default."""
    if not enabled:
        return summary, personalized, notes, False
    from engine.personalization import PersonalizationContext
    from llm.boundary import narrate_personalization

    signals = {"responder": dossier.fitness.responder} if dossier is not None else {}
    surfaces = {"summary": summary, "personalized": personalized or "", "notes": notes or ""}
    ctx = PersonalizationContext.build(surfaces, signals=signals)
    smoothed = narrate_personalization(ctx)
    if not smoothed:
        return summary, personalized, notes, False
    return (
        smoothed.get("summary") or summary,
        (smoothed.get("personalized") or personalized) if personalized else personalized,
        (smoothed.get("notes") or notes) if notes else notes,
        True,
    )


def _collect_narrative_capture(
    sink: list,
    *,
    deterministic: dict[str, str],
    final: dict[str, str],
    inputs: AthleteInputs,
    dossier: AthleteDossier | None,
    execution: ExecutionSummary | None,
    llm_applied: bool,
) -> None:
    """Append versioned `NarrativeRender`s (deterministic vs final per surface) for the distillation
    log. Best-effort: capture must never break rendering. ``athlete_id`` is left blank for the caller
    (which holds the store id) to fill before persisting."""
    try:
        from engine.narrative_capture import build_narrative_captures
        from llm.boundary import NARRATE_PROMPT_VERSION, active_narrate_model
        from store.serialization import athlete_inputs_fingerprint

        signals: dict[str, str] = {}
        if dossier is not None:
            signals["responder"] = dossier.fitness.responder
        if execution is not None and execution.scored_full_block:
            signals["execution"] = f"{execution.weeks_on_track}/{execution.weeks_logged} on-plan"
        sink.extend(
            build_narrative_captures(
                deterministic,
                final,
                athlete_id="",
                template_version=NARRATIVE_TEMPLATE_VERSION,
                llm_applied=llm_applied,
                llm_model=active_narrate_model() if llm_applied else None,
                prompt_version=NARRATE_PROMPT_VERSION if llm_applied else None,
                signals=signals,
                inputs_fingerprint=athlete_inputs_fingerprint(inputs),
            )
        )
    except Exception:  # noqa: BLE001 — observability must not break the plan render
        pass


def build_plan_sheet(
    plan: TrainingPlan,
    inputs: AthleteInputs,
    *,
    history: dict | None = None,
    tune_up_results: list[tuple[float, int, float]] | None = None,
    dossier: AthleteDossier | None = None,
    execution: ExecutionSummary | None = None,
    llm_narrative: bool = False,
    capture: list | None = None,
) -> PlanSheetLayout:
    long_day = _long_day(plan)
    quality_day = _quality_day(plan, long_day)
    # Which day-columns ever carry a medium-long run, so we can both surface them (bold) and give
    # the column enough width to show the longer title without crowding the easy days.
    medlong_days: set[str] = set()
    for w in plan.weeks:
        lr = w.long_run
        lmi = lr.workout.distance_mi or 0.0 if lr else 0.0
        for d in w.days:
            if _is_medium_long(d, lmi, long_day):
                medlong_days.add(d.day)

    # Column plan from B onward (A is a spacer for phase-band merges). The week reads as a plain
    # calendar Mon→Sun (all seven days, rest days included), then the weekly Total, and finally the
    # coach's "Why" last — so the schedule comes first and the rationale is there only if wanted.
    # The quality (Q2) and long-run days just get wider columns and bold emphasis, not their own slots.
    col_specs: list[tuple[str, str]] = [("Wk", "wk"), ("Date", "date")]
    for d in WEEK_ORDER:
        col_specs.append((d, f"day:{d}"))
    col_specs.append(("Total", "total"))
    col_specs.append(("Why", "why"))

    column_kinds = ["spacer"] + [spec[1].split(":")[0] for spec in col_specs]
    ncols = 1 + len(col_specs)
    day_for_col = [None] + [
        (spec[1].split(":", 1)[1] if spec[1].startswith("day:") else None) for spec in col_specs
    ]
    long_col = next(i for i, c in enumerate(day_for_col) if c == long_day)

    widths: list[int] = [16]  # A spacer
    for label, kind in col_specs:
        if kind == "wk":
            widths.append(40)
        elif kind == "date":
            widths.append(56)
        elif kind == "why":
            widths.append(250)
        elif kind == "total":
            widths.append(46)
        elif kind.startswith("day"):
            day = kind.split(":", 1)[1] if ":" in kind else None
            if day in (quality_day, long_day):
                widths.append(200)
            elif day in medlong_days:
                widths.append(140)
            else:
                widths.append(92)
        else:
            widths.append(90)

    def pad(cells: list) -> list:
        return cells + [""] * (ncols - len(cells))

    rows: list[Row] = []
    rows.append(Row("title", pad([plan.athlete or "Plan"])))
    anchor = ""
    if inputs.latest_marathon_race_text and inputs.last_marathon_time_s:
        anchor = (
            f" · Anchor {inputs.latest_marathon_race_text} "
            f"{_fmt_goal(inputs.last_marathon_time_s)}"
        )
    rows.append(
        Row(
            "subtitle",
            pad([f"VDOT {plan.vdot:g} · Goal: {_fmt_goal(plan.goal.get('goal_time_s'))}{anchor}"]),
        )
    )
    # The personalization section (when present) owns the "tailored to you" story, so the narrative
    # drops its tailoring tail to avoid repeating the long-run cap / structure twice.
    det_hist = _history_interpretation(history, inputs, plan, dossier)
    det_summary = _narrative(plan, inputs, include_tailoring=not det_hist, dossier=dossier)
    det_caution = _plan_caution_block(history, inputs, plan, execution=execution, dossier=dossier)
    # Hybrid prose: the deterministic surfaces above are the source of truth; an optional LLM pass may
    # rephrase them for tone (number-safe), falling back to the deterministic text on any failure.
    summary_text, hist_text, caution_text, llm_applied = _maybe_smooth(
        det_summary, det_hist, det_caution, dossier=dossier, enabled=llm_narrative
    )
    if capture is not None:
        _collect_narrative_capture(
            capture,
            deterministic={"summary": det_summary, "personalized": det_hist or "", "notes": det_caution or ""},
            final={"summary": summary_text, "personalized": hist_text or "", "notes": caution_text or ""},
            inputs=inputs, dossier=dossier, execution=execution, llm_applied=llm_applied,
        )

    rows.append(Row("narrative", pad([summary_text])))
    rows.append(Row("blank", pad([])))

    if hist_text:
        rows.append(Row("history_header", pad(["HOW THIS PLAN IS PERSONALIZED TO YOU"])))
        rows.append(Row("history", pad([hist_text])))
        rows.append(Row("blank", pad([])))

    if caution_text:
        rows.append(Row("cautions_header", pad(["PLAN NOTES AND CAUTIONS (READ THIS)"])))
        rows.append(Row("caution", pad([caution_text])))
        rows.append(Row("blank", pad([])))

    p = plan.paces or {}
    rows.append(Row("paces_header", pad(["", "YOUR PACES (per mile)"])))
    rows.append(Row(
        "pace_note",
        pad(["", f"Read from the Daniels VDOT tables for VDOT {plan.vdot:g}, and run them by feel on hard days rather than just the watch."]),
    ))
    # Marathon pace is shown at *goal* pace — the pace the workouts actually cue (engine exposes it
    # as ``marathon_goal``); the VDOT "marathon" entry drives goal-realism, not what the athlete runs.
    kinds_used = {d.workout.kind for w in plan.weeks for d in w.days}
    pace_rows: list[tuple[str, str]] = [
        ("Easy", str(p.get("easy", ""))),
        ("Marathon (goal)", str(p.get("marathon_goal") or p.get("marathon", ""))),
        ("Threshold", str(p.get("threshold", ""))),
    ]
    # Only advertise speed paces the plan actually prescribes (e.g. when VO2max is held at threshold
    # all block there is no Interval day) so the card never lists a pace the athlete never runs.
    if WorkoutKind.INTERVAL in kinds_used:
        pace_rows.append(("Interval", str(p.get("interval", ""))))
    if WorkoutKind.REP in kinds_used:
        pace_rows.append(("Rep", str(p.get("rep", ""))))
    for label, val in pace_rows:
        rows.append(Row("pace", pad(["", label, "", val, ""])))
    # Legend so the in-cell pace colors (applied by the formatter) are decodable at a glance.
    legend = "Workout colors:  Easy · Marathon · Threshold"
    if WorkoutKind.INTERVAL in kinds_used:
        legend += " · Intervals"
    if WorkoutKind.REP in kinds_used:
        legend += " · Reps"
    rows.append(Row("legend", pad(["", legend])))
    rows.append(Row("blank", pad([])))

    # Compact "how to read this tab" legend. The full session-by-session decode lives in the shared
    # Workout Dictionary tab, not here, to keep the execution page lean. The slate-blue and amber lines
    # tie the cell tints to meaning.
    pct = int(round(ON_TRACK_RATIO * 100))
    rows.append(Row("legend", pad(["", "E easy · M marathon pace · T threshold · I intervals · R reps · steady between easy and MP."])))
    rows.append(Row("legend", pad(["", f"A slate-blue week number means you logged under about {pct}% of that week (from Strava), and the Why note explains it. An amber Total means the week climbs above mileage you've shown before, so ramp in carefully. Tune-up cells tint green for on track, amber for watch, and red for behind."])))
    rows.append(Row("blank", pad([])))

    # The day-of-week header is repeated under each phase band (see the loop) so orientation
    # returns every few weeks without a frozen pane; nothing else emits it.
    header_cells: list[str | int | float] = [""] + [spec[0] for spec in col_specs]

    primary_race_name = str(plan.goal.get("name", "Race"))
    # Race name -> ISO date for every marathon on the calendar (primary + secondaries). A marathon
    # double has two race weeks, so each race row resolves its own name/date from its race-day
    # workout instead of always using the primary goal.
    race_dates_by_name: dict[str, str] = {}
    if plan.goal.get("name") and plan.goal.get("date"):
        race_dates_by_name[str(plan.goal["name"])] = str(plan.goal["date"])
    for _s in plan.goal.get("secondary_marathons") or []:
        if _s.get("name") and _s.get("date"):
            race_dates_by_name[str(_s["name"])] = str(_s["date"])

    def _race_band_and_row(wk_index: int, race_week: PlannedWeek | None = None) -> None:
        by_day = {d.day: d for d in race_week.days} if race_week is not None else {}
        race_name = primary_race_name
        race_iso = str(plan.goal.get("date") or "")
        if race_week is not None:
            rday = next((d for d in race_week.days if d.workout.kind == WorkoutKind.RACE), None)
            if rday is not None and rday.workout.label:
                nm = rday.workout.label.split(" - ")[0].strip()
                if nm:
                    race_name = nm
                race_iso = race_dates_by_name.get(race_name, race_iso)
        race_long_date = race_short_date = ""
        try:
            rd = date.fromisoformat(race_iso[:10])
            race_long_date, race_short_date = f"{rd:%B} {rd.day}", f"{rd:%b} {rd.day}"
        except (ValueError, TypeError):
            pass
        rows.append(Row("race_band", pad([f"   RACE DAY      {race_long_date} · Execute the plan"])))

        race_line: list[str | int | float] = [""]
        for _label, kind in col_specs:
            if kind == "wk":
                race_line.append(f"W{wk_index}")
            elif kind == "date":
                race_line.append(race_short_date)
            elif kind.startswith("day:"):
                day = kind.split(":", 1)[1]
                d = by_day.get(day)
                # The marathon lands on its actual weekday; the shakeout / easy days keep their
                # own calendar cells. Fall back to the long-run column if there's no race-week data.
                if (d is not None and d.workout.kind == WorkoutKind.RACE) or (race_week is None and day == long_day):
                    race_line.append(race_name.upper())
                else:
                    race_line.append(_day_cell(d))
            elif kind == "total":
                race_line.append(26)
            else:
                race_line.append("")
        rows.append(Row("race_day", pad(race_line), long_col=long_col))

    dates = _saturday_dates(plan)
    spans = {start: (phase, start, end) for phase, start, end in _phase_spans(plan)}
    # Mark weeks whose target rises above every prior week, so the "Why" can call out the +1 mi/day
    # ramp on the weeks it actually steps.
    ups = volume_step_ups([w.target_miles for w in plan.weeks])
    step_up_by_index = {w.index: ups[i] for i, w in enumerate(plan.weeks)}
    peak_mi = plan.peak_miles
    # The phase rationale is stated once, on each phase's first week (the week the band opens).
    phase_start_indices = set(spans.keys())
    # Narrate "reaches peak" only on the first peak-volume training week.
    first_peak_index = next(
        (
            w.index
            for w in plan.weeks
            if not _is_race_week(w) and not w.is_down_week and peak_mi and w.target_miles >= peak_mi - 0.5
        ),
        None,
    )
    first_step_up_index = next((w.index for w in plan.weeks if step_up_by_index.get(w.index)), None)
    # Weeks whose volume exceeds the athlete's demonstrated peak get an amber Total — a glance-level
    # "this is more than you've done before" cue that pairs with the cautions block.
    demonstrated_peak = ((history or {}).get("profile") or {}).get("peak_weekly_miles") or 0.0
    # Mutated as the "Why" column is built top-down: tracks which session purposes (and the
    # VO2-deferral caveat) have already been explained, so the rationale is stated once, not weekly.
    explained_purposes: set[str] = set()
    tune_up_outcomes = _tune_up_outcomes(plan, tune_up_results)
    race_week_seen = False
    for wi, w in enumerate(plan.weeks):
        if _is_race_week(w):
            # The engine folds race day into the final block week; render it as the race row.
            _race_band_and_row(w.index, w)
            race_week_seen = True
            continue

        if w.index in spans:
            phase, a, b = spans[w.index]
            tag = PHASE_TAGLINE.get(phase, "")
            text = f"   {phase.upper()}      Weeks {a}–{b} · {tag}"
            rows.append(Row("phase", pad([text]), phase=phase))
            rows.append(Row("table_header", pad(header_cells)))

        by_day = {d.day: d for d in w.days}
        lr_week = w.long_run
        long_mi = lr_week.workout.distance_mi or 0.0 if lr_week else 0.0
        tune_up_outcome = tune_up_outcomes.get(w.index)
        tune_up_d = _tune_up_day(w)
        week_exec = (
            execution.for_week(week_start=week_start_for_index(plan, w.index), week_index=w.index)
            if execution is not None else None
        )
        line: list[str | int | float] = [""]
        quality_cols: list[int] = []
        medlong_cols: list[int] = []
        tune_up_col: int | None = None
        for _label, kind in col_specs:
            col_idx = len(line)
            if kind == "wk":
                line.append(f"W{w.index}")
            elif kind == "date":
                line.append(dates[wi])
            elif kind == "why":
                why = _week_why(
                    w, quality_day, long_day, peak_mi, step_up_by_index.get(w.index, False),
                    show_phase_intent=(w.index in phase_start_indices),
                    is_first_peak=(w.index == first_peak_index),
                    is_first_step_up=(w.index == first_step_up_index),
                    explained=explained_purposes,
                    show_vo2_note=("vo2_threshold" not in explained_purposes),
                    execution=week_exec,
                )
                # Once a tune-up result has landed, lead the cell with the on-track/behind verdict.
                if tune_up_outcome is not None:
                    why = f"{tune_up_outcome[1]}\n\n{why}"
                line.append(why)
            elif kind == "total":
                line.append(round(w.planned_miles))
            elif kind.startswith("day:"):
                day = kind.split(":", 1)[1]
                day_obj = by_day.get(day)
                cell = _day_cell(day_obj)
                if day_obj is not None and day_obj.workout.is_quality:
                    quality_cols.append(col_idx)
                elif _is_medium_long(day_obj, long_mi, long_day):
                    cell = cell.replace("Easy Run", "Medium-long Run", 1)
                    medlong_cols.append(col_idx)
                if tune_up_d is not None and day_obj is tune_up_d:
                    tune_up_col = col_idx
                line.append(cell)
            else:
                line.append("")
        rows.append(
            Row(
                "week_down" if w.is_down_week else "week",
                pad(line),
                phase=w.phase,
                long_col=long_col,
                quality_cols=tuple(quality_cols),
                medlong_cols=tuple(medlong_cols),
                over_capacity=bool(demonstrated_peak) and not w.is_down_week and w.phase != "Taper" and w.target_miles > demonstrated_peak + 0.5,
                short_week=bool(week_exec is not None and week_exec.short),
                tune_up_status=(tune_up_outcome[0] if tune_up_outcome else None),
                tune_up_col=(tune_up_col if tune_up_outcome else None),
            )
        )

    if not race_week_seen:
        _race_band_and_row(len(plan.weeks) + 1)

    return PlanSheetLayout(
        rows=rows,
        ncols=ncols,
        column_widths=widths,
        long_day=long_day,
        quality_day=quality_day or "",
        column_kinds=column_kinds,
    )


def plan_to_values(plan: TrainingPlan) -> list[list[str | int | float]]:
    """Legacy flat grid (metadata + weeks). Kept for tests / non-styled fallback."""
    meta_rows: list[list[str | int | float]] = [
        ["athlete", plan.athlete],
        ["method", plan.method],
        ["vdot", plan.vdot],
        ["peak_miles", plan.peak_miles],
        ["block_weeks", plan.block_weeks],
    ]
    header = ["week", "phase", "label", "target_mi", "planned_mi"] + list(DAY_NAMES)
    rows: list[list[str | int | float]] = meta_rows + [[]] + [header]
    for w in plan.weeks:
        by_day = {d.day: d for d in w.days}
        row: list = [w.index, w.phase, w.label, w.target_miles, w.planned_miles]
        for dn in DAY_NAMES:
            d = by_day.get(dn)
            row.append(_cell_label(d) if d else "")
        rows.append(row)
    return rows
