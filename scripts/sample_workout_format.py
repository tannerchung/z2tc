#!/usr/bin/env python3
"""Publish a live sample tab showing the stacked multi-line workout-cell format.

Duplicates an existing draft tab (so all colors / widths / merges carry over), then
rewrites just the seven day-columns of every week row through
:func:`render.workout_cell.format_cell`. Lets us eyeball the Runna-style layout in
context before wiring it into the generator and republishing the real drafts.

Usage::

    PYTHONPATH=. python scripts/sample_workout_format.py
    PYTHONPATH=. python scripts/sample_workout_format.py --source "Z2TC_Gaurav Goel"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from render.runtime import sheets_service  # noqa: E402
from render.workout_cell import format_cell  # noqa: E402

SPREADSHEET_ID = "1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w"
DAY_COLS = range(3, 10)  # D..J (Mon..Sun) — A spacer, B Wk, C Date
_WEEK_RE = re.compile(r"^W\d+$")


def _sheet_id(svc, ss_id: str, title: str) -> int | None:
    meta = svc.spreadsheets().get(spreadsheetId=ss_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="Z2TC_Cindy Kim", help="draft tab to read from")
    ap.add_argument("--dest", default="SAMPLE — Workout Format", help="sample tab title")
    ap.add_argument("--in-place", action="store_true", help="reformat the source tab itself (no sample copy)")
    ap.add_argument("--spreadsheet-id", default=SPREADSHEET_ID)
    args = ap.parse_args()

    svc = sheets_service()
    ss = args.spreadsheet_id

    src_id = _sheet_id(svc, ss, args.source)
    if src_id is None:
        print(f"Source tab {args.source!r} not found", file=sys.stderr)
        return 1

    if args.in_place:
        target, new_id = args.source, src_id
    else:
        target = args.dest
        # Fresh sample each run.
        dest_id = _sheet_id(svc, ss, args.dest)
        if dest_id is not None:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=ss, body={"requests": [{"deleteSheet": {"sheetId": dest_id}}]}
            ).execute()
        dup = svc.spreadsheets().batchUpdate(
            spreadsheetId=ss,
            body={"requests": [{"duplicateSheet": {"sourceSheetId": src_id, "newSheetName": args.dest, "insertSheetIndex": 2}}]},
        ).execute()
        new_id = dup["replies"][0]["duplicateSheet"]["properties"]["sheetId"]
        svc.spreadsheets().batchUpdate(
            spreadsheetId=ss,
            body={"requests": [{"updateSheetProperties": {"properties": {"sheetId": new_id, "hidden": False}, "fields": "hidden"}}]},
        ).execute()

    qd = f"'{target}'"
    grid = svc.spreadsheets().values().get(spreadsheetId=ss, range=qd).execute().get("values", [])

    week_rows: list[int] = []
    for ri, row in enumerate(grid):
        b = row[1] if len(row) > 1 else ""
        if isinstance(b, str) and _WEEK_RE.match(b):
            week_rows.append(ri)
            for c in DAY_COLS:
                # Skip cells already stacked (newline present) so the reformat is re-run safe.
                if c < len(row) and row[c] and "\n" not in row[c]:
                    row[c] = format_cell(row[c])

    svc.spreadsheets().values().update(
        spreadsheetId=ss, range=f"{qd}!A1", valueInputOption="RAW", body={"values": grid}
    ).execute()

    # Grow the week rows so every stacked line is visible.
    resize = [
        {
            "autoResizeDimensions": {
                "dimensions": {"sheetId": new_id, "dimension": "ROWS", "startIndex": r, "endIndex": r + 1}
            }
        }
        for r in week_rows
    ]
    if resize:
        svc.spreadsheets().batchUpdate(spreadsheetId=ss, body={"requests": resize}).execute()

    print(f"Reformatted {len(week_rows)} week rows in {target!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
