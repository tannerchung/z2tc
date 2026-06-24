"""Google Sheets ``batchUpdate`` requests that style a :class:`PlanSheetLayout`.

Mirrors the hand-styled club tab: navy headers, phase color bands, recovery shading,
a bold-navy long-run column, an italic-gray "Why", and a peach race-day row.
"""

from __future__ import annotations

from typing import Any

from render.plan_layout import PlanSheetLayout
from render.plan_sheet_theme import PlanSheetTheme


def _rgb(t: tuple[float, float, float]) -> dict[str, float]:
    return {"red": t[0], "green": t[1], "blue": t[2]}


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
) -> dict[str, Any]:
    text: dict[str, Any] = {
        "fontFamily": theme.font_family,
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
    return cell


def _fields(*, wrap: bool = False, valign: bool = False) -> str:
    parts = ["textFormat", "backgroundColor"]
    if wrap:
        parts.append("wrapStrategy")
    if valign:
        parts.append("verticalAlignment")
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
    kinds = layout.column_kinds
    why_col = kinds.index("why") if "why" in kinds else None
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
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, size=theme.title_font_size, fg=theme.navy, bg=(1, 1, 1)), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "subtitle":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1)), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "narrative":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, size=theme.body_font_size, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "paces_header":
            reqs.append(_row_req(sheet_id, ri, 1, 5, _fmt(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=theme.pace_section_rgb), _fields()))
            merges.append(_merge(sheet_id, ri, 1, 5))
        elif k == "pace":
            reqs.append(_row_req(sheet_id, ri, 1, 3, _fmt(theme, bold=True, fg=theme.navy, bg=theme.pace_label_rgb), _fields()))
            reqs.append(_row_req(sheet_id, ri, 3, 5, _fmt(theme, bold=True, size=theme.pace_value_font_size, fg=theme.dark_text, bg=(1, 1, 1)), _fields()))
            merges.append(_merge(sheet_id, ri, 1, 3))
            merges.append(_merge(sheet_id, ri, 3, 5))
        elif k == "table_header":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, size=theme.header_font_size, fg=(1, 1, 1), bg=theme.navy), _fields()))
        elif k == "phase":
            bg = theme.phase_rgb.get(row.phase or "", (0.9, 0.9, 0.9))
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=theme.navy, bg=bg), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k in ("week", "week_down"):
            down = k == "week_down"
            base_fg = theme.gray_text if down else theme.dark_text
            base_bg = theme.recovery_rgb if down else (1, 1, 1)
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, italic=down, fg=base_fg, bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            if row.long_col is not None:
                reqs.append(_row_req(sheet_id, ri, row.long_col, row.long_col + 1, _fmt(theme, bold=True, italic=down, fg=(theme.gray_text if down else theme.navy), bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            # Make the midweek quality (Q2) cell pop like the long run, so both Q days read as quality.
            for qc in row.quality_cols:
                if qc == row.long_col:
                    continue
                reqs.append(_row_req(sheet_id, ri, qc, qc + 1, _fmt(theme, bold=True, italic=down, fg=(theme.gray_text if down else theme.navy), bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
            if why_col is not None:
                reqs.append(_row_req(sheet_id, ri, why_col, why_col + 1, _fmt(theme, italic=True, size=theme.header_font_size, fg=theme.gray_text, bg=base_bg, wrap=True, valign="TOP"), _fields(wrap=True, valign=True)))
        elif k == "race_band":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=(1, 1, 1), bg=theme.race_day_band_rgb), _fields()))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "race_day":
            reqs.append(_row_req(sheet_id, ri, 0, n, _fmt(theme, bold=True, fg=theme.race_day_fg, bg=theme.race_day_row_rgb), _fields()))

    # Merges last so row formats land first.
    reqs.extend(merges)
    return reqs
