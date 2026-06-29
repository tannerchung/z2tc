"""Execution summary — fold the athlete's *accumulating* weekly monitor signals into a structured,
pure read the narrative layer can speak to.

`python main.py monitor` compares the latest plan against weekly Strava actuals and appends
`AdherenceFlag` (volume came in short), `MissedQuality` (a prescribed quality day wasn't run), and
coaches add `WeeklyEvaluation` notes. This module folds those *event payloads* into an
`ExecutionSummary` so the plan-sheet "Why" column and notes block can reflect what actually happened
("last week came in under — we held the ramp") instead of narrating the prescription alone.

Pure: it consumes already-parsed payloads (the impure store read lives in `main.py`). Two builders:
`summarize_execution(payloads)` sees only the monitor's shortfall flags (honestly shortfall-oriented —
it never invents adherence it can't see), while `execution_from_actuals(plan, weekly_actuals)` scores
every elapsed week against its prescription so the narrative can give *earned* positive reinforcement
for on-plan weeks and use shortfalls as context. Weeks with no data render exactly as today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.plan.models import TrainingPlan
from store.events import AdherenceFlagPayload, MissedQualityPayload, WeeklyEvaluationPayload


def week_start_for_index(plan: TrainingPlan, index: int) -> str | None:
    """ISO Monday for a 1-based plan week index, derived from the race date and block length.

    This is the same mapping `monitor_block` uses to key `AdherenceFlag.week_start`, so the renderer
    can look up a week's execution by computing the identical key."""
    anchor = plan.goal.get("final_race_date") or plan.goal.get("date", "")
    try:
        race = date.fromisoformat(str(anchor)[:10])
    except (TypeError, ValueError):
        return None
    try:
        start = race - timedelta(weeks=plan.block_weeks)
        return (start + timedelta(weeks=index - 1)).isoformat()
    except (OverflowError, ValueError):
        return None


ON_TRACK_RATIO = 0.92  # actual/prescribed at/above this is "on plan" (same threshold the monitor flags below)


@dataclass
class WeekExecution:
    """What we know about one executed week. From the events-only path only flagged fields are set;
    from `execution_from_actuals` every elapsed week with data is scored (``verdict`` populated)."""

    week_start: str | None = None
    week_index: int | None = None
    prescribed_mi: float | None = None
    actual_mi: float | None = None
    ratio: float | None = None              # actual/prescribed
    verdict: str | None = None              # "on_track" | "short" when scored from actuals
    missed_quality_days: list[str] = field(default_factory=list)
    coach_note: str = ""

    @property
    def short(self) -> bool:
        if self.verdict is not None:
            return self.verdict == "short"
        return self.ratio is not None and self.ratio < ON_TRACK_RATIO

    @property
    def on_track(self) -> bool:
        return self.verdict == "on_track" or (
            self.verdict is None and self.ratio is not None and self.ratio >= ON_TRACK_RATIO
        )


@dataclass
class ExecutionSummary:
    weeks_flagged_short: int = 0
    missed_quality_count: int = 0
    worst_ratio: float | None = None        # lowest adherence ratio among flagged weeks
    recent_short_week: str | None = None     # week_start of the most recent short flag
    weeks_logged: int = 0                    # elapsed weeks we scored (only from execution_from_actuals)
    weeks_on_track: int = 0                  # of those, weeks at/above the on-plan threshold
    mean_adherence: float | None = None      # mean actual/prescribed over scored weeks
    by_week_start: dict[str, WeekExecution] = field(default_factory=dict)
    by_week_index: dict[int, WeekExecution] = field(default_factory=dict)
    coach_notes: list[tuple[str, str]] = field(default_factory=list)   # (week_start, note)

    @property
    def has_signal(self) -> bool:
        return bool(self.by_week_start or self.by_week_index or self.coach_notes)

    @property
    def scored_full_block(self) -> bool:
        """True when built from actuals (every elapsed week scored), so on-plan weeks are known and
        positive reinforcement is honest — not just the absence of a flag."""
        return self.weeks_logged > 0

    def for_week(self, *, week_start: str | None = None, week_index: int | None = None) -> WeekExecution | None:
        """Merge the volume score (keyed by ``week_start``) with any missed-quality / coach note
        (keyed by ``week_index``) into a single per-week view. None when nothing is known."""
        base = self.by_week_start.get(week_start) if week_start else None
        idx = self.by_week_index.get(week_index) if week_index is not None else None
        if base is None and idx is None:
            return None
        merged = WeekExecution(week_start=week_start, week_index=week_index)
        if base is not None:
            merged.prescribed_mi = base.prescribed_mi
            merged.actual_mi = base.actual_mi
            merged.ratio = base.ratio
            merged.verdict = base.verdict
            merged.coach_note = base.coach_note
        if idx is not None:
            merged.missed_quality_days = list(idx.missed_quality_days)
            merged.coach_note = merged.coach_note or idx.coach_note
        return merged


def _fold_qualitative(s: ExecutionSummary, payloads: list) -> None:
    """Fold missed-quality and coach-evaluation notes (the qualitative signals volume can't show)."""
    for p in payloads:
        if isinstance(p, MissedQualityPayload):
            we = s.by_week_index.setdefault(p.week_index, WeekExecution(week_index=p.week_index))
            if p.day not in we.missed_quality_days:
                we.missed_quality_days.append(p.day)
            s.missed_quality_count += 1
        elif isinstance(p, WeeklyEvaluationPayload) and p.note:
            we = s.by_week_start.setdefault(p.week_start, WeekExecution(week_start=p.week_start))
            we.coach_note = p.note
            s.coach_notes.append((p.week_start, p.note))


def summarize_execution(payloads: list) -> ExecutionSummary:
    """Fold monitor + coach-evaluation payloads into an `ExecutionSummary`. Accepts the parsed
    payload objects (e.g. from `store.events.parse_event_payload`); unrelated kinds are ignored.

    The monitor only flags *problems*, so this path is honestly shortfall-oriented: it never claims a
    week was on-plan it can't see. For positive reinforcement use `execution_from_actuals`, which
    scores every elapsed week against the prescription."""
    s = ExecutionSummary()
    ratios: list[tuple[str, float]] = []
    for p in payloads:
        if isinstance(p, AdherenceFlagPayload):
            we = s.by_week_start.setdefault(p.week_start, WeekExecution(week_start=p.week_start))
            we.prescribed_mi = p.prescribed_mi
            we.actual_mi = p.actual_mi
            we.ratio = p.ratio
            ratios.append((p.week_start, p.ratio))
    _fold_qualitative(s, payloads)

    short = [(ws, r) for ws, r in ratios if r < ON_TRACK_RATIO]
    s.weeks_flagged_short = len(short)
    if short:
        s.worst_ratio = round(min(r for _, r in short), 3)
        s.recent_short_week = max(ws for ws, _ in short)
    return s


def execution_from_actuals(
    plan: TrainingPlan,
    weekly_actuals: dict[str, float],
    *,
    today: date | None = None,
    payloads: list | None = None,
) -> ExecutionSummary:
    """Score *every elapsed week with data* on-plan or short from per-week actual miles
    (``week_start`` ISO Monday -> total run miles), the same weekly totals `monitor` reads.

    Unlike `summarize_execution`, which only sees the monitor's shortfall flags, this knows which
    weeks were hit on plan — so the narrative can lead with earned positive reinforcement and use the
    shortfalls as context for any conservative choices. A week is only scored when it has elapsed
    (``week_start <= today``) and has an actuals entry, so future or no-data weeks are never marked
    short. Optional ``payloads`` fold in missed-quality / coach notes that volume alone can't show."""
    today = today or date.today()
    today_iso = today.isoformat()
    s = ExecutionSummary()
    ratios: list[tuple[str, float]] = []
    for w in plan.weeks:
        target = float(getattr(w, "target_miles", 0.0) or 0.0)
        if target <= 0:
            continue
        ws = week_start_for_index(plan, w.index)
        if not ws or ws > today_iso or ws not in weekly_actuals:
            continue
        actual = float(weekly_actuals.get(ws) or 0.0)
        ratio = round(actual / target, 3)
        we = WeekExecution(
            week_start=ws,
            week_index=w.index,
            prescribed_mi=round(target, 1),
            actual_mi=round(actual, 1),
            ratio=ratio,
            verdict="on_track" if ratio >= ON_TRACK_RATIO else "short",
        )
        s.by_week_start[ws] = we
        s.by_week_index[w.index] = we
        ratios.append((ws, ratio))

    if payloads:
        _fold_qualitative(s, payloads)

    s.weeks_logged = len(ratios)
    short = [(ws, r) for ws, r in ratios if r < ON_TRACK_RATIO]
    s.weeks_flagged_short = len(short)
    s.weeks_on_track = len(ratios) - len(short)
    if ratios:
        s.mean_adherence = round(sum(r for _, r in ratios) / len(ratios), 3)
    if short:
        s.worst_ratio = round(min(r for _, r in short), 3)
        s.recent_short_week = max(ws for ws, _ in short)
    return s
