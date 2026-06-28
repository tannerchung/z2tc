"""Tests for the styled plan-sheet layout and workout glossary."""

from __future__ import annotations

from datetime import date

from engine.execution import summarize_execution, week_start_for_index
from engine.plan import build_club_plan, build_plan, common
from engine.plan.models import AthleteInputs, WorkoutKind
from render.plan_layout import _tune_up_day, build_plan_sheet
from store.events import AdherenceFlagPayload, MissedQualityPayload
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
        # Club engine policy (engine/plan/club.py), resolved here explicitly so these layout tests
        # render Cindy's real (club) sheet: two midweek quality runs eased into the Base phase.
        weekday_quality_sessions=2,
        base_quality_ramp=True,
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


def test_strides_per_phase_override_tightens_the_cap():
    # The strides_per_phase override lowers the per-phase stride budget (Cindy: 2, down from 3).
    import dataclasses
    from collections import defaultdict

    plan = build_plan(dataclasses.replace(_cindy_inputs(), strides_per_phase=2))
    per_phase = defaultdict(int)
    for w in plan.weeks[:-1]:  # race week's primer strides come from the race-week builder, not the budget
        # Count easy-run stride sessions only (the race-week shakeout primer is not budgeted).
        if any(
            d.workout and (d.workout.label or "").startswith("Easy")
            and d.workout.flags and any("strides" in f.lower() for f in d.workout.flags)
            for d in w.days
        ):
            per_phase[w.phase] += 1
    for phase, count in per_phase.items():
        assert count <= 2, f"{phase} has {count} stride weeks (override cap 2)"


def test_two_weekday_quality_default_adds_a_midweek_race_pace_run():
    # Two quality efforts per build week (Tue workout + Thu race-pace run) — except down weeks and
    # weeks the long run is itself a quality session (those stay at two hard sessions total). Base
    # eases the second quality in (one quality early, two by the back half), and the midweek
    # race-pace run seeds race-practice work into the Threshold phase.
    import dataclasses

    inputs = dataclasses.replace(_cindy_inputs(), weekday_quality_sessions=2)
    plan = build_plan(inputs)
    saw_two = False
    base_counts: list[int] = []
    for w in plan.weeks:
        by_day = {d.day: d.workout for d in w.days}
        weekday_quality = [
            d for d in ("Mon", "Tue", "Wed", "Thu", "Fri")
            if by_day.get(d) and by_day[d].is_quality
        ]
        if w.phase == "Base":
            if w.is_down_week:
                assert not weekday_quality, f"base down week {w.index} should stay aerobic"
            else:
                assert set(weekday_quality) <= {"Tue", "Thu"}, weekday_quality
                base_counts.append(len(weekday_quality))
            continue
        if w.phase not in ("Threshold", "Race Prep") or w.is_down_week:
            continue
        long_quality = bool(w.long_run and w.long_run.workout.is_quality)
        if long_quality:
            assert len(weekday_quality) == 1, f"week {w.index}: long is quality, expected 1 weekday quality"
        else:
            assert weekday_quality == ["Tue", "Thu"], f"week {w.index}: expected Tue+Thu quality, got {weekday_quality}"
            assert by_day["Thu"].label.startswith("Race-pace run"), f"week {w.index}: Thu should be the race-pace run"
            saw_two = True
    assert saw_two, "expected build weeks with two weekday quality runs"

    # Base eases the second quality in: it opens at one weekday quality and ramps to two.
    assert base_counts, "expected base build weeks"
    assert base_counts[0] == 1, f"base should open with one quality, got {base_counts}"
    assert base_counts[-1] == 2, f"base should ramp to two quality, got {base_counts}"
    assert base_counts == sorted(base_counts), f"base quality count must be non-decreasing, got {base_counts}"

    # The race-practice (race-pace) run lands in the Threshold phase, not only race prep.
    assert any(
        w.phase == "Threshold" and not w.is_down_week
        and any(d.day == "Thu" and d.workout.label.startswith("Race-pace run") for d in w.days)
        for w in plan.weeks
    ), "expected a midweek race-pace run during the Threshold phase"


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
    # Midweek quality lands on Tuesday (Q2) and Thursday (the second quality), both well clear of
    # the Friday rest and the Saturday long run.
    q2_days = {
        d.day
        for w in plan.weeks[:-1]  # exclude race week (the race itself counts as quality)
        for d in w.days
        if d.workout.is_quality and d.day != "Sat"
    }
    assert q2_days == {"Tue", "Thu"}, f"midweek quality should be Tue/Thu, got {q2_days}"


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


def test_pace_card_shows_goal_marathon_pace_matching_workouts():
    from engine.plan.common import marathon_pace_s

    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp)
    pace = {r.cells[1]: r.cells[3] for r in layout.rows if r.kind == "pace"}
    m, s = divmod(marathon_pace_s(inp.goal_marathon_s), 60)
    # The card must show *goal* MP (what the workouts cue), not the VDOT/current marathon pace.
    assert pace["Marathon (goal)"] == f"{m}:{s:02d}"


def test_pace_card_lists_only_prescribed_speed_zones():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp)
    labels = [r.cells[1] for r in layout.rows if r.kind == "pace"]
    kinds = {d.workout.kind for w in plan.weeks for d in w.days}
    assert {"Easy", "Marathon (goal)", "Threshold"} <= set(labels)
    assert ("Interval" in labels) == (WorkoutKind.INTERVAL in kinds)
    assert ("Rep" in labels) == (WorkoutKind.REP in kinds)


def test_textformat_runs_stay_within_cell_bounds():
    # Guards the class of bug where a run startIndex lands at/after the string end (Sheets 400s).
    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp)
    reqs = build_format_requests(7, layout, PlanSheetTheme())
    seen = 0
    for req in reqs:
        uc = req.get("updateCells")
        if not uc:
            continue
        rng = uc["range"]
        cell = layout.rows[rng["startRowIndex"]].cells[rng["startColumnIndex"]]
        length = len(cell) if isinstance(cell, str) else 0
        idxs = [run.get("startIndex", 0) for run in uc["rows"][0]["values"][0]["textFormatRuns"]]
        assert idxs == sorted(idxs)
        assert all(0 <= i < length for i in idxs), (cell, idxs)
        seen += 1
    assert seen, "expected some rich-text runs"


def test_day_header_repeats_under_each_phase():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp)
    headers = [r for r in layout.rows if r.kind == "table_header"]
    phases = [r for r in layout.rows if r.kind == "phase"]
    assert len(headers) == len(phases) >= 2


def test_why_column_states_recurring_rationale_once():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp)
    blob = "\n".join(str(r.cells[-1]) for r in layout.rows if r.kind in ("week", "week_down"))
    assert blob.count("about +1 mile per running day") <= 1
    assert blob.count("to raise your lactate threshold") <= 1


def test_plan_tab_defers_workout_decode_to_dictionary():
    # The session-by-session decode lives in the shared Workout Dictionary tab, not on every plan
    # execution page, so the plan tab stays lean and keeps only the compact pace/marker legend.
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs())
    assert not any(r.kind in ("workout_key_header", "workout_key") for r in layout.rows)
    legend_blob = "\n".join(str(r.cells[1]) for r in layout.rows if r.kind == "legend")
    assert "easy" in legend_blob and "marathon pace" in legend_blob


def test_is_medium_long_classification():
    from types import SimpleNamespace as NS

    from render.plan_layout import _is_medium_long

    def day(kind, dist, d="Mon"):
        return NS(day=d, workout=NS(kind=kind, distance_mi=dist))

    assert _is_medium_long(day(WorkoutKind.EASY, 13.2), 18, "Sat")     # ≥10 mi
    assert _is_medium_long(day(WorkoutKind.EASY, 10.0), 12, "Sat")     # ≥10 mi
    assert not _is_medium_long(day(WorkoutKind.EASY, 8.3), 18, "Sat")  # <10 and <60% of long
    assert not _is_medium_long(day(WorkoutKind.EASY, 6.0), 12, "Sat")  # below the 8 mi floor
    assert not _is_medium_long(day(WorkoutKind.EASY, 13.0, "Sat"), 13, "Sat")  # the long day itself


def test_caution_block_lists_coach_overrides():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    layout = build_plan_sheet(
        plan, inp, history={"profile": {"peak_weekly_miles": 38.9, "longest_run_excl_race_mi": 20.0}}
    )
    block = next((r.cells[0] for r in layout.rows if r.kind == "caution"), None)
    assert block is not None
    assert "customized Daniels plan" in block
    assert "capped your long run at 18" in block
    assert "+1 mile per running day" in block
    assert "tell me" in block
    assert "your coach" not in block  # first-person voice: coach speaks as "I"/"me"


def test_caution_block_flags_goal_pace_at_or_past_threshold():
    inp = AthleteInputs(
        name="Stretch Goal",
        vdot=37.0,
        goal_marathon_s=3 * 3600 + 45 * 60,
        w_now=20.0,
        p_history=30.0,
        longest_run_mi=20.0,
        days_per_week=3,
        race_date="2026-11-01",
        race_name="NYC Marathon",
        returning_marathoner=True,
        aggressive_volume_ramp=True,
        long_run_cap_mi=18,
        coach_target_mpw=38,
    )
    plan = build_plan(inp)
    layout = build_plan_sheet(
        plan, inp, history={"profile": {"peak_weekly_miles": 29.7, "longest_run_excl_race_mi": 20.7}}
    )
    block = next((r.cells[0] for r in layout.rows if r.kind == "caution"), None)
    assert block is not None
    assert "threshold pace" in block and "stretch" in block
    assert "tune-up race" in block
    # Over-capacity Total cue fires on build weeks above the demonstrated peak, but never on taper.
    over = [r for r in layout.rows if r.kind in ("week", "week_down") and r.over_capacity]
    assert over
    assert all(r.phase != "Taper" for r in over)


def _stretch_inputs() -> AthleteInputs:
    # A stretch goal (low VDOT, fast target) so the club seats a tune-up ladder into the build.
    return AthleteInputs(
        name="Reach", vdot=46.0, goal_marathon_s=3 * 3600 + 5 * 60, w_now=30.0, p_history=40.0,
        longest_run_mi=14.0, days_per_week=5, race_date="2026-11-01", block_weeks=18,
        method=common.DANIELS,
    )


def _marked_rows(layout):
    return [r for r in layout.rows if r.tune_up_status]


def test_tune_up_result_marks_week_on_track():
    # A strong tune-up (measured fitness above the goal's need) tints its race cell on-track and
    # leads the week's "Why" with the verdict.
    inp = _stretch_inputs()
    plan = build_club_plan(inp)
    first = next(w for w in plan.weeks if _tune_up_day(w) is not None)
    results = [(5000.0, 18 * 60, 56.0)]  # measured VDOT well above the 3:05 goal need
    layout = build_plan_sheet(plan, inp, tune_up_results=results)

    marked = _marked_rows(layout)
    assert len(marked) == 1, "exactly the first tune-up week should be marked"
    row = marked[0]
    assert row.tune_up_status == "on_track"
    assert row.tune_up_col is not None
    why = str(row.cells[layout.column_kinds.index("why")])
    assert "On track" in why
    assert f"W{first.index}" in [str(c) for c in row.cells]


def test_tune_up_result_marks_week_behind():
    # A weak tune-up flags the week behind and points the "Why" at re-anchoring.
    inp = _stretch_inputs()
    plan = build_club_plan(inp)
    results = [(5000.0, 28 * 60, 34.0)]  # measured fitness far short of the goal
    layout = build_plan_sheet(plan, inp, tune_up_results=results)

    marked = _marked_rows(layout)
    assert len(marked) == 1 and marked[0].tune_up_status == "behind"
    why = str(marked[0].cells[layout.column_kinds.index("why")])
    assert "Behind" in why and "re-anchor" in why
    # A marked layout still produces clean format requests (the race cell gets tinted).
    assert build_format_requests(1, layout, PlanSheetTheme())


def test_tune_up_results_pair_to_weeks_in_order():
    # Chronological results map to the earliest tune-up weeks first; a second result marks the
    # second tune-up week, leaving any later checkpoints unmarked.
    inp = _stretch_inputs()
    plan = build_club_plan(inp)
    tune_weeks = [w.index for w in plan.weeks if _tune_up_day(w) is not None]
    assert len(tune_weeks) >= 2
    results = [(5000.0, 18 * 60, 55.0), (10000.0, 38 * 60, 50.0)]
    layout = build_plan_sheet(plan, inp, tune_up_results=results)
    marked_weeks = {
        int(str(c)[1:]) for r in _marked_rows(layout) for c in r.cells if str(c).startswith("W")
    }
    assert marked_weeks == set(tune_weeks[:2])


def test_no_tune_up_results_leaves_weeks_unmarked():
    inp = _stretch_inputs()
    plan = build_club_plan(inp)
    layout = build_plan_sheet(plan, inp)
    assert not _marked_rows(layout)


def test_pace_zone_runs_color_detail_lines_not_the_title():
    from render.plan_sheet_format import PACE_EASY, PACE_MP, _pace_text_runs

    cell = "Marathon Long Run — 9 mi\n\n3.3 mi @ Easy\n3.5 mi @ MP (8:35)\n2.2 mi @ Easy"
    runs = _pace_text_runs(cell)
    # First run is empty so the title keeps the cell's base (navy bold) format.
    assert runs[0] == {"format": {}}
    assert all(r["startIndex"] > 0 for r in runs[1:])
    assert [r["startIndex"] for r in runs[1:]] == sorted(r["startIndex"] for r in runs[1:])
    # Each colored run begins exactly at its detail line.
    colors = {cell[r["startIndex"]:].split("\n", 1)[0]: tuple(r["format"]["foregroundColor"][k] for k in ("red", "green", "blue")) for r in runs[1:]}
    assert colors["3.5 mi @ MP (8:35)"] == PACE_MP
    assert colors["3.3 mi @ Easy"] == PACE_EASY
    # A single-line (plain easy) cell needs no rich-text runs.
    assert _pace_text_runs("Easy Run — 6 mi") is None


# --- Personalization from the dossier + accumulating execution -------------------------------

def _speed_dominant_dossier():
    from datetime import date

    from engine import athlete_profile as ap

    races = [
        ap.RacePerformance("2025-05-03", "5K", "5K", 5000.0, 1, 43.0),
        ap.RacePerformance("2025-06-14", "10K", "10K", 10000.0, 1, 39.0),
        ap.RacePerformance("2025-11-02", "Marathon", "Marathon", 42195.0, 1, 37.0),
    ]
    return ap.build_dossier(
        "Cindy Kim", volume_weeks=[], races=races, feed_weeks=None, current_vdot=37.0,
        goals=[("A", 3 * 3600 + 50 * 60)], source_date="2025-11-02", build_weeks=15, today=date(2026, 1, 1),
    )


def _why_for_week(layout, plan, target_index: int) -> str:
    why_col = layout.column_kinds.index("why")
    for r in layout.rows:
        if r.kind in ("week", "week_down") and any(str(c) == f"W{target_index}" for c in r.cells):
            return str(r.cells[why_col])
    return ""


def test_responder_summary_in_narrative():
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs(), dossier=_speed_dominant_dossier())
    narrative = next(r for r in layout.rows if r.kind == "narrative").cells[0]
    assert "speed sits ahead of your endurance" in narrative


def test_narrative_cites_pace_provenance():
    # The summary must explain HOW the paces were determined: Daniels VDOT tables for the athlete's
    # VDOT, and (with a dossier) the dated race that anchored it.
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(plan, _cindy_inputs(), dossier=_speed_dominant_dossier())
    narrative = next(r for r in layout.rows if r.kind == "narrative").cells[0]
    assert "Daniels VDOT tables" in narrative
    assert f"VDOT {plan.vdot:g}" in narrative
    assert "read from your Marathon on November 2, 2025" in narrative
    # And the paces card carries its own provenance note row.
    note = next(r for r in layout.rows if r.kind == "pace_note").cells[1]
    assert "Daniels VDOT tables" in note


def test_personalization_names_strava_source():
    plan = build_plan(_cindy_inputs())
    layout = build_plan_sheet(
        plan, _cindy_inputs(),
        history={"profile": {"weeks_with_runs": 12, "avg_run_days_per_week": 4, "max_run_days_per_week": 5,
                             "peak_weekly_miles": 38.9, "longest_run_excl_race_mi": 20.0,
                             "avg_long_run_pct": 35, "max_long_run_pct": 45}},
        dossier=_speed_dominant_dossier(),
    )
    hist = next(r for r in layout.rows if r.kind == "history").cells[0]
    # Data-first: the note opens on the demonstrated evidence, not a marketing preamble.
    assert "Strava data shows" in hist
    assert hist.startswith("From your")
    assert "race results over time" in hist


def test_personalization_falls_back_to_self_reported_baseline():
    # Survey-only athlete (no ingested Strava training block) still gets a personalization block,
    # grounded in their self-reported last marathon + demonstrated peak rather than scraped data.
    from dataclasses import replace

    inp = replace(
        _cindy_inputs(),
        latest_marathon_race_text="NYC Marathon",
        latest_marathon_time_s=14000,
        p_history=47.9,
    )
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp, history=None)
    hist = next(r for r in layout.rows if r.kind == "history").cells[0]
    assert "From what you shared" in hist
    assert "NYC Marathon" in hist and "3:53:20" in hist
    assert "47.9 miles per week" in hist
    assert "Strava data shows" not in hist  # not the scraped-history phrasing


def test_personalization_absent_without_history_or_baseline():
    from dataclasses import replace

    inp = replace(_cindy_inputs(), latest_marathon_race_text=None, latest_marathon_time_s=None, p_history=0.0)
    plan = build_plan(inp)
    layout = build_plan_sheet(plan, inp, history=None)
    assert not any(r.kind == "history" for r in layout.rows)


def test_responder_and_trajectory_clause_units():
    from render.plan_layout import _fitness_trajectory_clause, _responder_summary_clause

    d = _speed_dominant_dossier()
    assert "durability" in (_responder_summary_clause(d) or "")
    clause = _fitness_trajectory_clause(d)
    assert clause and "VDOT above your marathon" in clause
    assert _responder_summary_clause(None) is None
    assert _fitness_trajectory_clause(None) is None


def test_execution_feedback_only_on_landed_weeks():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    # A real build week (not down/taper/race) to flag short, and a different build week left clean.
    build_weeks = [w for w in plan.weeks if not w.is_down_week and w.phase not in ("Taper",) and not _is_marathon_week(plan, w)]
    short_idx = build_weeks[1].index
    clean_idx = build_weeks[-1].index
    ws = week_start_for_index(plan, short_idx)
    ex = summarize_execution([
        AdherenceFlagPayload(week_start=ws, prescribed_mi=20.0, actual_mi=12.0, ratio=0.60),
        MissedQualityPayload(week_index=short_idx, day="Tue", expected_label="Threshold"),
    ])
    layout = build_plan_sheet(plan, inp, execution=ex)

    assert "You logged about 12 of 20" in _why_for_week(layout, plan, short_idx)
    assert "quality session slipped (Tuesday)" in _why_for_week(layout, plan, short_idx)
    assert "prescribed miles this week" not in _why_for_week(layout, plan, clean_idx)

    caution = next((r.cells[0] for r in layout.rows if r.kind == "caution"), "")
    assert "come in under prescribed" in caution


def test_short_week_explained_and_marked():
    # A short week explains plainly what happened, that it's measured from Strava against the on-plan
    # threshold, and gets a per-week visual marker distinct from the over-capacity amber Total.
    inp = _cindy_inputs()
    plan = build_plan(inp)
    build_weeks = [w for w in plan.weeks if not w.is_down_week and w.phase not in ("Taper",) and not _is_marathon_week(plan, w)]
    short_idx = build_weeks[1].index
    ws = week_start_for_index(plan, short_idx)
    ex = summarize_execution([
        AdherenceFlagPayload(week_start=ws, prescribed_mi=20.0, actual_mi=12.0, ratio=0.60),
        MissedQualityPayload(week_index=short_idx, day="Tue", expected_label="Threshold"),
    ])
    layout = build_plan_sheet(plan, inp, execution=ex)
    why = _why_for_week(layout, plan, short_idx)
    assert "flagged short" in why
    assert "Strava log" in why
    assert "92%" in why  # the on-plan threshold stated in plain language
    assert "the same week that came in short" in why  # missed-quality tied to the volume flag

    short_rows = [r for r in layout.rows if r.kind in ("week", "week_down") and r.short_week]
    assert short_rows and any(f"W{short_idx}" in [str(c) for c in r.cells] for r in short_rows)

    # The short-week marker tints the Wk cell, distinct from the over-capacity amber Total.
    from render.plan_sheet_format import build_format_requests
    from render.plan_sheet_theme import PlanSheetTheme

    theme = PlanSheetTheme()
    reqs = build_format_requests(5, layout, theme)
    short_bg = list(theme.short_week_bg)
    assert any(
        r.get("repeatCell", {}).get("cell", {}).get("userEnteredFormat", {}).get("backgroundColor")
        == {"red": short_bg[0], "green": short_bg[1], "blue": short_bg[2]}
        for r in reqs
    )


def test_on_plan_weeks_earn_positive_reinforcement():
    # Scored-from-actuals execution: on-plan weeks get praise in their "Why" and the notes block
    # leads with earned consistency, while the shortfall frames the conservative ramp.
    from engine.execution import execution_from_actuals

    inp = _cindy_inputs()
    plan = build_plan(inp)
    build_weeks = [w for w in plan.weeks if not w.is_down_week and w.phase not in ("Taper",) and not _is_marathon_week(plan, w)]
    on_idx = build_weeks[0].index
    short_idx = build_weeks[1].index
    on_w = next(w for w in plan.weeks if w.index == on_idx)
    short_w = next(w for w in plan.weeks if w.index == short_idx)
    today = date(2026, 12, 31)  # well past every week, so both are scored
    actuals = {
        week_start_for_index(plan, on_idx): on_w.target_miles,            # on plan
        week_start_for_index(plan, short_idx): short_w.target_miles * 0.6,  # short
    }
    ex = execution_from_actuals(plan, actuals, today=today)
    assert ex.weeks_on_track >= 1 and ex.weeks_flagged_short >= 1

    layout = build_plan_sheet(plan, inp, execution=ex)
    assert "right on plan" in _why_for_week(layout, plan, on_idx)
    caution = next((r.cells[0] for r in layout.rows if r.kind == "caution"), "")
    assert "hit prescribed volume" in caution
    assert "keeping the ramp conservative" in caution


def test_personalization_is_deterministic():
    inp = _cindy_inputs()
    plan = build_plan(inp)
    d = _speed_dominant_dossier()
    ws = week_start_for_index(plan, 2)
    ex = summarize_execution([AdherenceFlagPayload(week_start=ws, prescribed_mi=20.0, actual_mi=12.0, ratio=0.60)])
    a = build_plan_sheet(plan, inp, dossier=d, execution=ex).values
    b = build_plan_sheet(plan, inp, dossier=d, execution=ex).values
    assert a == b


def _is_marathon_week(plan, week) -> bool:
    from engine.plan.models import WorkoutKind

    return any(dd.workout.kind == WorkoutKind.RACE and (dd.workout.distance_mi or 0) >= 26.0 for dd in week.days)
