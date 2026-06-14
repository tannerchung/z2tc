"""Harvest Google Sheets grid formatting and derive a compact ``StyleSpec``."""

from __future__ import annotations

import os
from typing import Any

from llm.boundary import StyleSpec, extract_style


def default_club_spreadsheet_id() -> str:
    return os.environ.get(
        "Z2TC_CLUB_SPREADSHEET_ID",
        "1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w",
    )


def _col_letter(n: int) -> str:
    if n <= 0:
        return "A"
    s = ""
    x = n
    while x > 0:
        x, r = divmod(x - 1, 26)
        s = chr(65 + r) + s
    return s


def _escape_a1_sheet_title(title: str) -> str:
    if any(c in title for c in ("'", " ", "!", '"', "#", "&", "(", ")", ",", ";")):
        return "'" + title.replace("'", "''") + "'"
    return title


def harvest_workbook_style(spreadsheet_id: str, *, service: Any = None) -> dict[str, Any]:
    """Sample each tab's top-left grid (fonts/fills) via ``includeGridData``."""
    from render.runtime import sheets_service

    svc = service or sheets_service()
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields=(
            "properties.title,"
            "sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"
        ),
    ).execute()
    ranges: list[str] = []
    for sh in (meta.get("sheets") or [])[:35]:
        props = sh.get("properties") or {}
        title = str(props.get("title") or "")
        if not title:
            continue
        gp = props.get("gridProperties") or {}
        nc = max(1, min(int(gp.get("columnCount") or 12), 18))
        nr = max(1, min(int(gp.get("rowCount") or 6), 10))
        end_col = _col_letter(nc)
        prefixed = _escape_a1_sheet_title(title)
        ranges.append(f"{prefixed}!A1:{end_col}{nr}")
    if not ranges:
        return {
            "spreadsheet_id": spreadsheet_id,
            "workbook_title": (meta.get("properties") or {}).get("title"),
            "tabs": [],
        }
    full = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
        includeGridData=True,
    ).execute()
    tabs_out: list[dict[str, Any]] = []
    for sh in full.get("sheets") or []:
        props = sh.get("properties") or {}
        title = str(props.get("title") or "")
        sample_cells: list[dict[str, Any]] = []
        for grid in sh.get("data") or []:
            for ri, row in enumerate(grid.get("rowData") or []):
                for ci, cell in enumerate(row.get("values") or []):
                    fmt = cell.get("userEnteredFormat")
                    if not fmt:
                        continue
                    sample_cells.append(
                        {
                            "a1": f"{_col_letter(ci + 1)}{ri + 1}",
                            "userEnteredFormat": fmt,
                            "formattedValue": cell.get("formattedValue"),
                        }
                    )
                    if len(sample_cells) >= 150:
                        break
                if len(sample_cells) >= 150:
                    break
            if len(sample_cells) >= 150:
                break
        tabs_out.append({"title": title, "sample_cells": sample_cells})
    return {
        "spreadsheet_id": spreadsheet_id,
        "workbook_title": (meta.get("properties") or {}).get("title"),
        "tabs": tabs_out,
    }


def derive_style_spec(
    format_dump: dict[str, Any], *, use_llm_assist: bool = False
) -> StyleSpec:
    """Heuristic style from ``harvest_workbook_style`` output; optional LLM assist hook."""
    return extract_style(format_dump, use_llm_assist=use_llm_assist)
