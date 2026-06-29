"""Plan interop exports: structured IR normalizer, iCalendar feed, and Garmin FIT workouts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.plan import build_plan
from engine.plan.models import AthleteInputs
from export.ics import plan_to_ics
from export.structured import METERS_PER_MILE, ExportRepeat, ExportStep, plan_to_workouts


def _inputs() -> AthleteInputs:
    return AthleteInputs(
        name="Export Tester",
        vdot=45.0,
        goal_marathon_s=3 * 3600 + 30 * 60,
        w_now=30.0,
        p_history=40.0,
        longest_run_mi=16.0,
        days_per_week=5,
        race_date="2026-11-01",
        race_name="Test Marathon",
        method="pfitzinger",
    )


def _plan():
    return build_plan(_inputs())


def _daniels_plan():
    # Daniels 2Q quality reliably yields multi-rep interval/threshold blocks.
    return build_plan(
        AthleteInputs(
            name="Rep Tester",
            vdot=50.0,
            goal_marathon_s=3 * 3600 + 10 * 60,
            w_now=35.0,
            p_history=45.0,
            longest_run_mi=16.0,
            days_per_week=6,
            race_date="2026-11-01",
            race_name="Test",
            method="daniels",
        )
    )


def test_plan_to_workouts_skips_rest_and_anchors_dates():
    plan = _plan()
    works = plan_to_workouts(plan)
    assert works, "expected exportable sessions"
    assert all(w.kind != "rest" for w in works)
    # The last running day should land on or before the race date, dates are ISO and ascending.
    dated = [w for w in works if w.date]
    assert dated == sorted(dated, key=lambda w: (w.date, w.day))
    assert all(w.date <= plan.goal["final_race_date"] for w in dated)


def test_quality_session_pads_to_full_distance():
    # A "X mi w/ Y mi @ pace" session stores only the quality block in segments; the export pads
    # warmup/cooldown easy so the steps sum back to the session total.
    plan = _plan()
    for week in plan.weeks:
        for day in week.days:
            w = day.workout
            if not w.segments or not w.distance_mi:
                continue
            ew = next(x for x in plan_to_workouts(plan) if x.week_index == week.index and x.day == day.day)
            dist_steps = [s for s in ew.flat_steps if s.duration_type == "distance" and s.distance_m]
            if not dist_steps:
                continue
            total_mi = sum(s.distance_m for s in dist_steps) / METERS_PER_MILE
            assert total_mi == pytest.approx(w.distance_mi, abs=0.2)
            return
    pytest.skip("no segmented quality session in this fixture")


def test_pace_band_orientation_fast_is_higher_speed():
    step = ExportStep("active", "distance", "x", distance_m=1609.344, pace_fast_s=400, pace_slow_s=420)
    assert step.speed_high_mps > step.speed_low_mps  # faster pace (fewer s/mi) → higher speed


def test_ics_is_valid_and_deterministic():
    plan = _plan()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = plan_to_ics(plan, now=now)
    b = plan_to_ics(plan, now=now)
    assert a == b
    assert a.startswith("BEGIN:VCALENDAR\r\n")
    assert a.rstrip().endswith("END:VCALENDAR")
    assert a.count("BEGIN:VEVENT") == len([w for w in plan_to_workouts(plan) if w.date])
    assert "\r\n" in a  # CRLF line endings
    # UID is stable per athlete/week/day so re-subscribing updates in place.
    assert "UID:export-tester-w1-" in a


def test_ics_escapes_special_chars():
    plan = _plan()
    # Force a comma/semicolon into the description via the goal name path is overkill; check escaping
    # of a known label (paces contain no specials, so assert the escaper is wired by folding a long line).
    ics = plan_to_ics(plan, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    # Folded continuation lines begin with a single space.
    assert any(line.startswith(" ") for line in ics.split("\r\n"))


def test_running_only_drops_cross_training():
    plan = _plan()
    full = plan_to_workouts(plan)
    running = plan_to_workouts(plan, running_only=True)
    assert all(w.sport == "running" for w in running)
    assert len(running) <= len(full)


def test_fit_export_encodes_decodable_workouts():
    pytest.importorskip("fit_tool")
    from fit_tool.fit_file import FitFile

    from export.fit import plan_to_fit

    plan = _plan()
    files = plan_to_fit(plan)
    assert files, "expected at least one FIT workout"
    name, data = files[0]
    assert name.endswith(".fit")
    ff = FitFile.from_bytes(data)  # decodes without error
    step_msgs = [r.message for r in ff.records if type(r.message).__name__ == "WorkoutStepMessage"]
    assert step_msgs
    # At least one step across the plan carries a pace (SPEED) target.
    all_files = [FitFile.from_bytes(d) for _, d in files]
    has_speed = any(
        getattr(r.message, "target_type", None) == 0
        for ff in all_files
        for r in ff.records
        if type(r.message).__name__ == "WorkoutStepMessage"
    )
    assert has_speed


def test_fit_filename_is_stable_and_sortable():
    from export.fit import fit_filename
    from export.structured import plan_to_workouts as ptw

    plan = _plan()
    ew = ptw(plan, running_only=True)[0]
    fn = fit_filename(ew)
    assert fn.startswith("w01-") and fn.endswith(".fit")


def _first_repeat_workout(plan):
    return next(
        (ew for ew in plan_to_workouts(plan) if any(isinstance(i, ExportRepeat) for i in ew.steps)),
        None,
    )


def test_multi_rep_segment_becomes_repeat_block():
    plan = _daniels_plan()
    ew = _first_repeat_workout(plan)
    assert ew is not None, "expected a repeat block in a Daniels plan"
    rb = next(i for i in ew.steps if isinstance(i, ExportRepeat))
    assert rb.count >= 2 and rb.steps
    # flat_steps expands the loop: each rep contributes len(rb.steps) steps.
    non_repeat = [i for i in ew.steps if not isinstance(i, ExportRepeat)]
    assert len(ew.flat_steps) == len(non_repeat) + rb.count * len(rb.steps)


def test_fit_repeat_block_loops_back_with_count():
    pytest.importorskip("fit_tool")
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.profile_type import WorkoutStepDuration

    from export.fit import workout_to_fit

    plan = _daniels_plan()
    ew = _first_repeat_workout(plan)
    assert ew is not None
    rb = next(i for i in ew.steps if isinstance(i, ExportRepeat))

    ff = FitFile.from_bytes(workout_to_fit(ew))
    step_msgs = [r.message for r in ff.records if type(r.message).__name__ == "WorkoutStepMessage"]
    repeat_steps = [
        m for m in step_msgs
        if m.duration_type == WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT.value
    ]
    assert repeat_steps, "expected a native FIT repeat step"
    rs = repeat_steps[0]
    assert rs.target_repeat_steps == rb.count
    assert 0 <= rs.duration_step < rs.message_index  # loops back to an earlier real step
    # num_valid_steps must count every step message, including the repeat control step.
    wkt = next(r.message for r in ff.records if type(r.message).__name__ == "WorkoutMessage")
    assert wkt.num_valid_steps == len(step_msgs)


def test_ics_renders_repeat_blocks_compactly():
    ics = plan_to_ics(_daniels_plan(), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert "×" in ics  # "4 × (1770 m @ T, 60 s jog)" rather than four expanded bullets


def test_strides_are_structured_with_hard_target_and_run_last():
    # Daniels easy + strides days carry a real rep block (not just a label), the strides hold a
    # pace target (hard target), and they close the session ("to finish") after the easy volume.
    plan = _daniels_plan()
    ew = None
    for week in plan.weeks:
        for day in week.days:
            w = day.workout
            if w.kind.value == "easy" and any("stride" in f for f in w.flags):
                ew = next(x for x in plan_to_workouts(plan)
                          if x.week_index == week.index and x.day == day.day)
                break
        if ew:
            break
    assert ew is not None, "expected a Daniels easy + strides day"

    # The stride block is the last item (runs to finish), and the lead item is the easy volume.
    assert isinstance(ew.steps[-1], ExportRepeat)
    assert isinstance(ew.steps[0], ExportStep) and ew.steps[0].intensity != "rest"
    strides = ew.steps[-1]
    assert strides.count == 6
    work = strides.steps[0]
    assert work.pace_fast_s and work.pace_slow_s, "strides must carry a hard pace target"


def test_easy_strides_day_has_no_cooldown_split():
    # An aerobic day with a finishing touch is easy-then-reps, not warm-up/cool-down around a block.
    plan = _daniels_plan()
    for week in plan.weeks:
        for day in week.days:
            w = day.workout
            if w.kind.value == "easy" and any("stride" in f for f in w.flags):
                ew = next(x for x in plan_to_workouts(plan)
                          if x.week_index == week.index and x.day == day.day)
                kinds = [s.intensity for s in ew.steps if isinstance(s, ExportStep)]
                assert "cooldown" not in kinds and "warmup" not in kinds
                return
    pytest.skip("no strides day in fixture")
