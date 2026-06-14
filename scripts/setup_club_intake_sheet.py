#!/usr/bin/env python3
"""Add an *Intake_setup* worksheet to the club Google Sheet with form-linking instructions.

Requires Google credentials that can edit the spreadsheet (same token as
``render.runtime`` — ``spreadsheets`` scope).

Usage::

    python scripts/setup_club_intake_sheet.py

Set ``Z2TC_CLUB_SPREADSHEET_ID`` to override the default club workbook ID.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SPREADSHEET_ID = "1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w"
TAB_TITLE = "Intake_setup"


def main() -> int:
    from render.runtime import sheets_service

    sid = os.environ.get("Z2TC_CLUB_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID)
    svc = sheets_service()

    meta = svc.spreadsheets().get(spreadsheetId=sid, fields="sheets(properties(sheetId,title))").execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if TAB_TITLE in existing:
        print(f"Sheet tab {TAB_TITLE!r} already exists — skipping create. Edit it in the UI if needed.")
        return 0

    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": TAB_TITLE}}}]},
    ).execute()

    rows = [
        ["Zone 2 Track Club — Intake form (link to this workbook)", "", ""],
        ["", "", ""],
        [
            "1. Create a new Google Form (or duplicate your old one). Questions: see",
            "",
            "",
        ],
        [str(ROOT / "docs" / "intake-google-form.md"), "", ""],
        ["", "", ""],
        [
            "2. In the Form: Responses → Link to Sheets → Select existing spreadsheet →",
            "paste this file's URL or ID:",
            "",
        ],
        [f"https://docs.google.com/spreadsheets/d/{sid}/edit", "", ""],
        ["", "", ""],
        [
            "3. Rename the new responses tab to something like Intake_responses.",
            "",
            "",
        ],
        [
            "4. Paste your published form URL here (for coaches):",
            "(replace this cell)",
            "",
        ],
        ["", "", ""],
        ["Strava-filled fields (do not ask athletes): w_now, p_history, longest_run_mi, vdot.", "", ""],
        [
            "Primary vs secondary marathons: engine uses PRIMARY for the 18-week block; see docs.",
            "",
            "",
        ],
    ]
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{TAB_TITLE}'!A1:C20",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print(f"Added tab {TAB_TITLE!r} to spreadsheet {sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
