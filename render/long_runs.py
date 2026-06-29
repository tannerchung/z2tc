"""Club-wide "Saturday Long Runs" tab: one schedule, a column per athlete.

The whole club runs together on Saturdays; this tab is the **union of each athlete's own
plan projected onto a single Saturday calendar**, spanning the earliest block start through
the latest race in the batch. ``Wk`` is a continuous running count over that grid (week 1 =
the first Saturday any plan starts), *not* a per-plan week number.

Each athlete cell is that athlete's **actual** Saturday-session mileage for the week, ``26.2``
on a day they race a goal marathon (a marathon double shows it on both races, each anchored to
its own true date via ``final_race_date``), and **blank** outside their block — no recover/
bonus/easy placeholder tokens. Cells are tinted only for the distinct cases (goal marathon,
tune-up race, recovery week) with a highlighted legend row, so a 5K/10K tune-up or a cutback
week reads at a glance instead of looking like a random low number; ordinary long runs stay plain.
Phase bands and a shared "Workout" column are intentionally omitted: with runners on different
calendars and methods, neither translates meaningfully across a row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.plan.models import TrainingPlan, WorkoutKind


def canonical_phase(name: str | None) -> str:
    """Map a method-specific phase name to the club's canonical four-phase vocabulary, so the
    banners read the same regardless of which coach's plan is the spine (Pfitz calls Base
    "Endurance" and Threshold "LT + Endurance")."""
    s = (name or "").lower()
    if "taper" in s:
        return "Taper"
    if "race" in s and "prep" in s:
        return "Race Prep"
    if "lt" in s or "threshold" in s:
        return "Threshold"
    if "base" in s or "endurance" in s:
        return "Base"
    return (name or "").title()


@dataclass(frozen=True)
class ClubAthlete:
    name: str
    plan: TrainingPlan


@dataclass
class LRRow:
    kind: str                      # title|subtitle|legend|blank|header|week|race_band|race_day
    cells: list[str | int | float]
    phase: str | None = None
    num_cols: tuple[int, ...] = ()   # athlete columns holding a numeric mileage (bold)
    range_col: int | None = None
    cell_cats: dict[int, str] = field(default_factory=dict)  # athlete col -> session category (tint)


@dataclass
class LongRunsLayout:
    rows: list[LRRow]
    ncols: int
    column_widths: list[int]
    column_kinds: list[str]          # wk|date|workout|athlete|range|course
    freeze_rows: int = 4

    @property
    def values(self) -> list[list[str | int | float]]:
        return [r.cells for r in self.rows]


def _is_marathon_day(day) -> bool:
    """The goal marathon, not a tune-up race. Pfitzinger/Daniels blocks schedule shorter
    ``WorkoutKind.RACE`` tune-ups mid-block; those stay normal week rows."""
    return day.workout.kind == WorkoutKind.RACE and (day.workout.distance_mi or 0) >= 26.0


def _is_marathon_week(week) -> bool:
    return any(_is_marathon_day(d) for d in week.days)


def _race_date(plan: TrainingPlan) -> date | None:
    try:
        return date.fromisoformat(str(plan.goal.get("date"))[:10])
    except (ValueError, TypeError):
        return None


def _marathon_saturday(race: date) -> date:
    """The Saturday that anchors a race week (the race day itself if it falls on a Saturday,
    else the Saturday just before — Sunday marathons train on the Saturday two weeks of taper
    earlier). Every athlete's Saturdays land on the same weekly grid as a result."""
    return race - timedelta(days=(race.weekday() - 5) % 7)


def _final_race_date(plan: TrainingPlan) -> date | None:
    """The plan's *last* race day. For a marathon double this is the later (``final_race_date``)
    race, not the primary goal — the plan's weeks run through it, so the calendar must anchor there."""
    for key in ("final_race_date", "date"):
        try:
            return date.fromisoformat(str(plan.goal.get(key))[:10])
        except (ValueError, TypeError):
            continue
    return None


def _week_saturdays(plan: TrainingPlan) -> list[date]:
    """The Saturday anchoring each plan week, counting back from the plan's *final* race (mirrors
    ``render.plan_layout._saturday_dates``, which anchors on ``final_race_date``, as ``date`` objects).
    Anchoring on the final race is what places a double's first marathon on its true Saturday."""
    race = _final_race_date(plan)
    if race is None:
        return []
    last_sat = _marathon_saturday(race)
    n = len(plan.weeks)
    return [last_sat - timedelta(weeks=(n - 1 - i)) for i in range(n)]


def _fmt_miles(miles: float) -> int | float:
    return int(miles) if abs(miles - round(miles)) < 0.05 else round(miles, 1)


def _session_category(workout, is_down: bool) -> str:
    """Classify a Saturday session so the cell can be tinted. Only the genuinely distinct cases get
    a tint — a goal marathon, a shorter tune-up race, or a recovery-week cutback; ordinary long runs
    (including the common goal-pace ones) stay plain so the grid doesn't drown in highlight."""
    if workout is not None and workout.kind == WorkoutKind.RACE:
        return "marathon" if (workout.distance_mi or 0) >= 26.0 else "tune_up"
    return "recovery" if is_down else "easy"


def _saturday_cell(week) -> tuple[float, str] | None:
    """``(miles, category)`` for the athlete's Saturday session, or ``None`` if there isn't one.

    Reads the Saturday day directly (not ``week.long_run``, which excludes ``RACE``) so a 5K/10K
    tune-up race that *replaces* the long run still shows its real distance and a race tint."""
    sat = next((d for d in week.days if str(d.day) == "Sat"), None)
    workout = sat.workout if sat is not None else None
    miles = sat.miles if (sat is not None and sat.miles and sat.miles > 0) else None
    if miles is None:
        lr = week.long_run
        if lr is not None and lr.miles > 0:
            miles, workout = lr.miles, lr.workout
    if miles is None:
        return None
    return miles, _session_category(workout, week.is_down_week)


# Long-run cell tints + the colored legend row (mirrors the plan tab's pace-zone language).
_CAT_BG = {
    "marathon": (0.988, 0.894, 0.839),   # peach (goal race day)
    "tune_up": (0.992, 0.925, 0.78),     # soft gold (tune-up race)
    "recovery": (0.945, 0.945, 0.945),   # light gray (recovery-week long run)
    "easy": (1.0, 1.0, 1.0),
}
_CAT_FG = {
    "marathon": (0.545, 0.18, 0.0),      # dark orange
    "tune_up": (0.6, 0.33, 0.0),         # amber
    "recovery": (0.502, 0.502, 0.502),   # gray
    "easy": (0.149, 0.149, 0.149),       # dark text
}
_LEGEND_ITEMS: tuple[tuple[str, str], ...] = (
    ("Goal marathon", "marathon"),
    ("Tune-up race", "tune_up"),
    ("Recovery week", "recovery"),
    ("Easy long run", "easy"),
)
_LEGEND_PREFIX = "Session key"


def _legend_blocks(ncols: int) -> list[tuple[int, int, str, str]]:
    """Lay the legend out as ``(start_col, end_col, label, category)`` blocks across the row, so each
    swatch can be a real **background-highlighted** cell (Sheets can't tint part of a merged cell)."""
    items = [(_LEGEND_PREFIX, "prefix"), *_LEGEND_ITEMS]
    if ncols < len(items):                       # too few columns: drop the prefix, then fall back
        items = list(_LEGEND_ITEMS)
    if ncols < len(items):
        return [(0, ncols, "Key: goal marathon · tune-up · goal-pace · recovery · easy", "prefix")]
    base, rem = divmod(ncols, len(items))
    blocks: list[tuple[int, int, str, str]] = []
    c = 0
    for i, (label, cat) in enumerate(items):
        span = base + (1 if i < rem else 0)
        blocks.append((c, c + span, label, cat))
        c += span
    return blocks


def _athlete_marathons(plan: TrainingPlan) -> list[tuple[str, date]]:
    """Every goal marathon the athlete races this cycle — primary plus any secondaries — as
    ``(name, real race date)``. Driven by the goal dates, not by scanning for a race-day workout:
    a Pfitzinger taper can end without an explicit race day, but the runner still races that Sunday."""
    out: list[tuple[str, date]] = []
    primary = _race_date(plan)
    if primary is not None:
        out.append((str(plan.goal.get("name") or "Marathon"), primary))
    for r in plan.goal.get("secondary_marathons") or []:
        try:
            d = date.fromisoformat(str(r.get("date"))[:10])
        except (ValueError, TypeError, AttributeError):
            continue
        out.append((str(r.get("name") or "Marathon"), d))
    return out


def season_marathons(plans: list[TrainingPlan]) -> list[tuple[str, date, int]]:
    """Distinct goal marathons across the batch, earliest first — the club's race season.

    Returns ``(name, date, weeks)`` per race, deduped by name (a marathon has one date); ``weeks``
    is the longest block among plans targeting that race (matching how the spine takes the
    max-week plan), so the Read Me can show a per-race countdown labeled to each marathon."""
    seen: dict[str, list] = {}
    for p in plans:
        rd = _race_date(p)
        if rd is None:
            continue
        name = str(p.goal.get("name") or "Marathon").strip()
        weeks = p.block_weeks or len(p.weeks)
        if name not in seen:
            seen[name] = [rd, weeks]
        else:
            seen[name][1] = max(seen[name][1], weeks)
    return sorted(((n, d, w) for n, (d, w) in seen.items()), key=lambda t: t[1])


def _short_name(name: str) -> str:
    short = re.sub(r"\bmarathon\b", "", name, flags=re.I).strip(" -—·")
    return short or name


def _season_subtitle(marathons: list[tuple[str, date, int]]) -> str | None:
    """One line naming each marathon in the group with its date (Berlin Sep 27 · Chicago Oct 11)."""
    if not marathons:
        return None
    races = " · ".join(f"{_short_name(n)} {d:%b} {d.day}" for n, d, _ in marathons)
    year = marathons[0][1].year
    lead = f"{year} marathon season — {races}." if len(marathons) > 1 else f"{races}."
    return f"{lead} One Saturday calendar, different distances, same finish window."


def build_long_runs_layout(
    spine: TrainingPlan,
    athletes: list[ClubAthlete],
    *,
    course_links: dict[int, str] | None = None,
    subtitle: str | None = None,
) -> LongRunsLayout:
    """Build the Saturday Long Runs grid from each athlete's plan, projected onto one shared calendar.

    The grid is the **union** of every athlete's Saturdays — earliest block start through the latest
    race in the batch — with a continuous week count (week 1 = the first Saturday any plan starts).
    Each cell is that athlete's **actual** long-run mileage for the week, ``26.2`` on their own goal
    marathon (a double shows it on both races), and **blank** outside their block — no recover/bonus/
    easy tokens. Phase bands and the shared-workout column are dropped: with runners on different
    calendars and different methods they don't translate across the row.
    """
    course_links = course_links or {}
    club_sats = _week_saturdays(spine)
    sats_by_athlete = {a.name: _week_saturdays(a.plan) for a in athletes}
    all_sats = [s for ss in sats_by_athlete.values() for s in ss] + list(club_sats)

    kinds: list[str] = ["wk", "date"] + ["athlete"] * len(athletes) + ["range", "course"]
    ncols = len(kinds)
    widths = [{"wk": 40, "date": 56, "athlete": 58, "range": 84, "course": 209}[k] for k in kinds]
    range_col = 2 + len(athletes)

    def pad(cells: list) -> list:
        return list(cells) + [""] * (ncols - len(cells))

    rows: list[LRRow] = [LRRow("title", pad(["Saturday Long Runs"]))]
    season_sub = _season_subtitle(season_marathons([spine, *[a.plan for a in athletes]]))
    rows.append(LRRow("subtitle", pad([subtitle or season_sub or "The one session we all do together, different distances and the same finish window."])))
    legend_cells: list[str | int | float] = [""] * ncols
    for c0, _, label, _ in _legend_blocks(ncols):
        legend_cells[c0] = label
    rows.append(LRRow("legend", legend_cells))
    rows.append(LRRow("header", pad(["Wk", "Date", *[a.name for a in athletes], "Range", "Strava Course"])))

    if not all_sats:
        return LongRunsLayout(rows=rows, ncols=ncols, column_widths=widths, column_kinds=kinds)

    g0, g1 = min(all_sats), max(all_sats)
    grid = [g0 + timedelta(weeks=i) for i in range((g1 - g0).days // 7 + 1)]
    spine_idx_by_date = {s: i for i, s in enumerate(club_sats)}  # course-link lookup only
    sbd = {a.name: {d: i for i, d in enumerate(sats_by_athlete[a.name])} for a in athletes}
    # The Saturday that anchors each marathon the athlete races -> (name, real race date).
    race_sats = {
        a.name: {_marathon_saturday(d): (name, d) for name, d in _athlete_marathons(a.plan)}
        for a in athletes
    }

    for gi, cd in enumerate(grid):
        cells: list[str | int | float] = [gi + 1, f"{cd:%b} {cd.day}"]
        num_cols: list[int] = []
        nums: list[float] = []
        cats: dict[int, str] = {}
        race_names: list[str] = []
        race_date_actual: date | None = None
        for a in athletes:
            col = len(cells)
            val: str | int | float = ""
            race = race_sats[a.name].get(cd)
            idx = sbd[a.name].get(cd)
            if race is not None:                 # racing today (real mileage = 26.2)
                name, actual = race
                val = 26.2
                cats[col] = "marathon"
                if not any(name.lower() == x.lower() for x in race_names):
                    race_names.append(name)   # dedup case-insensitively (intake casing varies)
                race_date_actual = actual
            elif idx is not None:                # mid-block: this week's Saturday session
                sc = _saturday_cell(a.plan.weeks[idx])
                if sc is not None:
                    miles, cat = sc
                    val = _fmt_miles(miles)
                    cats[col] = cat
            cells.append(val)
            if isinstance(val, (int, float)):
                num_cols.append(col)
                nums.append(float(val))
        if nums:
            lo, hi = min(nums), max(nums)
            cells.append(f"{lo:g}-{hi:g} mi" if lo != hi else f"{lo:g} mi")
        else:
            cells.append("")
        spine_idx = spine_idx_by_date.get(cd)
        cells.append(course_links.get(spine.weeks[spine_idx].index, "") if spine_idx is not None else "")

        if race_names:
            d = race_date_actual or cd
            rows.append(LRRow("race_band", pad([f"   RACE DAY      {' · '.join(race_names)}  ·  {d:%B} {d.day} · Execute the plan"])))
            rows.append(LRRow("race_day", pad(cells), num_cols=tuple(num_cols), range_col=range_col, cell_cats=cats))
        else:
            rows.append(LRRow("week", pad(cells), num_cols=tuple(num_cols), range_col=range_col, cell_cats=cats))

    return LongRunsLayout(rows=rows, ncols=ncols, column_widths=widths, column_kinds=kinds)


# ---------------------------------------------------------------------------------
# Format requests (Google Sheets batchUpdate) — mirrors the hand-styled club tab.
# ---------------------------------------------------------------------------------
def _rgb(t: tuple[float, float, float]) -> dict[str, float]:
    return {"red": t[0], "green": t[1], "blue": t[2]}


def _cell(
    theme,
    *,
    bold: bool = False,
    italic: bool = False,
    size: int | None = None,
    fg=None,
    bg=None,
    align: str | None = None,
    wrap: bool = False,
):
    text = {"fontFamily": theme.font_family, "fontSize": size or theme.body_font_size, "bold": bold, "italic": italic}
    if fg:
        text["foregroundColor"] = _rgb(fg)
    cell: dict = {"textFormat": text, "verticalAlignment": "MIDDLE"}
    if bg:
        cell["backgroundColor"] = _rgb(bg)
    if align:
        cell["horizontalAlignment"] = align
    if wrap:
        cell["wrapStrategy"] = "WRAP"
    return cell


_FIELDS = "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy)"


def _rng(sheet_id: int, row: int, c0: int, c1: int, cell: dict) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": c0, "endColumnIndex": c1},
            "cell": {"userEnteredFormat": cell},
            "fields": _FIELDS,
        }
    }


def _merge(sheet_id: int, row: int, c0: int, c1: int) -> dict:
    return {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": c0, "endColumnIndex": c1}}}




def build_long_runs_format_requests(sheet_id: int, layout: LongRunsLayout, theme) -> list[dict]:
    n = layout.ncols
    kinds = layout.column_kinds
    aligns = {"wk": "CENTER", "date": "CENTER", "workout": "LEFT", "athlete": "CENTER", "range": "CENTER", "course": "LEFT"}

    reqs: list[dict] = [
        {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": len(layout.rows) + 2, "startColumnIndex": 0, "endColumnIndex": n}}}
    ]
    for i, w in enumerate(layout.column_widths):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    merges: list[dict] = []
    for ri, row in enumerate(layout.rows):
        k = row.kind
        if k == "title":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, size=theme.title_font_size, fg=theme.navy, bg=(1, 1, 1), align="LEFT")))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "subtitle":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1), align="LEFT")))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "legend":
            for c0, c1, _label, cat in _legend_blocks(n):
                if cat == "prefix":
                    reqs.append(_rng(sheet_id, ri, c0, c1, _cell(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=(1, 1, 1), align="LEFT", wrap=True)))
                else:
                    reqs.append(_rng(sheet_id, ri, c0, c1, _cell(theme, bold=True, size=theme.header_font_size, fg=_CAT_FG[cat], bg=_CAT_BG[cat], align="CENTER", wrap=True)))
                if c1 - c0 > 1:
                    merges.append(_merge(sheet_id, ri, c0, c1))
        elif k == "header":
            for ci, kind in enumerate(kinds):
                reqs.append(_rng(sheet_id, ri, ci, ci + 1, _cell(theme, bold=True, size=theme.header_font_size, fg=(1, 1, 1), bg=theme.navy, align=aligns.get(kind, "CENTER"), wrap=True)))
        elif k == "week":
            for ci, kind in enumerate(kinds):
                is_range = ci == row.range_col
                if kind == "athlete":
                    cat = row.cell_cats.get(ci)
                    reqs.append(_rng(sheet_id, ri, ci, ci + 1, _cell(
                        theme, bold=ci in row.num_cols,
                        fg=_CAT_FG.get(cat, theme.dark_text), bg=_CAT_BG.get(cat, (1, 1, 1)), align="CENTER",
                    )))
                else:
                    reqs.append(_rng(sheet_id, ri, ci, ci + 1, _cell(
                        theme, bold=is_range,
                        fg=(theme.navy if is_range else theme.dark_text), bg=(1, 1, 1), align=aligns.get(kind, "CENTER"),
                    )))
        elif k == "race_band":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, fg=(1, 1, 1), bg=theme.race_day_band_rgb, align="LEFT")))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "race_day":
            for ci, kind in enumerate(kinds):
                if kind == "athlete":
                    cat = row.cell_cats.get(ci)
                    reqs.append(_rng(sheet_id, ri, ci, ci + 1, _cell(
                        theme, bold=True,
                        fg=_CAT_FG.get(cat, theme.race_day_fg), bg=_CAT_BG.get(cat, theme.race_day_row_rgb), align="CENTER",
                    )))
                else:
                    reqs.append(_rng(sheet_id, ri, ci, ci + 1, _cell(theme, bold=True, fg=theme.race_day_fg, bg=theme.race_day_row_rgb, align=aligns.get(kind, "CENTER"))))

    reqs.append({"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": layout.freeze_rows}}, "fields": "gridProperties.frozenRowCount"}})
    reqs.extend(merges)
    return reqs
