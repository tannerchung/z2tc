"""Google Sheets ``batchUpdate`` requests that style a :class:`PlanSheetLayout`.

Mirrors the hand-styled club tab: navy headers, phase color bands, recovery shading,
a bold-navy long-run column, an italic-gray "Why", and a peach race-day row.
"""

from __future__ import annotations

from typing import Any

from render.plan_layout import PlanSheetLayout
from render.plan_sheet_theme import PlanSheetTheme

# Per-pace-zone text colors for rich-text (textFormatRuns) coloring inside a workout cell.
# The title line keeps the cell's base format (navy bold); each detail line is recolored by the
# effort it names, so a glance separates easy volume from the day's hard work.
PACE_EASY = (0.502, 0.502, 0.502)       # gray — easy / warm-up / cool-down / steady / strides
PACE_MP = (0.6, 0.0, 0.0)               # maroon — marathon pace
PACE_THRESHOLD = (0.82, 0.4, 0.0)       # orange — threshold / tempo
PACE_FAST = (0.45, 0.2, 0.6)            # purple — VO2max intervals / reps
ROW_SEPARATOR = (0.85, 0.85, 0.85)      # hairline between week rows

# Words shown in the legend row, each colored to match its in-cell pace zone.
_LEGEND_ZONES = (
    ("Easy", PACE_EASY),
    ("Marathon", PACE_MP),
    ("Threshold", PACE_THRESHOLD),
    ("Intervals", PACE_FAST),
    ("Reps", PACE_FAST),
)


def _rgb(t: tuple[float, float, float]) -> dict[str, float]:
    return {"red": t[0], "green": t[1], "blue": t[2]}


def _zone_color(line: str) -> tuple[float, float, float] | None:
    """The pace-zone color for a detail line, or None to leave it on the cell's base format.

    Checked hardest-effort first so a mixed line (over/unders name both Threshold and MP) takes
    the dominant zone; Steady is matched before MP so "Steady (between easy & MP)" reads as easy."""
    if "VO2max" in line or "Interval" in line:
        return PACE_FAST
    if "Rep" in line:
        return PACE_FAST
    if "Threshold" in line:
        return PACE_THRESHOLD
    if "Steady" in line:
        return PACE_EASY
    if "MP" in line or "Marathon" in line:
        return PACE_MP
    if any(t in line for t in ("Easy", "Warm-up", "Cool-down", "strides", "surges", "jog")):
        return PACE_EASY
    return None


def _legend_runs(text: object) -> list[dict[str, Any]] | None:
    """Color each zone word in the legend string (``Easy``, ``Marathon``, …) to match the grid."""
    if not isinstance(text, str):
        return None
    events: list[tuple[int, tuple[float, float, float] | None]] = []
    for word, color in _LEGEND_ZONES:
        i = text.find(word)
        if i >= 0:
            events.append((i, color))
            # A run index must be < len; skip the trailing reset when the word ends the string.
            if i + len(word) < len(text):
                events.append((i + len(word), None))
    if not events:
        return None
    events.sort()
    runs: list[dict[str, Any]] = []
    if events[0][0] != 0:
        runs.append({"format": {}})
    for idx, color in events:
        fmt = {} if color is None else {"foregroundColor": _rgb(color), "foregroundColorStyle": {"rgbColor": _rgb(color)}}
        runs.append({"format": fmt} if idx == 0 else {"startIndex": idx, "format": fmt})
    return runs


def _pace_text_runs(text: object) -> list[dict[str, Any]] | None:
    """Build Sheets ``textFormatRuns`` that recolor each detail line of a stacked workout cell by
    its pace zone. The first run (index 0) is empty so the title inherits the cell's base format;
    a new run is emitted only when the active color changes, keeping the run list minimal."""
    if not isinstance(text, str) or "\n" not in text:
        return None
    runs: list[dict[str, Any]] = [{"format": {}}]
    active: tuple[float, float, float] | None = None
    idx = 0
    for i, line in enumerate(text.split("\n")):
        start = idx
        idx += len(line) + 1  # + newline
        if i == 0 or not line.strip():
            continue  # title keeps base; blanks keep the current run
        color = _zone_color(line)
        if color == active:
            continue
        runs.append(
            {"startIndex": start, "format": {}}
            if color is None
            else {"startIndex": start, "format": {"foregroundColor": _rgb(color), "foregroundColorStyle": {"rgbColor": _rgb(color)}}}
        )
        active = color
    return runs if len(runs) > 1 else None


def _fmt(
    theme: PlanSheetTheme,
    *,
    bold: bool = False,
    italic: bool = False,
    size: int | None = None,
    fg: tuple[float, float, float] | None = None,
    bg: tuple[float, float, float] | None = None,
    wrap: bool = False,
    valign: str | None = None,
    halign: str | None = None,
    border_bottom: tuple[float, float, float] | None = None,
    font_family: str | None = None,
) -> dict[str, Any]:
    text: dict[str, Any] = {
        "fontFamily": font_family or theme.font_family,
        "fontSize": size or theme.body_font_size,
        "bold": bold,
        "italic": italic,
    }
    if fg:
        text["foregroundColor"] = _rgb(fg)
    cell: dict[str, Any] = {"textFormat": text}
    if bg:
        cell["backgroundColor"] = _rgb(bg)
    if wrap:
        cell["wrapStrategy"] = "WRAP"
    if valign:
        cell["verticalAlignment"] = valign
    if halign:
        cell["horizontalAlignment"] = halign
    if border_bottom:
        cell["borders"] = {"bottom": {"style": "SOLID", "color": _rgb(border_bottom)}}
    return cell


def _fields(*, wrap: bool = False, valign: bool = False, halign: bool = False, borders: bool = False) -> str:
    parts = ["textFormat", "backgroundColor"]
    if wrap:
        parts.append("wrapStrategy")
    if valign:
        parts.append("verticalAlignment")
    if halign:
        parts.append("horizontalAlignment")
    if borders:
        parts.append("borders")
    return "userEnteredFormat(" + ",".join(parts) + ")"


def _row_req(sheet_id: int, row: int, c0: int, c1: int, cell: dict, fields: str) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row,
                "endRowIndex": row + 1,
                "startColumnIndex": c0,
                "endColumnIndex": c1,
            },
            "cell": {"userEnteredFormat": cell},
            "fields": fields,
        }
    }


def _runs_req(sheet_id: int, row: int, col: int, runs: list[dict[str, Any]]) -> dict:
    """Set only a cell's ``textFormatRuns`` (rich-text coloring), leaving its value and base
    format intact — the string is already written by the earlier values().update."""
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row,
                "endRowIndex": row + 1,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "rows": [{"values": [{"textFormatRuns": runs}]}],
            "fields": "textFormatRuns",
        }
    }


def _merge(sheet_id: int, row: int, c0: int, c1: int) -> dict:
    return {
        "mergeCells": {
            "mergeType": "MERGE_ALL",
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row,
                "endRowIndex": row + 1,
                "startColumnIndex": c0,
                "endColumnIndex": c1,
            },
        }
    }


def build_format_requests(
    sheet_id: int, layout: PlanSheetLayout, theme: PlanSheetTheme
) -> list[dict[str, Any]]:
    n = layout.ncols
    # Long-form copy above the calendar (summary, personalization, cautions) reads better in a
    # narrower column than the full grid width, so cap it at column I (index 8) instead of stretching
    # edge to edge.
    text_end = min(n, 9)
    kinds = layout.column_kinds
    why_col = kinds.index("why") if "why" in kinds else None
    day_cols = [i for i, c in enumerate(kinds) if c == "day"]
    center_cols = [i for i, c in enumerate(kinds) if c in ("wk", "date", "total")]
    total_col = kinds.index("total") if "total" in kinds else None
    wk_col = kinds.index("wk") if "wk" in kinds else None
    # Republishing reuses the tab; clear stale merges so new rows are not hidden under them.
    reqs: list[dict[str, Any]] = [
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": len(layout.rows) + 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": n,
                }
            }
        }
    ]
    merges: list[dict[str, Any]] = []

    # Column widths
    for i, w in enumerate(layout.column_widths):
        reqs.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": w},
                    "fields": "pixelSize",
                }
            }
        )

    for ri, row in enumerate(layout.rows):
        k = row.kind
        if k == "title":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, size=theme.title_font_size, fg=theme.navy, bg=(1, 1, 1), font_family=theme.title_font_family), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "subtitle":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1)), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "narrative":
            reqs.append(_row_req(sheet_id, ri, 0, text_end, _fmt(theme, size=theme.body_font_size, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 0, text_end))
        elif k == "history_header":
            reqs.append(_row_req(sheet_id, ri, 0, text_end, _fmt(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=theme.pace_section_rgb), _fields()))
            merges.append(_merge(sheet_id, ri, 0, text_end))
        elif k == "history":
            reqs.append(_row_req(sheet_id, ri, 0, text_end, _fmt(theme, size=theme.body_font_size, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 0, text_end))
        elif k == "cautions_header":
            reqs.append(_row_req(sheet_id, ri, 0, text_end, _fmt(theme, bold=True, size=theme.header_font_size, fg=theme.caution_fg, bg=theme.caution_header_bg), _fields()))
            merges.append(_merge(sheet_id, ri, 0, text_end))
        elif k == "caution":
            reqs.append(_row_req(sheet_id, ri, 0, text_end, _fmt(theme, size=theme.body_font_size, fg=theme.caution_fg, bg=theme.caution_body_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 0, text_end))
        elif k == "paces_header":
            reqs.append(_row_req(sheet_id, ri, 1, 5, _fmt(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=theme.pace_section_rgb), _fields()))
            merges.append(_merge(sheet_id, ri, 1, 5))
        elif k == "pace_note":
            reqs.append(_row_req(sheet_id, ri, 1, text_end, _fmt(theme, italic=True, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1), wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 1, text_end))
        elif k == "pace":
            reqs.append(_row_req(sheet_id, ri, 1, 3, _fmt(theme, bold=True, fg=theme.navy, bg=theme.pace_label_rgb), _fields()))
            reqs.append(_row_req(sheet_id, ri, 3, 5, _fmt(theme, bold=True, size=theme.pace_value_font_size, fg=theme.dark_text, bg=(1, 1, 1)), _fields()))
            merges.append(_merge(sheet_id, ri, 1, 3))
            merges.append(_merge(sheet_id, ri, 3, 5))
        elif k == "legend":
            reqs.append(_row_req(sheet_id, ri, 1, text_end, _fmt(theme, italic=True, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1), wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 1, text_end))
            legend_runs = _legend_runs(row.cells[1] if len(row.cells) > 1 else None)
            if legend_runs:
                reqs.append(_runs_req(sheet_id, ri, 1, legend_runs))
        elif k == "table_header":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, size=theme.header_font_size, fg=(1, 1, 1), bg=theme.navy), _fields()))
            for cc in center_cols:
                reqs.append(_row_req(sheet_id, ri, cc, cc + 1, _fmt(theme, bold=True, size=theme.header_font_size, fg=(1, 1, 1), bg=theme.navy, halign="CENTER"), _fields(halign=True)))
        elif k == "phase":
            bg = theme.phase_rgb.get(row.phase or "", (0.9, 0.9, 0.9))
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=theme.navy, bg=bg), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k in ("week", "week_down"):
            down = k == "week_down"
            base_fg = theme.gray_text if down else theme.dark_text
            base_bg = theme.recovery_rgb if down else (1, 1, 1)
            emphasis_fg = theme.gray_text if down else theme.navy
            # Base row carries a hairline bottom border so weeks separate cleanly in a dense grid.
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, italic=down, fg=base_fg, bg=base_bg, wrap=True, valign="TOP", border_bottom=ROW_SEPARATOR), _fields(wrap=True, valign=True, borders=True)))
            # Long run + midweek quality + any medium-long read as the week's key sessions (bold navy).
            for ec in {row.long_col, *row.quality_cols, *row.medlong_cols}:
                if ec is None:
                    continue
                reqs.append(_row_req(sheet_id, ri, ec, ec + 1, _fmt(theme, bold=True, italic=down, fg=emphasis_fg, bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            for cc in center_cols:
                reqs.append(_row_req(sheet_id, ri, cc, cc + 1, _fmt(theme, italic=down, fg=base_fg, bg=base_bg, valign="TOP", halign="CENTER"), _fields(valign=True, halign=True)))
            if row.over_capacity and total_col is not None:
                # Amber Total: this week's volume is beyond anything the athlete has demonstrated.
                reqs.append(_row_req(sheet_id, ri, total_col, total_col + 1, _fmt(theme, bold=True, fg=theme.caution_fg, bg=theme.over_capacity_bg, valign="TOP", halign="CENTER"), _fields(valign=True, halign=True)))
            if row.short_week and wk_col is not None:
                # Slate-blue Wk marker: the athlete logged this week short of the on-plan threshold.
                # Distinct from the amber over-capacity Total so "came in short" never reads as "too much".
                reqs.append(_row_req(sheet_id, ri, wk_col, wk_col + 1, _fmt(theme, bold=True, italic=down, fg=theme.short_week_fg, bg=theme.short_week_bg, valign="TOP", halign="CENTER"), _fields(valign=True, halign=True)))
            if row.tune_up_status and row.tune_up_col is not None:
                # Once a tune-up result lands, tint its race cell green (on track) / amber (B-goal
                # watch) / red (behind) — a glance-level read that pairs with the verdict in "Why".
                tu_bg, tu_fg = {
                    "on_track": (theme.on_track_bg, theme.on_track_fg),
                    "watch": (theme.over_capacity_bg, theme.caution_fg),
                    "behind": (theme.behind_bg, theme.behind_fg),
                }.get(row.tune_up_status, (theme.on_track_bg, theme.on_track_fg))
                reqs.append(_row_req(sheet_id, ri, row.tune_up_col, row.tune_up_col + 1, _fmt(theme, bold=True, fg=tu_fg, bg=tu_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            if why_col is not None:
                reqs.append(_row_req(sheet_id, ri, why_col, why_col + 1, _fmt(theme, italic=True, size=theme.header_font_size, fg=theme.gray_text, bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            for dc in day_cols:
                txt = row.cells[dc] if dc < len(row.cells) else None
                if txt == "Rest Day":
                    # De-emphasize rest so the eye lands on the days that carry work.
                    reqs.append(_row_req(sheet_id, ri, dc, dc + 1, _fmt(theme, italic=True, size=theme.subtitle_font_size, fg=theme.gray_text, bg=base_bg, valign="TOP"), _fields(valign=True)))
                    continue
                # Rich-text: recolor each detail line of a stacked workout cell by its pace zone.
                runs = _pace_text_runs(txt)
                if runs:
                    reqs.append(_runs_req(sheet_id, ri, dc, runs))
        elif k == "race_band":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=(1, 1, 1), bg=theme.race_day_band_rgb), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "race_day":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=theme.race_day_fg, bg=theme.race_day_row_rgb), _fields()))

    # Merges last so row formats land first.
    reqs.extend(merges)
    return reqs
