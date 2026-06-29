"""Platform-neutral structured-workout IR + the normalizer from a ``TrainingPlan``.

The engine already emits structured :class:`~engine.plan.models.Workout` objects (segments with
per-mile paces, distances, recoveries). This module flattens those into a flat list of
:class:`ExportStep` with explicit *pace bands* (fast/slow seconds-per-mile), which is what both the
calendar and the Garmin FIT exporter need — a single source of truth for duration/target/repeat
logic so each downstream exporter stays a thin serializer.

Rep blocks are expanded into explicit work+recovery steps (a valid, readable workout everywhere);
true FIT repeat loops are a later optimization. Pure stdlib so the engine can stay import-free of
the export layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.execution import week_start_for_index
from engine.plan.models import DAY_NAMES, TrainingPlan, Workout, WorkoutKind

METERS_PER_MILE = 1609.344

# Easy / aerobic kinds run at the easy band; these never carry a distinct work pace.
_EASY_KINDS = {
    WorkoutKind.EASY,
    WorkoutKind.LONG,
    WorkoutKind.RECOVERY,
    WorkoutKind.MEDIUM_LONG,
    WorkoutKind.GENERAL_AEROBIC,
    WorkoutKind.STRIDES,
}

# Sessions whose segment is a centerpiece flanked by easy running (warm-up before, cool-down after).
# Everything else with segments is an easy/aerobic day with a finishing touch (strides), so the
# easy volume runs first and the rep block closes the session.
_MIDBLOCK_KINDS = {
    WorkoutKind.THRESHOLD,
    WorkoutKind.MARATHON_PACE,
    WorkoutKind.INTERVAL,
    WorkoutKind.REP,
    WorkoutKind.RACE,
}


@dataclass(frozen=True)
class ExportStep:
    """One executable step. ``pace_fast_s``/``pace_slow_s`` are seconds-per-mile bounds (fast = fewer
    seconds); ``None`` means no pace target (open / by-effort)."""

    intensity: str                 # warmup | active | recovery | interval | cooldown | rest
    duration_type: str             # distance | time | open
    label: str
    distance_m: float | None = None
    time_s: int | None = None
    pace_fast_s: int | None = None
    pace_slow_s: int | None = None

    @property
    def speed_low_mps(self) -> float | None:
        """Slow bound as m/s (the lower speed), for FIT custom speed targets."""
        return METERS_PER_MILE / self.pace_slow_s if self.pace_slow_s else None

    @property
    def speed_high_mps(self) -> float | None:
        return METERS_PER_MILE / self.pace_fast_s if self.pace_fast_s else None


@dataclass(frozen=True)
class ExportRepeat:
    """A ``count`` × ``steps`` loop block (e.g. 5 × [1000 m @ I, 2:00 jog]). FIT encodes this as a
    native repeat step; other consumers expand it via :attr:`ExportWorkout.flat_steps`."""

    count: int
    steps: list[ExportStep]


# A workout item is either a single step or a repeat block.
ExportItem = ExportStep | ExportRepeat


@dataclass(frozen=True)
class ExportWorkout:
    """A single day's session, normalized for export."""

    name: str
    sport: str                     # running | cross
    day: str                       # Mon..Sun
    week_index: int
    phase: str
    kind: str                      # WorkoutKind value
    date: str | None               # ISO YYYY-MM-DD (None if it can't be anchored)
    total_mi: float | None
    description: str               # human-readable label/breakdown
    steps: list[ExportItem] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.sport == "running"

    @property
    def flat_steps(self) -> list[ExportStep]:
        """Repeat blocks expanded into a flat step list (for display, totals, and non-FIT export)."""
        out: list[ExportStep] = []
        for item in self.steps:
            if isinstance(item, ExportRepeat):
                for _ in range(item.count):
                    out.extend(item.steps)
            else:
                out.append(item)
        return out


def _pace_band(pace_s: int | None, *, tol_frac: float = 0.015, min_tol_s: int = 2) -> tuple[int | None, int | None]:
    """A fast/slow seconds-per-mile band around a single midpoint pace. Daniels paces are point
    targets; a small tolerance makes watch alerts usable without being twitchy."""
    if not pace_s:
        return None, None
    tol = max(min_tol_s, round(pace_s * tol_frac))
    return pace_s - tol, pace_s + tol


def _easy_band(paces: dict) -> tuple[int | None, int | None]:
    lo, hi = paces.get("easy_low_s"), paces.get("easy_high_s")
    if lo and hi:
        return int(lo), int(hi)  # easy_low_s is the faster (fewer-seconds) bound
    return _pace_band(paces.get("easy_s"))


_TIME_RE = re.compile(r"(\d+):(\d{2})")
_SEC_RE = re.compile(r"(\d+)\s*s\b")
_METERS_RE = re.compile(r"(\d+)\s*m\b")


def _easy_mid_s(paces: dict) -> int | None:
    fast, slow = _easy_band(paces)
    if fast and slow:
        return (fast + slow) // 2
    return paces.get("easy_s")


def _recovery_step(recovery: str | None) -> ExportStep | None:
    """Parse a recovery hint (e.g. ``"60 s jog"``, ``"400 m jog"``, ``"equal-time jog"``) into a
    recovery step. Unparseable / equal-time recoveries become an open (by-effort) jog."""
    if not recovery:
        return None
    text = recovery.strip()
    if (m := _TIME_RE.search(text)):
        secs = int(m.group(1)) * 60 + int(m.group(2))
        return ExportStep("recovery", "time", f"{text}", time_s=secs)
    if (m := _SEC_RE.search(text)):
        return ExportStep("recovery", "time", text, time_s=int(m.group(1)))
    if (m := _METERS_RE.search(text)):
        return ExportStep("recovery", "distance", text, distance_m=float(m.group(1)))
    return ExportStep("recovery", "open", text)


def _recovery_distance_m(recovery: str | None, work_dist_m: float | None, work_pace_s: int | None,
                         easy_mid_s: int | None) -> float:
    """Best-effort meters covered during a recovery, used only to size warmup/cooldown padding."""
    if not recovery or not easy_mid_s:
        return 0.0
    easy_speed = METERS_PER_MILE / easy_mid_s
    text = recovery.strip()
    if (m := _TIME_RE.search(text)):
        return (int(m.group(1)) * 60 + int(m.group(2))) * easy_speed
    if (m := _SEC_RE.search(text)):
        return int(m.group(1)) * easy_speed
    if (m := _METERS_RE.search(text)):
        return float(m.group(1))
    if "equal-time" in text and work_dist_m and work_pace_s:
        work_time_s = work_dist_m * work_pace_s / METERS_PER_MILE
        return work_time_s * easy_speed
    return 0.0


def _segment_steps(workout: Workout, paces: dict) -> list[ExportItem]:
    """Work/recovery items from the segments, padded with warmup/cooldown easy running so the steps
    add up to the session total (segments often encode only the quality block, e.g. the 4 mi @ T
    inside an 8 mi run). Multi-rep segments become a single :class:`ExportRepeat` loop block."""
    core: list[ExportItem] = []
    structured_m = 0.0
    easy_mid = _easy_mid_s(paces)
    for seg in workout.segments:
        if seg.pace_label == "E":
            fast, slow = _easy_band(paces)
        else:
            fast, slow = _pace_band(seg.pace_s)
        reps = max(1, seg.reps)
        work_intensity = "interval" if seg.pace_label in ("I", "R", "T") and reps > 1 else "active"

        if seg.distance_m:
            work = ExportStep(work_intensity, "distance", _seg_label(seg),
                              distance_m=float(seg.distance_m), pace_fast_s=fast, pace_slow_s=slow)
            work_m = float(seg.distance_m)
        elif seg.duration_s:
            work = ExportStep(work_intensity, "time", _seg_label(seg),
                              time_s=int(seg.duration_s), pace_fast_s=fast, pace_slow_s=slow)
            work_m = seg.duration_s * METERS_PER_MILE / seg.pace_s if seg.pace_s else 0.0
        else:
            work = ExportStep(work_intensity, "open", _seg_label(seg), pace_fast_s=fast, pace_slow_s=slow)
            work_m = 0.0

        if reps > 1:
            inner = [work]
            rec_m = 0.0
            if (rec := _recovery_step(seg.recovery)):
                inner.append(rec)
                rec_m = _recovery_distance_m(seg.recovery, seg.distance_m, seg.pace_s, easy_mid)
            core.append(ExportRepeat(count=reps, steps=inner))
            structured_m += reps * (work_m + rec_m)
        else:
            core.append(work)
            structured_m += work_m

    return _pad_warmup_cooldown(core, workout, structured_m, paces)


def _pad_warmup_cooldown(core: list[ExportItem], workout: Workout, structured_m: float,
                         paces: dict) -> list[ExportItem]:
    """Account for easy running the segments don't cover. A mid-block quality session gets a
    warm-up before and cool-down after; an easy/aerobic day with a finishing touch (strides) runs
    the easy volume first and closes with the rep block — so strides land "to finish"."""
    total_m = (workout.distance_mi or 0) * METERS_PER_MILE
    remainder = total_m - structured_m
    fast, slow = _easy_band(paces)
    if remainder < 0.25 * METERS_PER_MILE or not fast:
        return core
    if workout.kind in _MIDBLOCK_KINDS:
        each = round(remainder / 2)
        warmup = ExportStep("warmup", "distance", "Warm-up easy", distance_m=each, pace_fast_s=fast, pace_slow_s=slow)
        cooldown = ExportStep("cooldown", "distance", "Cool-down easy", distance_m=each, pace_fast_s=fast, pace_slow_s=slow)
        return [warmup, *core, cooldown]
    easy = ExportStep("active", "distance", "Easy run", distance_m=round(remainder), pace_fast_s=fast, pace_slow_s=slow)
    return [easy, *core]


def _seg_label(seg) -> str:
    if seg.distance_m:
        return f"{seg.distance_m:g} m @ {seg.pace_label}"
    if seg.duration_s:
        return f"{seg.duration_s}s @ {seg.pace_label}"
    return f"@ {seg.pace_label}"


def _single_step(workout: Workout, paces: dict) -> list[ExportStep]:
    """A steady run with no sub-structure: one distance step at the right band."""
    if workout.kind == WorkoutKind.MARATHON_PACE:
        fast, slow = _pace_band(paces.get("marathon_goal_s") or workout.pace_s)
    elif workout.kind in _EASY_KINDS:
        fast, slow = _easy_band(paces)
    else:
        fast, slow = _pace_band(workout.pace_s)
    dist = (workout.distance_mi or 0) * METERS_PER_MILE
    if dist <= 0:
        return [ExportStep("active", "open", workout.label, pace_fast_s=fast, pace_slow_s=slow)]
    return [ExportStep("active", "distance", workout.label, distance_m=round(dist),
                       pace_fast_s=fast, pace_slow_s=slow)]


def _day_date(plan: TrainingPlan, week_index: int, day: str) -> str | None:
    monday = week_start_for_index(plan, week_index)
    if not monday:
        return None
    try:
        return (date.fromisoformat(monday) + timedelta(days=DAY_NAMES.index(day))).isoformat()
    except (ValueError, KeyError):
        return None


def workout_to_export(plan: TrainingPlan, week, day, *, paces: dict) -> ExportWorkout | None:
    """Normalize one :class:`PlannedDay` into an :class:`ExportWorkout` (``None`` for rest days)."""
    w = day.workout
    if w.kind == WorkoutKind.REST:
        return None
    sport = "cross" if w.kind == WorkoutKind.CROSS else "running"
    if sport == "cross":
        mins = w.duration_min or 60
        steps = [ExportStep("active", "time", w.label, time_s=mins * 60)]
    elif w.segments:
        steps = _segment_steps(w, paces)
    else:
        steps = _single_step(w, paces)
    name = f"W{week.index} {day.day} — {w.label}"
    return ExportWorkout(
        name=name[:80],
        sport=sport,
        day=day.day,
        week_index=week.index,
        phase=week.phase,
        kind=w.kind.value,
        date=_day_date(plan, week.index, day.day),
        total_mi=w.distance_mi,
        description=w.label,
        steps=steps,
    )


def plan_to_workouts(plan: TrainingPlan, *, running_only: bool = False) -> list[ExportWorkout]:
    """Every exportable session in calendar order. ``running_only`` drops cross-training days."""
    out: list[ExportWorkout] = []
    for week in plan.weeks:
        for day in week.days:
            ew = workout_to_export(plan, week, day, paces=plan.paces)
            if ew is None or (running_only and not ew.is_running):
                continue
            out.append(ew)
    return out
