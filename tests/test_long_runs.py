"""Club Long Runs projection + Read Me generation."""

from __future__ import annotations

from engine.plan import AthleteInputs, build_plan
from render.long_runs import (
    ClubAthlete,
    build_long_runs_format_requests,
    build_long_runs_layout,
)
from render.plan_sheet_theme import PlanSheetTheme
from render.read_me import build_read_me_layout


def HMS(h, m, s):
    return h * 3600 + m * 60 + s


def _pfitz(**over):
    base = dict(
        name="Tanner", vdot=52, goal_marathon_s=HMS(3, 10, 0), w_now=40.0, p_history=55.0,
        longest_run_mi=18.0, days_per_week=6, race_date="2026-10-11", block_weeks=18,
        race_name="Chicago Marathon",
    )
    base.update(over)
    return build_plan(AthleteInputs(**base))


def _daniels(**over):
    base = dict(
        name="Kelly", vdot=43, goal_marathon_s=HMS(3, 55, 0), w_now=28.0, p_history=31.0,
        longest_run_mi=13.0, days_per_week=4, race_date="2026-10-11", block_weeks=18,
        race_name="Chicago Marathon",
    )
    base.update(over)
    return build_plan(AthleteInputs(**base))


def _berlin(**over):
    base = dict(
        name="Michelle", vdot=48, goal_marathon_s=HMS(3, 30, 0), w_now=38.0, p_history=45.0,
        longest_run_mi=16.0, days_per_week=6, race_date="2026-09-27", block_weeks=18,
        race_name="Berlin Marathon",
    )
    base.update(over)
    return build_plan(AthleteInputs(**base))


def _club():
    spine = _pfitz()
    athletes = [
        ClubAthlete("Tanner", spine),
        ClubAthlete("Kelly", _daniels()),
        ClubAthlete("Michelle", _berlin()),
    ]
    return spine, athletes


def test_layout_columns_and_header():
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    header = next(r for r in layout.rows if r.kind == "header").cells
    assert header[0] == "Wk" and header[1] == "Date"
    assert "Tanner" in header and "Kelly" in header and "Michelle" in header
    assert "Range" in header and "Strava Course" in header
    # Title + frozen header region.
    assert layout.rows[0].kind == "title" and layout.rows[0].cells[0] == "Saturday Long Runs"
    assert layout.freeze_rows == 4


def _data_rows(layout):
    return [r for r in layout.rows if r.kind in ("week", "race_day")]


def test_week_number_is_continuous_and_no_phase_or_workout_columns():
    # The Wk column is a single running count over the union grid; phases/workout are gone.
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    assert "workout" not in layout.column_kinds
    assert not any(r.kind == "phase" for r in layout.rows)
    wk_values = [r.cells[0] for r in _data_rows(layout)]
    assert wk_values == list(range(1, len(wk_values) + 1))


def test_no_recover_bonus_easy_tokens_anywhere():
    # Outside an athlete's block the cell is blank — never a recover/bonus/easy placeholder.
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    flat = [str(c) for r in layout.rows for c in r.cells]
    assert not any(tok in flat for tok in ("recover", "bonus", "easy"))


def test_range_is_min_max_over_numeric_only():
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    for row in _data_rows(layout):
        nums = [row.cells[c] for c in row.num_cols]
        rng = row.cells[row.range_col]
        if not nums:
            assert rng == ""
            continue
        lo, hi = min(nums), max(nums)
        expected = f"{lo:g}-{hi:g} mi" if lo != hi else f"{lo:g} mi"
        assert rng == expected


def test_each_marathon_gets_its_own_race_band():
    # Berlin (Sep 27) and Chicago (Oct 11) are distinct marathons in the batch; each earns a band.
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    bands = [r.cells[0] for r in layout.rows if r.kind == "race_band"]
    assert any("Berlin" in b for b in bands)
    assert any("Chicago" in b for b in bands)
    assert len([r for r in layout.rows if r.kind == "race_day"]) == 2


def test_marathon_cells_show_262_or_real_mileage_then_blank():
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    header = next(r for r in layout.rows if r.kind == "header").cells
    m_col, t_col = header.index("Michelle"), header.index("Tanner")
    race_days = [r for r in layout.rows if r.kind == "race_day"]
    berlin_row, chicago_row = race_days[0], race_days[-1]

    # Michelle runs Berlin: 26.2 on the earlier race-day row.
    assert berlin_row.cells[m_col] == 26.2
    # Tanner targets Chicago, so on Berlin's race day he is still building — a real long-run number.
    assert isinstance(berlin_row.cells[t_col], (int, float)) and berlin_row.cells[t_col] != 26.2
    # On Chicago's race day Tanner races; Michelle's block already ended → blank, not a token.
    assert chicago_row.cells[t_col] == 26.2
    assert chicago_row.cells[m_col] == ""


def test_saturday_cell_reads_session_mileage_and_category():
    # A 5K/10K tune-up race replaces the long run on Saturday; ``week.long_run`` excludes RACE, so
    # the grid must read the Saturday day directly — surfacing the distance and a "tune_up" tint.
    from engine.plan.models import PlannedDay, PlannedWeek, Workout, WorkoutKind
    from render.long_runs import _saturday_cell

    tune_up = PlannedWeek(
        index=7, phase="Threshold", label="10K tune-up", target_miles=30.0,
        days=[
            PlannedDay("Mon", Workout(WorkoutKind.EASY, "Easy run", distance_mi=9.0)),
            PlannedDay("Sat", Workout(WorkoutKind.RACE, "10K tune-up race", distance_mi=6.2)),
        ],
    )
    assert _saturday_cell(tune_up) == (6.2, "tune_up")

    # A goal-pace long run is no longer a distinct tint — it reads as a plain easy long-run cell.
    mp_long = PlannedWeek(
        index=8, phase="Threshold", label="mp", target_miles=40.0,
        days=[PlannedDay("Sat", Workout(WorkoutKind.MARATHON_PACE, "Long run 16 mi w/ 6 mi @ MP", distance_mi=16.0))],
    )
    assert _saturday_cell(mp_long) == (16.0, "easy")

    easy_down = PlannedWeek(
        index=9, phase="Base", label="down", target_miles=20.0, is_down_week=True,
        days=[PlannedDay("Sat", Workout(WorkoutKind.LONG, "Long run 10 mi", distance_mi=10.0))],
    )
    assert _saturday_cell(easy_down) == (10.0, "recovery")

    plain = PlannedWeek(
        index=10, phase="Base", label="easy", target_miles=30.0,
        days=[PlannedDay("Sat", Workout(WorkoutKind.LONG, "Long run 14 mi", distance_mi=14.0))],
    )
    assert _saturday_cell(plain) == (14.0, "easy")

    rest_sat = PlannedWeek(
        index=11, phase="Taper", label="rest sat", target_miles=10.0,
        days=[PlannedDay("Sat", Workout(WorkoutKind.REST, "Rest"))],
    )
    assert _saturday_cell(rest_sat) is None


def test_double_places_first_marathon_on_its_true_saturday():
    # A Berlin->NYC double must show 26.2 on BOTH races, dated correctly, with real bridge mileage
    # between them — the anchoring uses final_race_date, not the primary goal.
    from engine.plan.club import build_marathon_double
    from engine.plan.models import MarathonRace

    dbl = build_marathon_double(AthleteInputs(
        name="Tamara", vdot=48, goal_marathon_s=HMS(3, 30, 0), w_now=38.0, p_history=45.0,
        longest_run_mi=16.0, days_per_week=6, race_date="2026-09-27", block_weeks=20,
        race_name="Berlin Marathon",
        secondary_races=(MarathonRace("New York City Marathon", "2026-11-01"),),
    ))
    assert dbl is not None
    spine = _pfitz()
    layout = build_long_runs_layout(spine, [ClubAthlete("Tamara", dbl), ClubAthlete("Tanner", spine)])
    header = next(r for r in layout.rows if r.kind == "header").cells
    tam = header.index("Tamara")

    bands = [r.cells[0] for r in layout.rows if r.kind == "race_band"]
    assert any("Berlin" in b and "September 27" in b for b in bands)
    assert any("New York" in b and "November 1" in b for b in bands)

    tam_vals = [r.cells[tam] for r in layout.rows if r.kind == "race_day"]
    assert tam_vals.count(26.2) >= 2   # races both Berlin and NYC


def test_grid_extends_to_cover_a_later_and_longer_block():
    # Spine is 18-week Chicago (Oct 11). A 20-week NYC block ending Nov 1 must NOT blank out:
    # the grid extends to the later race, and the NYC athlete keeps real mileage past Chicago day.
    spine = _pfitz()
    nyc = build_plan(AthleteInputs(
        name="Dana", vdot=50, goal_marathon_s=HMS(3, 15, 0), w_now=42.0, p_history=50.0,
        longest_run_mi=18.0, days_per_week=6, race_date="2026-11-01", block_weeks=20,
        race_name="New York City Marathon",
    ))
    athletes = [ClubAthlete("Tanner", spine), ClubAthlete("Dana", nyc)]
    layout = build_long_runs_layout(spine, athletes)
    header = next(r for r in layout.rows if r.kind == "header").cells
    d_col = header.index("Dana")

    race_days = [r for r in layout.rows if r.kind == "race_day"]
    # Two distinct race days: Chicago (Oct 11) then NYC (Nov 1).
    assert len(race_days) == 2
    chicago_row, nyc_row = race_days[0], race_days[-1]
    # On Chicago's race day Dana is still building toward NYC → a real long-run number.
    assert isinstance(chicago_row.cells[d_col], (int, float))
    # Dana runs NYC on the final race-day row.
    assert nyc_row.cells[d_col] == 26.2
    assert any("New York" in r.cells[0] for r in layout.rows if r.kind == "race_band")


def test_legend_row_and_cell_categories_present():
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    legend = next((r for r in layout.rows if r.kind == "legend"), None)
    assert legend is not None and any("Tune-up race" in str(c) for c in legend.cells)
    # Goal-marathon cells carry a 'marathon' category on race-day rows; mid-block cells get tints too.
    race_days = [r for r in layout.rows if r.kind == "race_day"]
    assert any("marathon" in r.cell_cats.values() for r in race_days)
    cats_seen = {c for r in layout.rows if r.kind in ("week", "race_day") for c in r.cell_cats.values()}
    assert "easy" in cats_seen and "marathon" in cats_seen
    # Each legend swatch is a real background-tinted cell (not colored text in one merged cell).
    from render.long_runs import _CAT_BG, _legend_blocks
    blocks = _legend_blocks(layout.ncols)
    assert {cat for _, _, _, cat in blocks} >= {"marathon", "tune_up", "recovery", "easy"}
    assert "quality" not in {cat for _, _, _, cat in blocks}
    reqs = build_long_runs_format_requests(7, layout, PlanSheetTheme())
    tune_bg = _rgb_dict = {"red": _CAT_BG["tune_up"][0], "green": _CAT_BG["tune_up"][1], "blue": _CAT_BG["tune_up"][2]}
    assert any(r.get("repeatCell", {}).get("cell", {}).get("userEnteredFormat", {}).get("backgroundColor") == tune_bg for r in reqs)


def test_format_requests_build():
    spine, athletes = _club()
    layout = build_long_runs_layout(spine, athletes)
    reqs = build_long_runs_format_requests(123, layout, PlanSheetTheme())
    assert any("updateSheetProperties" in r and "frozenRowCount" in str(r) for r in reqs)
    assert any("mergeCells" in r for r in reqs)


def _sections(layout) -> dict[str, str]:
    """Map each section header to the body row that follows it (stacked single-column layout)."""
    out: dict[str, str] = {}
    pending: str | None = None
    for r in layout.rows:
        if r.kind == "section_header":
            pending = str(r.cells[0])
        elif r.kind == "section_body" and pending is not None:
            out[pending] = str(r.cells[0])
            pending = None
    return out


def test_read_me_content():
    from datetime import date

    spine = _pfitz()
    marathons = [("Berlin Marathon", date(2026, 9, 27), 20), ("Chicago Marathon", date(2026, 10, 11), 21)]
    layout = build_read_me_layout(spine, athletes=["Tanner", "Kelly"], marathons=marathons)
    assert layout.rows[0].cells[0] == "Zone 2 Track Club — 2026 Marathon Plan"
    # One live countdown formula per race, in chronological order, labeled to each marathon. The
    # week count is computed in-sheet from TODAY(), so we assert the formula's shape and labeling.
    countdowns = [r.cells[0] for r in layout.rows if r.kind == "countdown"]
    assert countdowns[0].startswith("=") and "DATE(2026,9,27)" in countdowns[0] and "Berlin Marathon · September 27, 2026" in countdowns[0]
    assert "DATE(2026,10,11)" in countdowns[1] and "Chicago Marathon · October 11, 2026" in countdowns[1]
    assert "TODAY()" in countdowns[0]
    sections = _sections(layout)
    assert "This plan is yours" in sections
    assert "The four training phases" in sections
    assert "Resources" in sections
    assert "Base" in sections["The four training phases"] and "Week" in sections["The four training phases"]


def test_read_me_has_legend_and_roster():
    spine = _pfitz()
    layout = build_read_me_layout(spine, athletes=["Tanner", "Kelly", "Michelle"])
    sections = _sections(layout)
    assert "How to read this sheet" in sections
    assert "Who this is for" in sections

    legend = sections["How to read this sheet"]
    # The legend explains columns, abbreviations, tinting, flagged weeks, and the 92% threshold in words.
    assert "92%" in legend
    assert "slate-blue" in legend
    assert "threshold" in legend and "marathon pace" in legend

    roster = sections["Who this is for"]
    assert "Tanner" in roster and "Kelly" in roster and "Michelle" in roster
