"""Write ``TrainingPlan`` grids into a club spreadsheet; read coach feedback cells."""

from __future__ import annotations

import re
from typing import Any

from googleapiclient.errors import HttpError

from engine.plan.models import DAY_NAMES, TrainingPlan
from llm.boundary import StyleSpec
from store.events import DifficultyPayload, EventRecord, FatigueFlagPayload

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


def plan_to_values(plan: TrainingPlan) -> list[list[str | int | float]]:
    """Tabular values: metadata rows, blank, header, one row per week."""
    meta_rows: list[list[str | int | float]] = [
        ["athlete", plan.athlete],
        ["method", plan.method],
        ["vdot", plan.vdot],
        ["peak_miles", plan.peak_miles],
        ["block_weeks", plan.block_weeks],
        ["goal_name", str(plan.goal.get("name", ""))],
        ["goal_date", str(plan.goal.get("date", ""))],
        ["goal_time_s", str(plan.goal.get("goal_time_s", ""))],
    ]
    header = ["week", "phase", "label", "target_mi", "planned_mi"] + list(DAY_NAMES)
    rows: list[list[str | int | float]] = [header]
    for w in plan.weeks:
        by_day = {d.day: d for d in w.days}
        row: list[str | int | float] = [
            w.index,
            w.phase,
            w.label,
            w.target_miles,
            w.planned_miles,
        ]
        for dn in DAY_NAMES:
            d = by_day.get(dn)
            if not d:
                row.append("")
                continue
            wo = d.workout
            cell = (wo.label or "").replace("\n", " ").strip()
            if wo.distance_mi is not None:
                cell = f"{cell} ({wo.distance_mi:g} mi)".strip()
            row.append(cell)
        rows.append(row)
    return meta_rows + [[]] + rows


def render_plan(
    plan: TrainingPlan,
    style: StyleSpec,
    *,
    spreadsheet_id: str | None = None,
    sheet_title: str | None = None,
    service: Any = None,
) -> dict[str, Any]:
    """Write ``plan`` to a tab (create if missing) and apply light header formatting."""
    from render.runtime import sheets_service

    svc = service or sheets_service()
    ss_id = spreadsheet_id or default_club_spreadsheet_id()
    title = sheet_title or f"Z2TC_{(plan.athlete or 'plan')[:24]}".replace("/", "-")
    qt = _escape_sheet_title(title)
    sheet_id, is_new = _ensure_sheet(svc, ss_id, title)
    values = plan_to_values(plan)
    if not is_new:
        try:
            svc.spreadsheets().values().clear(
                spreadsheetId=ss_id,
                range=f"{qt}",
                body={},
            ).execute()
        except HttpError:
            pass
    svc.spreadsheets().values().update(
        spreadsheetId=ss_id,
        range=f"{qt}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    ncols = len(values[-1]) if values else 1
    nrows = len(values)
    header_row = next(
        (i for i, r in enumerate(values) if r and r[0] == "week"),
        0,
    )
    rgb = style.header_rgb
    bg: dict[str, Any] | None = None
    if rgb and len(rgb) == 3:
        bg = {
            "red": float(rgb[0]),
            "green": float(rgb[1]),
            "blue": float(rgb[2]),
        }
    fmt: dict[str, Any] = {
        "textFormat": {
            "bold": True,
            "fontSize": style.title_font_size or 10,
            "fontFamily": style.title_font_family or "Arial",
        }
    }
    if bg:
        fmt["backgroundColor"] = bg
    requests = [
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
    svc.spreadsheets().batchUpdate(
        spreadsheetId=ss_id, body={"requests": requests}
    ).execute()
    return {"spreadsheet_id": ss_id, "sheet_title": title, "rows_written": nrows}


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
