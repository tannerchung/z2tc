# Plan sheet layout & styling

Deterministic Google Sheets layout for athlete plan drafts published into the club
workbook. **Canonical spec:** [`plan-sheet-layout.md`](plan-sheet-layout.md).

| Module | Role |
|--------|------|
| [`../../render/plan_layout.py`](../../render/plan_layout.py) | Tab structure (title → subtitle → narrative → paces → color-coded week table → race row) |
| [`../../render/plan_sheet_format.py`](../../render/plan_sheet_format.py) | Sheets `batchUpdate` formatting (phase bands, recovery shading, merges, widths) |
| [`../../render/workout_glossary.py`](../../render/workout_glossary.py) | Workout label → plain English (fills the per-week **Why**) |
| [`../../render/plan_sheet_theme.py`](../../render/plan_sheet_theme.py) | Palette / fonts sampled from the club `Cindy` tab |
| [`../../render/plan_sheet_format.py`](../../render/plan_sheet_format.py) | Sheets API `batchUpdate` requests |

Refresh harvested theme: `python main.py ingest-style` → `output/club_workbook_style.json`.
