"""Write ``TrainingPlan`` grids into a club spreadsheet; read coach feedback cells."""

from __future__ import annotations

import re
from typing import Any

from googleapiclient.errors import HttpError

from engine.plan.models import AthleteInputs, TrainingPlan
from llm.boundary import StyleSpec
from store.events import DifficultyPayload, EventRecord, FatigueFlagPayload

from render.plan_layout import build_plan_sheet, plan_to_values
from render.plan_sheet_format import build_format_requests
from render.plan_sheet_theme import PlanSheetTheme, theme_from_style_spec
from render.style import default_club_spreadsheet_id


def _escape_sheet_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _sheet_id_for_title(service: Any, spreadsheet_id: str, title: str) -> int | None:
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))",
    ).execute()
    for sh in meta.get("sheets") or []:
        p = sh.get("properties") or {}
        if p.get("title") == title:
            return int(p["sheetId"])
    return None


def _ensure_sheet(service: Any, spreadsheet_id: str, title: str) -> tuple[int, bool]:
    sid = _sheet_id_for_title(service, spreadsheet_id, title)
    if sid is not None:
        return sid, False
    body = {"requests": [{"addSheet": {"properties": {"title": title[:99]}}}]}
    res = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    new_id = int(res["replies"][0]["addSheet"]["properties"]["sheetId"])
    return new_id, True


def render_plan(
    plan: TrainingPlan,
    style: StyleSpec,
    *,
    spreadsheet_id: str | None = None,
    sheet_title: str | None = None,
    service: Any = None,
    hidden: bool = False,
    inputs: AthleteInputs | None = None,
) -> dict[str, Any]:
    """Write ``plan`` to a tab using the deterministic plan-sheet layout."""
    from render.runtime import sheets_service

    svc = service or sheets_service()
    ss_id = spreadsheet_id or default_club_spreadsheet_id()
    title = sheet_title or f"Z2TC_{(plan.athlete or 'plan')[:24]}".replace("/", "-")
    qt = _escape_sheet_title(title)
    sheet_id, is_new = _ensure_sheet(svc, ss_id, title)

    if inputs is not None:
        layout = build_plan_sheet(plan, inputs)
        values = layout.values
        theme = theme_from_style_spec(style)
        requests = build_format_requests(sheet_id, layout, theme)
    else:
        values = plan_to_values(plan)
        layout = None
        theme = theme_from_style_spec(style)
        requests = _legacy_header_format(sheet_id, values, theme)

    if not is_new:
        try:
            svc.spreadsheets().values().clear(
                spreadsheetId=ss_id,
                range=f"{qt}",
                body={},
            ).execute()
        except HttpError:
            pass
        # Drop stale merges *before* writing values — otherwise cells under an old merge
        # are silently discarded and the new row appears blank.
        try:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=ss_id,
                body={
                    "requests": [
                        {
                            "unmergeCells": {
                                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 200}
                            }
                        }
                    ]
                },
            ).execute()
        except HttpError:
            pass
    svc.spreadsheets().values().update(
        spreadsheetId=ss_id,
        range=f"{qt}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    if hidden:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "hidden": True},
                    "fields": "hidden",
                }
            }
        )
    if requests:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=ss_id, body={"requests": requests}
        ).execute()

    nrows = len(values)
    return {
        "spreadsheet_id": ss_id,
        "sheet_title": title,
        "rows_written": nrows,
        "hidden": hidden,
        "layout": "plan_sheet" if inputs is not None else "legacy",
        "weeks": len(plan.weeks),
    }


def _legacy_header_format(
    sheet_id: int, values: list[list], theme: PlanSheetTheme
) -> list[dict[str, Any]]:
    """Minimal header row when ``inputs`` omitted (tests / backward compat)."""
    ncols = len(values[-1]) if values else 1
    header_row = next((i for i, r in enumerate(values) if r and r[0] == "week"), 0)
    rgb = theme.header_rgb
    fmt: dict[str, Any] = {
        "textFormat": {
            "bold": True,
            "fontSize": theme.header_font_size,
            "fontFamily": theme.font_family,
        },
        "backgroundColor": {"red": rgb[0], "green": rgb[1], "blue": rgb[2]},
    }
    return [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row,
                    "endRowIndex": header_row + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": ncols,
                },
                "cell": {"userEnteredFormat": fmt},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }
    ]


def read_feedback_cells(
    spreadsheet_id: str,
    sheet_title: str,
    athlete_id: str,
    *,
    feel_a1: str = "B2:B30",
    check_a1: str = "C2:C30",
    service: Any = None,
) -> list[EventRecord]:
    """Map free-text 'feel' and checkbox-ish columns to proposed sheet-sourced events."""
    from render.runtime import sheets_service

    svc = service or sheets_service()
    qt = _escape_sheet_title(sheet_title)
    res = (
        svc.spreadsheets()
        .values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=[f"{qt}!{feel_a1}", f"{qt}!{check_a1}"],
        )
        .execute()
    )
    rngs = res.get("valueRanges") or []
    feel_vals = (rngs[0].get("values") or []) if rngs else []
    check_vals = (rngs[1].get("values") or []) if len(rngs) > 1 else []
    out: list[EventRecord] = []
    for row in feel_vals:
        if not row:
            continue
        text = str(row[0] or "").lower()
        if "hard" in text or "struggle" in text or "heavy" in text:
            out.append(
                EventRecord(
                    athlete_id=athlete_id,
                    source="sheet",
                    status="proposed",
                    payload=DifficultyPayload(delta=1),
                )
            )
        elif "easy" in text or "good" in text or "great" in text:
            out.append(
                EventRecord(
                    athlete_id=athlete_id,
                    source="sheet",
                    status="proposed",
                    payload=DifficultyPayload(delta=-1),
                )
            )
    truthy = re.compile(r"^(true|x|yes|1|y)\s*$", re.I)
    for row in check_vals:
        if not row:
            continue
        cell = str(row[0] or "").strip()
        if truthy.match(cell):
            out.append(
                EventRecord(
                    athlete_id=athlete_id,
                    source="sheet",
                    status="proposed",
                    payload=FatigueFlagPayload(
                        week_start="unknown",
                        reason="sheet_checkbox",
                    ),
                )
            )
    return out
