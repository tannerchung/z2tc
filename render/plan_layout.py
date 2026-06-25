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

from engine.plan.common import volume_step_ups
from engine.plan.models import (
    DAY_NAMES,
    AthleteInputs,
    PlannedWeek,
    TrainingPlan,
    WorkoutKind,
)
from render.plan_sheet_theme import PHASE_TAGLINE
from render.workout_glossary import explain_workout_label

_LONG_KINDS = {WorkoutKind.LONG, WorkoutKind.MARATHON_PACE, WorkoutKind.MEDIUM_LONG}

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
    "Base": "Base phase — build the aerobic engine with easy volume and durability; consistency matters more than pace.",
    "Threshold": "Threshold phase — raise the lactate threshold so goal marathon pace costs less, and start banking goal-pace miles in the long run.",
    "Race Prep": "Race-prep phase — sharpen VO2max and lock in goal marathon pace under fatigue; this is the most race-specific block.",
    "Taper": "Taper — shed accumulated fatigue while keeping the legs sharp: volume drops, but a touch of quality stays so you don't go flat.",
}


def _is_race_week(week: PlannedWeek) -> bool:
    return any(d.workout.kind == WorkoutKind.RACE for d in week.days)


@dataclass
class Row:
    kind: str                       # title|subtitle|narrative|blank|paces_header|pace|
                                    # table_header|phase|week|week_down|race_band|race_day
    cells: list[str | int | float]
    phase: str | None = None
    long_col: int | None = None     # column index of the long-run cell (week rows)
    quality_cols: tuple[int, ...] = ()  # column indices of quality (Q) workouts this week


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
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _saturday_dates(plan: TrainingPlan) -> list[str]:
    """One reference date per week (the week's Saturday), counting back from race day."""
    try:
        race = date.fromisoformat(str(plan.goal.get("date"))[:10])
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


def _session_clause(day: str, workout, is_long: bool) -> str:
    return f"{_DAY_FULL.get(day, day)} {_name_lower(_workout_name(workout.label))} {_trains(workout, is_long)}"


def _volume_note(week: PlannedWeek, peak_mi: float, is_step_up: bool, is_first_peak: bool) -> str:
    if week.phase == "Taper":
        return ""
    t = week.target_miles
    if peak_mi and t >= peak_mi - 0.5:
        # Only narrate the peak the first time it's reached; later peak weeks just hold it.
        return f"Volume reaches the {peak_mi:g}-mile peak — the biggest sustained load of the block." if is_first_peak else ""
    if is_step_up:
        return f"Volume steps up to {t:g} mi (about +1 mile per running day) on the way to the {peak_mi:g}-mile peak."
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
) -> str:
    """Explain the week without repeating the phase rationale every row: the phase intention is
    stated once (``show_phase_intent``, on the phase's first week), and every week then carries
    only what's specific to it — its quality days + the metric each targets, the dress rehearsal /
    deferral notables, and the volume story."""
    if week.is_down_week:
        return (
            "Recovery week — volume drops about 20% so the body absorbs the previous block. "
            "Keep the long run easy and the quality light; this is where the adaptations consolidate."
        )

    by_day = {d.day: d for d in week.days}
    parts: list[str] = []
    if show_phase_intent:
        parts.append(_PHASE_INTENT.get(week.phase, f"{week.phase} week."))

    clauses: list[str] = []
    q2 = by_day.get(quality_day) if quality_day else None
    if q2 is not None and q2.workout.is_quality and quality_day != long_day:
        clauses.append(_session_clause(quality_day, q2.workout, is_long=False))
    lr = by_day.get(long_day)
    if lr is not None and lr.workout.kind != WorkoutKind.REST:
        if week.phase == "Taper" and not lr.workout.is_quality:
            clauses.append(f"{_DAY_FULL.get(long_day, long_day)} a shortened, easy long run to stay loose without adding fatigue")
        else:
            clauses.append(_session_clause(long_day, lr.workout, is_long=True))
    if clauses:
        parts.append("This week's quality: " + "; ".join(clauses) + ".")

    if any("VO2max deferred" in f for f in week.flags):
        parts.append(
            "VO2max is held at threshold this week because the mileage is stepping up — we don't "
            "stack hard intervals on a volume increase."
        )
    if lr is not None and "Race-practice" in (lr.workout.label or ""):
        parts.append(
            "This is the dress rehearsal: hold the sustained block at goal pace and practise fueling, "
            "kit and pacing exactly as on race day."
        )

    note = _volume_note(week, peak_mi, is_step_up, is_first_peak)
    if note:
        parts.append(note)
    return " ".join(parts)


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
    week reads as a full Mon→Sun rhythm."""
    if day_obj is None or day_obj.workout.kind == WorkoutKind.REST:
        return "Rest Day"
    return _cell_label(day_obj)


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


def _narrative(plan: TrainingPlan, inputs: AthleteInputs) -> str:
    goal = _fmt_goal(plan.goal.get("goal_time_s"))
    bits = [
        f"This {plan.block_weeks}-week {plan.method.title()} plan targets "
        f"{plan.goal.get('name', 'the marathon')} on {plan.goal.get('date', '')} "
        f"at a {goal} goal, off VDOT {plan.vdot:g}.",
        f"It opens near {inputs.w_now:g} mpw and builds toward a peak of "
        f"{plan.peak_miles:g} mpw.",
    ]
    if inputs.returning_marathoner:
        bits.append("Paces are anchored on the last marathon block and detrained to today.")
    return " ".join(bits)


def build_plan_sheet(plan: TrainingPlan, inputs: AthleteInputs) -> PlanSheetLayout:
    long_day = _long_day(plan)
    quality_day = _quality_day(plan, long_day)

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
            widths.append(200 if day in (quality_day, long_day) else 92)
        else:
            widths.append(90)

    def pad(cells: list) -> list:
        return cells + [""] * (ncols - len(cells))

    rows: list[Row] = []
    rows.append(Row("title", pad([plan.athlete or "Plan"])))
    anchor = ""
    if inputs.latest_marathon_race_text and inputs.last_marathon_time_s:
        anchor = (
            f" · Anchor: {inputs.latest_marathon_race_text} "
            f"{_fmt_goal(inputs.last_marathon_time_s)}"
        )
    rows.append(
        Row(
            "subtitle",
            pad([f"VDOT {plan.vdot:g} · Goal: {_fmt_goal(plan.goal.get('goal_time_s'))}{anchor}"]),
        )
    )
    rows.append(Row("narrative", pad([_narrative(plan, inputs)])))
    rows.append(Row("blank", pad([])))

    p = plan.paces or {}
    rows.append(Row("paces_header", pad(["", "YOUR PACES (per mile)"])))
    for label, key in (
        ("Easy", "easy"),
        ("Marathon Pace", "marathon"),
        ("Threshold", "threshold"),
        ("Interval", "interval"),
    ):
        rows.append(Row("pace", pad(["", label, "", str(p.get(key, "")), ""])))
    rows.append(Row("blank", pad([])))

    header_cells: list[str | int | float] = [""] + [spec[0] for spec in col_specs]
    rows.append(Row("table_header", pad(header_cells)))

    race_name = str(plan.goal.get("name", "Race"))
    race_long_date = ""   # "October 11"
    race_short_date = ""  # "Oct 11"
    try:
        rd = date.fromisoformat(str(plan.goal.get("date"))[:10])
        race_long_date = f"{rd:%B} {rd.day}"
        race_short_date = f"{rd:%b} {rd.day}"
    except (ValueError, TypeError):
        pass

    def _race_band_and_row(wk_index: int, race_week: PlannedWeek | None = None) -> None:
        by_day = {d.day: d for d in race_week.days} if race_week is not None else {}
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

        by_day = {d.day: d for d in w.days}
        line: list[str | int | float] = [""]
        quality_cols: list[int] = []
        for _label, kind in col_specs:
            col_idx = len(line)
            if kind == "wk":
                line.append(f"W{w.index}")
            elif kind == "date":
                line.append(dates[wi])
            elif kind == "why":
                line.append(
                    _week_why(
                        w, quality_day, long_day, peak_mi, step_up_by_index.get(w.index, False),
                        show_phase_intent=(w.index in phase_start_indices),
                        is_first_peak=(w.index == first_peak_index),
                    )
                )
            elif kind == "total":
                line.append(round(w.planned_miles))
            elif kind.startswith("day:"):
                day_obj = by_day.get(kind.split(":", 1)[1])
                line.append(_day_cell(day_obj))
                if day_obj is not None and day_obj.workout.is_quality:
                    quality_cols.append(col_idx)
            else:
                line.append("")
        rows.append(
            Row(
                "week_down" if w.is_down_week else "week",
                pad(line),
                phase=w.phase,
                long_col=long_col,
                quality_cols=tuple(quality_cols),
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
