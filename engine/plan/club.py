"""Zone 2 Track Club engine — the club's house modifications over the pure plan engine.

The generators in this package are **pure/textbook**: same ``AthleteInputs`` always yield the same
``TrainingPlan``, with no club opinions baked in (Daniels' Phase I Base stays aerobic, a single
midweek quality, the textbook 30%/25% long-run share, etc.). This module is the **only** seam where
z2tc's coaching *policy* lives. :func:`apply_club_policy` resolves the club's house defaults onto the
athlete inputs and then production dispatches through the pure ``build_plan``; the pure engine stays
untouched and independently testable.

Precedence is strict and one-directional: **explicit coach choice (event-folded inputs) > club policy
> textbook default**. The resolver only fills fields the coach left *unset* (``None``), so a coach
override always survives — which is why the override-able inputs are tri-state ``Optional``.

Today's club policy (:class:`ClubPolicy`):

- **Two quality efforts every build week** (``weekday_quality_sessions = 2``) rather than Daniels'
  single midweek quality — a coach can still opt an athlete down to ``1``.
- **Ease that second quality into the Base phase** (``base_quality_ramp``) so the block opens at one
  effort and ramps to two, instead of the textbook aerobic-only Base.
- **Allow a larger long-run share** (``long_run_share_cap = 0.50``) so a low-mileage / 3-day athlete
  still reaches a real long run (the textbook 30% only buys ~9 mi off a 30 mpw week). The
  time-on-feet and 18-mi ceilings still bound it.
- **Schedule tune-up races** (``schedule_tune_ups``): the club drops a short/sharp 5K/10K/10K ladder
  into the build (from the readiness tune-up ladder) — no half marathon close to the goal (cf.
  Pfitzinger/Higdon). **Daniels plans get the ladder by default** (an empirical mid-block race is the
  club's preferred way to refine VDOT/paces); other methods get it only when the goal needs fitness
  the athlete hasn't shown yet. A coach can pre-set ``tune_up_races`` (including ``()`` for none).
- **Aggressive-ramp default** (``allow_aggressive_ramp``) is the club's stance on the volume ramp.
  The default is the textbook 3-week hold (``False``); a coach opts an athlete in per-athlete.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date as _date

from . import common, workouts
from .models import (
    DAY_NAMES,
    MARATHON_M,
    AthleteInputs,
    MarathonRace,
    PlannedWeek,
    TrainingPlan,
    TuneUpRace,
    Workout,
    WorkoutKind,
    training_plan_goal_payload,
)


@dataclass(frozen=True)
class ClubPolicy:
    """Declarative source of truth for z2tc's house defaults. This is the only place club opinions
    live; the generators and shared math never reference these numbers directly. Bump ``version``
    when the rules change so stored plans can be reasoned about against the policy that built them."""

    version: int = 2
    weekday_quality_sessions: int = 2     # two midweek quality efforts a build week (vs Daniels' one)
    base_quality_ramp: bool = True        # ease the second quality into Base for two-quality athletes
    long_run_share_cap: float = 0.50      # allow the long run up to 50% of the week (textbook is 0.30/0.25)
    allow_aggressive_ramp: bool = False   # club default for the volume ramp (False = textbook 3-wk hold; coach opts in)
    schedule_tune_ups: bool = True        # drop a short/sharp 5K/10K/10K checkpoint ladder into the build (Daniels: always; other methods: when the goal needs verifying)


CLUB_POLICY = ClubPolicy()


def _default_tune_ups(inputs: AthleteInputs) -> tuple[TuneUpRace, ...]:
    """Build the club's default tune-up ladder from the readiness checkpoints. **Daniels plans get
    the ladder by default** — the club's house stance is that an empirical 5K/10K race mid-block is
    the best way to refine an athlete's VDOT and paces, on-track goal or not. Other methods only get
    the club ladder when the goal needs a VDOT the athlete hasn't demonstrated (a stretch worth
    verifying); an already-in-reach goal gets none. Placement nudges off down weeks / the final build
    week so the pure generator can always seat the race on a real training week."""
    if not inputs.goal_marathon_s or inputs.vdot <= 0:
        return ()

    from engine.readiness import tune_up_ladder

    taper_weeks = min(3, max(0, inputs.block_weeks - 1))
    build_weeks = inputs.block_weeks - taper_weeks
    if build_weeks < 4:
        return ()

    ladder = tune_up_ladder(
        inputs.vdot, inputs.goal_marathon_s,
        build_weeks=build_weeks, taper_weeks=taper_weeks, race_date=inputs.race_date,
    )
    # Daniels always gets the ladder (empirical VDOT/pace feedback is the club default). For other
    # methods, only schedule when the goal is a real stretch — otherwise there's nothing to verify,
    # so don't clutter the block with races.
    is_daniels = (inputs.method or "").lower() == common.DANIELS
    if not is_daniels and (ladder.required_vdot is None or ladder.required_vdot <= inputs.vdot + 0.1):
        return ()

    races: list[TuneUpRace] = []
    used: set[int] = set()
    for cp in ladder.checkpoints:
        wk = cp.week
        if wk % 4 == 0:            # down week — pull the race a week earlier so it lands on a build week
            wk -= 1
        wk = max(1, min(wk, build_weeks - 1))   # keep off the final build week (dress rehearsal)
        if wk in used:
            continue
        used.add(wk)
        races.append(TuneUpRace(week=wk, distance_m=cp.distance_m, label=cp.label, target_time_s=cp.on_track_time_s))
    return tuple(races)


def apply_club_policy(inputs: AthleteInputs, policy: ClubPolicy = CLUB_POLICY) -> AthleteInputs:
    """Resolve the club's house defaults onto ``inputs``, filling only fields the coach left unset
    (``None``) so an explicit coach override always wins. Idempotent: applying it twice is a no-op."""
    changes: dict[str, object] = {}

    weekday_quality = inputs.weekday_quality_sessions
    if weekday_quality is None:
        weekday_quality = policy.weekday_quality_sessions
        changes["weekday_quality_sessions"] = weekday_quality

    # Resolve the Base ramp to a concrete bool: the club enables it only for two-quality athletes.
    if inputs.base_quality_ramp is None:
        changes["base_quality_ramp"] = policy.base_quality_ramp and (weekday_quality or 1) >= 2

    if inputs.long_run_share_cap is None:
        changes["long_run_share_cap"] = policy.long_run_share_cap

    if inputs.aggressive_volume_ramp is None:
        changes["aggressive_volume_ramp"] = policy.allow_aggressive_ramp

    if inputs.tune_up_races is None:
        changes["tune_up_races"] = _default_tune_ups(inputs) if policy.schedule_tune_ups else ()

    return replace(inputs, **changes) if changes else inputs


# ---------------------------------------------------------------------------
# Tune-up placement — a club post-process over the pure plan (method-agnostic)
# ---------------------------------------------------------------------------
_MARATHON_MI = 26.0
_TUNE_UP_CUTBACK = 0.85   # mini-cutback week so the tune-up is raced fresh


def _clock(seconds: int | None) -> str:
    """Race-time clock: H:MM:SS past an hour (Half), else M:SS (5K/10K)."""
    if not seconds:
        return "\u2014"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _is_marathon_week(week: PlannedWeek) -> bool:
    return any(d.workout.kind == WorkoutKind.RACE and (d.workout.distance_mi or 0) >= _MARATHON_MI for d in week.days)


def _has_native_tune_ups(plan: TrainingPlan) -> bool:
    """Some methods (Pfitzinger, Higdon) prescribe their own mid-block tune-up races. Detect a
    non-marathon ``RACE`` already in the plan so the club doesn't stack a second ladder on top."""
    return any(
        d.workout.kind == WorkoutKind.RACE and 0 < (d.workout.distance_mi or 0) < _MARATHON_MI
        for w in plan.weeks
        for d in w.days
    )


def _race_distance_m(workout: Workout) -> float:
    """The distance to size a target against. Prefer the race segment's distance (Pfitzinger's
    '8-15K tune-up' session is 11 mi total but the race itself is 10K); fall back to the session
    miles (Higdon's half is a true 13.1)."""
    for seg in workout.segments or ():
        if seg.distance_m:
            return float(seg.distance_m)
    return round((workout.distance_mi or 0) * common.METERS_PER_MILE)


def _annotate_native_tune_ups(plan: TrainingPlan, inputs: AthleteInputs) -> int:
    """Give a method's *native* tune-up races (Pfitzinger/Higdon) the same goal-linked target the
    club ladder computes: for each native race week, the on-track time that keeps the marathon goal
    alive and the realistic (projected-fitness) mark. Annotates the week's flags; returns the count.
    Distances/weeks stay exactly as the book prints them — we only add what to aim for."""
    from engine.readiness import projected_vdot
    from engine.vdot import RACE_METERS, predict_race_time, vdot_from_race

    goal_s = (plan.goal or {}).get("goal_time_s") or inputs.goal_marathon_s
    required = vdot_from_race(RACE_METERS["Marathon"], goal_s) if goal_s else None
    current = plan.vdot
    build_weeks = sum(1 for w in plan.weeks if w.phase != "Taper") or len(plan.weeks) or 1

    annotated = 0
    for w in plan.weeks:
        race = next(
            (d.workout for d in w.days
             if d.workout.kind == WorkoutKind.RACE and 0 < (d.workout.distance_mi or 0) < _MARATHON_MI),
            None,
        )
        if race is None or not goal_s or required is None:
            continue
        dist = _race_distance_m(race)
        frac = min(1.0, w.index / build_weeks)
        on_track_v = round(current + (required - current) * frac, 1)
        proj_v = projected_vdot(current, w.index)
        on_track_t = predict_race_time(on_track_v, dist)
        proj_t = predict_race_time(proj_v, dist)
        if on_track_t is None:
            continue
        w.flags = list(w.flags) + [
            f"tune-up target: aim \u2264 {_clock(on_track_t)} to stay on pace for {_clock(goal_s)} "
            f"({_clock(proj_t)} is the realistic mark; slower \u2192 re-anchor the goal). "
            "Recompute fitness after with `record-tune-up`."
        ]
        annotated += 1
    return annotated


def _seat_week(by_index: dict[int, PlannedWeek], wanted: int, used: set[int]) -> int | None:
    """Nearest valid build week to ``wanted`` to seat a tune-up: a real training week (not taper, a
    down/cutback week, the marathon week, or one already taken). Searching outward keeps the race
    near its intended fraction of the build even when the target week is a down week for this method."""
    for cand in (wanted, wanted - 1, wanted + 1, wanted - 2, wanted + 2):
        w = by_index.get(cand)
        if w is None or cand in used:
            continue
        if w.phase == "Taper" or w.is_down_week or _is_marathon_week(w):
            continue
        return cand
    return None


def place_tune_up_races(plan: TrainingPlan, inputs: AthleteInputs) -> TrainingPlan:
    """Seat each declared :class:`TuneUpRace` into the plan as a `RACE` on its week's long-run slot,
    on a mini-cutback week so it's run fresh (the race is the week's only quality). This is the club
    seam that makes tune-ups **method-agnostic** — every club plan gets the feedback-loop races, not
    just Daniels — by rewriting the week with :func:`common.assemble_week` rather than per-generator
    code. Mutates the plan's weeks in place and appends summary flags; a no-op when no races are set."""
    races = inputs.tune_up_races or ()
    if not races:
        return plan

    # Defer to a method that already races mid-block (Pfitzinger/Higdon) so we don't double-schedule;
    # those native tune-ups serve the same feedback loop. We don't move them (the book's distances and
    # weeks are deliberate) but we *annotate* them with the same goal-linked target the ladder computes,
    # so those athletes also know what to aim for and can `record-tune-up` the result.
    if _has_native_tune_ups(plan):
        annotated = _annotate_native_tune_ups(plan, inputs)
        plan.flags = list(plan.flags) + [
            f"tune-up ladder deferred: the {plan.method} plan already schedules its own mid-block "
            f"tune-up races; annotated {annotated} with goal-linked target times — record results "
            "with `record-tune-up` to track the goal"
        ]
        return plan

    easy_s, easy_str = common.easy_pace(plan.paces)
    by_index = {w.index: w for w in plan.weeks}
    used: set[int] = set()
    scheduled: list[tuple[int, TuneUpRace]] = []
    new_flags: list[str] = []

    for tu in races:
        seat = _seat_week(by_index, int(tu.week), used)
        if seat is None:
            new_flags.append(
                f"tune-up {tu.label} (week {tu.week}) not scheduled — no open build week nearby "
                "(down/taper/marathon); move it manually"
            )
            continue
        used.add(seat)
        w = by_index[seat]
        race_mi = round(tu.distance_m / common.METERS_PER_MILE, 1)
        race = Workout(WorkoutKind.RACE, f"{tu.label} tune-up race", distance_mi=race_mi)
        target = round(w.target_miles * _TUNE_UP_CUTBACK, 1)
        w.days = common.assemble_week(
            inputs.days_per_week, target, {common.LONG_RUN_DAY: race}, easy_s, easy_str, stride_days=0
        )
        w.target_miles = target
        if "(tune-up)" not in w.label:
            w.label = f"{w.label} (tune-up)"
        tgt = f"; on-track target \u2264 {_clock(tu.target_time_s)} for the goal" if tu.target_time_s else ""
        w.flags = list(w.flags) + [
            f"tune-up race: {tu.label} replaces the long run on a mini-cutback week{tgt}. "
            "Race it hard, then recover \u2014 it's the week's only quality."
        ]
        scheduled.append((seat, tu))

    for seat, tu in sorted(scheduled):
        tgt = f", target \u2264 {_clock(tu.target_time_s)}" if tu.target_time_s else ""
        new_flags.append(
            f"tune-up race scheduled: {tu.label} in week {seat}{tgt} \u2014 replaces that week's long run "
            "on a mini-cutback week; the result tells you mid-block whether the goal is tracking"
        )

    if new_flags:
        plan.flags = list(plan.flags) + new_flags
    return plan


# ---------------------------------------------------------------------------
# Marathon double — one continuous plan: full build to the first race, then a
# recovery → re-sharpen → mini-taper bridge to the second race.
# ---------------------------------------------------------------------------
_RACE_MI = round(MARATHON_M / common.METERS_PER_MILE, 1)


def _valid_iso(s: str | None) -> bool:
    try:
        _date.fromisoformat(str(s)[:10])
        return True
    except (TypeError, ValueError):
        return False


def _weeks_between(d1: str, d2: str) -> int:
    a = _date.fromisoformat(d1[:10])
    b = _date.fromisoformat(d2[:10])
    return round((b - a).days / 7)


def _race_weekday(iso: str) -> str:
    try:
        return DAY_NAMES[_date.fromisoformat(iso[:10]).weekday()]
    except (TypeError, ValueError):
        return common.LONG_RUN_DAY


def _bridge_fracs(n: int) -> list[float]:
    """Bridge week volumes as a fraction of peak: recover, re-sharpen, mini-taper into the race
    (the last entry is the race week). Hand-shaped for the common 2-6 week gaps; a generic ramp
    covers anything longer."""
    shapes = {
        1: [0.45],
        2: [0.45, 0.45],
        3: [0.45, 0.65, 0.45],
        4: [0.40, 0.60, 0.70, 0.45],
        5: [0.40, 0.55, 0.70, 0.60, 0.45],
        6: [0.40, 0.50, 0.65, 0.70, 0.60, 0.45],
    }
    return shapes.get(n) or ([0.40] + [0.65] * (n - 2) + [0.45])


def append_marathon_double_bridge(
    plan: TrainingPlan, inputs: AthleteInputs, *, second_race: MarathonRace, gap_weeks: int
) -> TrainingPlan:
    """Append the bridge from the (already-built) first race to ``second_race``: an opening recovery
    week, easy aerobic re-sharpen weeks with a single light marathon-pace touch, and a mini-taper
    into the second race. Mutates ``plan`` (weeks + block_weeks) and returns it."""
    easy_s, easy_str = common.easy_pace(plan.paces)
    mp_s = plan.paces.get("marathon_goal_s") or common.marathon_pace_s(inputs.goal_marathon_s)
    mp_str = f"{mp_s // 60}:{mp_s % 60:02d}"
    peak = plan.peak_miles or max((w.target_miles for w in plan.weeks), default=20.0)
    fracs = _bridge_fracs(gap_weeks)
    last_idx = plan.weeks[-1].index if plan.weeks else 0
    first_name = plan.goal.get("name") or "the first race"
    race_weekday = _race_weekday(second_race.date)

    extra: list[PlannedWeek] = []
    for j, frac in enumerate(fracs):
        wk = last_idx + j + 1
        target = round(peak * frac, 1)
        is_race = j == len(fracs) - 1
        is_recovery = j == 0 and not is_race
        if is_race:
            race = Workout(WorkoutKind.RACE, f"{second_race.name} - race day", distance_mi=_RACE_MI)
            days = common.race_week_days(
                inputs.days_per_week, race, easy_s, easy_str, race_day=race_weekday,
                stride_pace_s=plan.paces.get("rep_s"),
            )
            extra.append(
                PlannedWeek(
                    index=wk, phase="2nd Race", label=f"{second_race.name} race week",
                    target_miles=target, is_down_week=False, days=days, flags=[],
                )
            )
            continue
        long_mi = round(min(target * 0.5, 10.0 if is_recovery else 15.0), 1)
        fixed: dict[str, Workout] = {common.LONG_RUN_DAY: common.long_run_easy(long_mi, easy_s, easy_str)}
        if not is_recovery and gap_weeks >= 3:
            ctx = workouts.WeekContext(
                caps=common.session_caps(target, mp_s), paces=plan.paces, mp_s=mp_s, mp_str=mp_str,
                easy_s=easy_s, easy_str=easy_str, long_mi=long_mi,
            )
            fixed[common.midweek_quality_day(inputs.days_per_week)] = workouts.named("mp_run", ctx)
        days = common.assemble_week(inputs.days_per_week, target, fixed, easy_s, easy_str, stride_days=0)
        label = f"Post-{first_name} recovery" if is_recovery else f"Bridge to {second_race.name}"
        extra.append(
            PlannedWeek(
                index=wk, phase="Recovery" if is_recovery else "Bridge",
                label=f"{label} (wk {j + 1}/{gap_weeks})",
                target_miles=target, is_down_week=is_recovery, days=days, flags=[],
            )
        )

    plan.weeks = list(plan.weeks) + extra
    plan.block_weeks = len(plan.weeks)
    return plan


def build_marathon_double(inputs: AthleteInputs) -> TrainingPlan | None:
    """If the athlete races two marathons in the cycle, build one continuous plan: a full build +
    taper to the **earlier** race, then a bridge to the **later** race, with the goal/paces anchored
    to whichever race is marked primary. Returns ``None`` when this isn't a two-marathon cycle."""
    from . import build_plan  # local import to avoid a package import cycle

    races = []
    if _valid_iso(inputs.race_date):
        races.append((inputs.race_date, inputs.race_name, True))
    for r in inputs.secondary_races:
        if _valid_iso(r.date):
            races.append((r.date, r.name, False))
    if len(races) < 2:
        return None
    races.sort(key=lambda r: r[0])
    first, second = races[0], races[-1]
    if first[0] == second[0]:
        return None
    primary = next((r for r in races if r[2]), first)
    gap = _weeks_between(first[0], second[0])
    if gap < 1:
        return None

    # Build to the FIRST race; if the primary (goal) race sits later, shorten the build so the whole
    # plan still ends on the second race rather than running past it.
    weeks_first_to_primary = max(0, _weeks_between(first[0], primary[0]))
    build_len = max(4, inputs.block_weeks - weeks_first_to_primary)
    eff = replace(
        inputs, race_date=first[0], race_name=first[1], block_weeks=build_len, secondary_races=()
    )
    plan = place_tune_up_races(build_plan(eff), eff)
    # Guarantee the first race lands on the last build week. Daniels already builds a race week, but
    # some generators (e.g. a non-18-wk Pfitzinger block) only taper without an explicit race day.
    last = plan.weeks[-1]
    if not any(d.workout.kind == WorkoutKind.RACE and (d.workout.distance_mi or 0) >= 26 for d in last.days):
        easy_s, easy_str = common.easy_pace(plan.paces)
        first_race = Workout(WorkoutKind.RACE, f"{first[1]} - race day", distance_mi=_RACE_MI)
        last.days = common.race_week_days(
            eff.days_per_week, first_race, easy_s, easy_str, race_day=_race_weekday(first[0]),
            stride_pace_s=plan.paces.get("rep_s"),
        )
        last.label = f"{first[1]} race week"
    plan = append_marathon_double_bridge(
        plan, inputs, second_race=MarathonRace(second[1], second[0]), gap_weeks=gap
    )
    # Re-anchor the goal payload to the true primary (goal race) and the full secondary list, so the
    # calendar ends on the second race while realism/paces stay keyed to the goal race.
    plan.goal = training_plan_goal_payload(inputs)

    if primary[0] == second[0]:
        note = (
            f"marathon double: your goal race {primary[1]} ({primary[0]}) falls {gap} week(s) after "
            f"{first[1]} ({first[0]}). The block peaks for {first[1]}, so {primary[1]} is run on "
            "residual fitness — decide which race you truly want to target."
        )
    else:
        note = (
            f"marathon double: full build to {first[1]} ({first[0]}), then a {gap}-week "
            f"recovery-to-race bridge to {second[1]} ({second[0]}). Race the second by effort off "
            f"residual fitness; the goal and paces are anchored to {primary[1]}."
        )
    plan.flags = list(plan.flags) + [note]
    return plan
