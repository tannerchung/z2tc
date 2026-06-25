"""Tests for the styled plan-sheet layout and workout glossary."""

from __future__ import annotations

from engine.plan import build_plan, common
from engine.plan.models import AthleteInputs
from render.plan_layout import build_plan_sheet
from render.plan_sheet_format import build_format_requests
from render.plan_sheet_theme import PlanSheetTheme
from render.workout_glossary import explain_workout_label


def _cindy_inputs() -> AthleteInputs:
    return AthleteInputs(
        name="Cindy Kim",
        vdot=39.3,
        goal_marathon_s=3 * 3600 + 50 * 60,
        w_now=16.0,
        p_history=38.9,
        longest_run_mi=20.0,
        days_per_week=4,
        race_date="2026-10-11",
        race_name="Chicago Marathon",
        returning_marathoner=True,
        race_fit=True,
        recent_break_days=14,
        # Cindy's standing coach overrides (recorded as ManualOverride events on her athlete
        # record): a faster monitored volume ramp, a long run allowed past the 3 h cap, and
        # quality long runs confined to the race-prep block (easy longs elsewhere, 4-day load).
        aggressive_volume_ramp=True,
        long_run_cap_mi=18,
        quality_long_runs_race_prep_only=True,
    )


def test_explain_q1_long_run():
    label = (
        "Marathon long run 13 mi (nonstop): 3.3 E + 5.5 M + 1 T + 1 M + 2.2 E (M @ 8:46/mi)"
    )
    text = explain_workout_label(label)
    assert "Marathon long run" in text
    assert "3.3 mi easy" in text
    assert "5.5 mi marathon pace" in text
    assert "8:46/mi" in text


def test_layout_shape_matches_club_tab():
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    kinds = [r.kind for r in layout.rows]

    assert layout.rows[0].kind == "title"
    assert layout.rows[0].cells[0] == "Cindy Kim"
    assert "paces_header" in kinds
    assert "table_header" in kinds
    assert "phase" in kinds
    assert "race_band" in kinds
    assert kinds[-1] == "race_day"

    flat = "\n".join(str(c) for row in layout.values for c in row)
    assert "YOUR PACES (per mile)" in flat
    assert "Why" in flat
    assert "BASE" in flat and "Weeks" in flat
    assert "RACE DAY" in flat

    # The week reads as a calendar Mon→Sun (weekend last); rest days are spelled out, not blanked.
    header = next(r for r in layout.rows if r.kind == "table_header").cells
    day_cols = [c for c in header if c in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")]
    assert day_cols == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert "Rest Day" in flat

    # Every emitted row is padded to the declared width.
    assert all(len(r.cells) == layout.ncols for r in layout.rows)
    assert len(layout.column_widths) == layout.ncols


def test_why_explains_whole_week_intention():
    # The single "Why" column should read as the week's intention: the phase goal, the chosen
    # quality days + the metric each targets, and the volume story (not just one workout decode).
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    why_col = layout.column_kinds.index("why")
    whys = [str(r.cells[why_col]) for r in layout.rows if r.kind in ("week", "week_down")]
    blob = "\n".join(whys)

    # Phase intention + a named physiological metric appear.
    assert any("phase" in w for w in whys)
    assert "lactate threshold" in blob and "VO2max" in blob
    # The chosen quality days are named with their purpose: the midweek Q2 (Tuesday on the 4-day
    # week, spaced clear of the long run) and the Saturday long run.
    assert "Tuesday" in blob and "Saturday" in blob
    # The +1 mi/day ramp and the dress rehearsal are called out where they occur.
    assert "+1 mile per running day" in blob
    assert "dress rehearsal" in blob


def test_aggressive_ramp_reaches_peak_only_when_opted_in():
    # With a long climb to peak, the coach's aggressive_volume_ramp override (+1 mi/day every week)
    # reaches and holds the demonstrated peak, whereas the default Daniels 3-week hold tops out
    # short. This confirms the ramp cadence is a per-athlete override, not a default-engine change.
    import dataclasses

    base = dataclasses.replace(_cindy_inputs(), w_now=20.0, coach_target_mpw=70.0, days_per_week=5)

    aggressive = build_plan(dataclasses.replace(base, aggressive_volume_ramp=True))
    a_peak = max(w.target_miles for w in aggressive.weeks if w.phase != "Taper")
    assert a_peak >= aggressive.peak_miles - 0.5

    default = build_plan(dataclasses.replace(base, aggressive_volume_ramp=False))
    d_peak = max(w.target_miles for w in default.weeks if w.phase != "Taper")
    assert d_peak < a_peak - 0.5


def test_long_run_cap_override_builds_past_the_time_cap():
    # The long_run_cap_mi override lets Cindy's long run reach 18 mi (over the 3 h / share caps);
    # without it the same athlete is held well under that by the safety caps.
    import dataclasses

    capped = build_plan(_cindy_inputs())
    capped_peak_long = max(
        d.workout.distance_mi
        for w in capped.weeks
        for d in w.days
        if d.workout and d.workout.distance_mi and "ong run" in (d.workout.label or "")
    )
    assert capped_peak_long >= 17.9

    default = build_plan(dataclasses.replace(_cindy_inputs(), long_run_cap_mi=None))
    default_peak_long = max(
        d.workout.distance_mi
        for w in default.weeks
        for d in w.days
        if d.workout and d.workout.distance_mi and "ong run" in (d.workout.label or "")
    )
    assert default_peak_long < capped_peak_long


def test_quality_long_runs_confined_to_race_prep_when_opted_in():
    # With the override, no Base/Threshold long run is a quality session (the midweek Q2 carries
    # the quality); quality long runs exist only in the race-prep block. Default keeps the
    # phase-rotated quality long runs.
    import dataclasses

    sparse = build_plan(_cindy_inputs())
    for w in sparse.weeks:
        lr = w.long_run
        if lr and lr.workout.is_quality:
            assert w.phase == "Race Prep", f"week {w.index} ({w.phase}) has a quality long run"
    assert any(w.long_run and w.long_run.workout.is_quality for w in sparse.weeks if w.phase == "Race Prep")

    default = build_plan(dataclasses.replace(_cindy_inputs(), quality_long_runs_race_prep_only=False))
    assert any(
        w.phase == "Threshold" and w.long_run and w.long_run.workout.is_quality for w in default.weeks
    )


def test_strides_follow_hanson_at_most_one_per_week():
    # House default follows Hanson: easy days stay easy, so at most ONE light stride session per
    # week, and never on every easy run (a plain easy/recovery run always remains).
    plan = build_plan(_cindy_inputs())
    for w in plan.weeks:
        easy = [d for d in w.days if d.workout and (d.workout.label or "").startswith("Easy")]
        stride_runs = [d for d in easy if d.workout.flags and any("strides" in f.lower() for f in d.workout.flags)]
        assert len(stride_runs) <= 1, f"week {w.index}: more than one stride session"
        if len(easy) >= 2:
            assert len(stride_runs) < len(easy), f"week {w.index}: strides landed on every easy run"


def test_strides_capped_at_three_weeks_per_phase():
    # Strides are an economy touch, not a weekly fixture: no phase has more than 3 stride weeks,
    # and down/recovery weeks never carry strides.
    from collections import defaultdict

    plan = build_plan(_cindy_inputs())
    per_phase = defaultdict(int)
    for w in plan.weeks:
        has_strides = any(
            d.workout and d.workout.flags and any("strides" in f.lower() for f in d.workout.flags)
            for d in w.days
        )
        if has_strides:
            per_phase[w.phase] += 1
        if w.is_down_week:
            assert not has_strides, f"down week {w.index} should have no strides"
    for phase, count in per_phase.items():
        assert count <= 3, f"{phase} has {count} stride weeks (max 3)"


def test_long_run_ramps_to_cap_with_limited_peak_weeks():
    # The long_run_cap_mi override ramps the long run up to the cap and only tops out there for the
    # last few build weeks (default 3) — not a jump to the cap held most of the block. The early
    # build long runs climb monotonically and the peak long run lands before the taper.
    import dataclasses

    inputs = _cindy_inputs()
    plan = build_plan(inputs)
    sat_longs = [
        next((d.workout.distance_mi for d in w.days if d.day == "Sat" and d.workout.distance_mi), 0.0)
        for w in plan.weeks
    ]
    cap = inputs.long_run_cap_mi
    at_cap = [mi for mi in sat_longs if mi >= cap - 0.1]
    assert at_cap, "long run should reach the cap"
    assert len(at_cap) <= common.DEFAULT_LONG_RUN_PEAK_WEEKS, "too many weeks at the long-run cap"

    # Non-down build long runs climb monotonically; down weeks dip as cutbacks (excluded here).
    climbing = [
        sat_longs[w.index - 1]
        for w in plan.weeks
        if w.index <= 8 and not w.is_down_week and sat_longs[w.index - 1]
    ]
    assert climbing == sorted(climbing), "non-down long runs should ramp up monotonically"
    assert max(climbing) < cap - 1.0, "early long runs should be well under the cap"

    # Fewer permitted peak weeks => fewer (or equal) weeks actually sitting at the cap.
    two = build_plan(dataclasses.replace(inputs, long_run_peak_weeks=2))
    two_at_cap = sum(
        1 for w in two.weeks
        if any(d.day == "Sat" and d.workout.distance_mi and d.workout.distance_mi >= cap - 0.1 for d in w.days)
    )
    assert two_at_cap <= 2


def test_four_day_week_rests_the_day_before_the_long_run():
    # Higdon-style 4-day spacing: runs cluster Mon–Thu and Friday is rest, so a growing easy run
    # never lands the day before the Saturday long run, and the midweek Q2 stays clear of it.
    from engine.plan.models import WorkoutKind

    plan = build_plan(_cindy_inputs())
    for w in plan.weeks[:-1]:  # exclude race week (its own structure)
        by_day = {d.day: d.workout for d in w.days}
        assert by_day["Fri"].kind == WorkoutKind.REST, f"week {w.index}: Friday should be rest before the long run"
        run_days = [d for d in w.days if d.workout.kind != WorkoutKind.REST]
        assert len(run_days) == 4, f"week {w.index}: expected 4 run days, got {len(run_days)}"
    # Quality (Q2) sessions land on Tuesday, well clear of the Saturday long run.
    q2_days = {
        d.day
        for w in plan.weeks[:-1]  # exclude race week (the race itself counts as quality)
        for d in w.days
        if d.workout.is_quality and d.day != "Sat"
    }
    assert q2_days == {"Tue"}, f"midweek quality should be Tuesday, got {q2_days}"


def test_sunday_race_renders_as_the_last_cell_of_the_week():
    # A Sunday marathon must be the *last* day cell of the final row (Mon→Sun), with that week's
    # shakeout to its left — never with training shown after the race.
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    header = next(r for r in layout.rows if r.kind == "table_header").cells
    race_row = next(r for r in layout.rows if r.kind == "race_day")
    day_cols = [i for i, k in enumerate(layout.column_kinds) if k == "day"]

    race_idx = next(i for i in day_cols if "MARATHON" in str(race_row.cells[i]).upper())
    assert race_idx == day_cols[-1], "race should be the last day cell of the week"
    assert header[race_idx] == "Sun"
    shakeout_idx = next(i for i in day_cols if "Shakeout" in str(race_row.cells[i]))
    assert shakeout_idx < race_idx, "the shakeout must come before the race, not after it"


def test_race_week_easy_runs_land_on_training_days():
    # Race week shouldn't drop a run onto a normal rest day: its easy run(s) fall on the athlete's
    # own training days (Tue here), Wednesday stays rest, and the day before the race is a shakeout.
    from engine.plan.models import WorkoutKind

    plan = build_plan(_cindy_inputs())
    by_day = {d.day: d.workout for d in plan.weeks[-1].days}
    assert by_day["Sun"].kind == WorkoutKind.RACE
    assert "Shakeout" in by_day["Sat"].label
    assert by_day["Wed"].kind == WorkoutKind.REST  # her rest day stays rest
    midweek_easy = [d for d in ("Mon", "Tue", "Thu") if by_day[d].kind != WorkoutKind.REST]
    assert midweek_easy == ["Tue"], f"race-week easy run should be on a training day, got {midweek_easy}"


def test_recovery_weeks_are_shaded():
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    down = [r for r in layout.rows if r.kind == "week_down"]
    assert down, "expected at least one down/recovery week"


def test_format_requests_build_cleanly():
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    reqs = build_format_requests(123, layout, PlanSheetTheme())
    assert reqs
    assert any("repeatCell" in r for r in reqs)
    assert any("mergeCells" in r for r in reqs)
    assert any("updateDimensionProperties" in r for r in reqs)
