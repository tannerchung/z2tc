#!/usr/bin/env python3
"""Retro-fit the new sectioned "Why" layout onto already-published plan tabs.

The Why column was historically a single space-joined paragraph. The generator now
emits scannable blocks (phase intent → bulleted quality list → caveats → volume), but
existing tabs can't be regenerated without their original event-folded inputs. Since the
old paragraph already contains the right content, this re-flows it in place by parsing it
back into those blocks. Idempotent: cells already containing newlines are left alone.

Usage::

    PYTHONPATH=. python scripts/retro_reflow_why.py --tab "Z2TC_Cindy Kim" --tab "Z2TC_Gaurav Goel"
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

SPREADSHEET_ID = "1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w"
_QUALITY = "This week's quality:"
_WEEK_RE = re.compile(r"^W\d+$")


def _sentences(s: str) -> list[str]:
    parts = re.split(r"\.\s+", s.strip())
    return [(p if p.endswith(".") else p + ".") for p in parts if p.strip()]


def reflow_why(text: str) -> str:
    """Turn a legacy one-paragraph Why into the new block layout. Mirrors plan_layout._week_why."""
    text = (text or "").strip()
    if not text or "\n" in text:  # empty or already reflowed
        return text

    if _QUALITY not in text:
        # Recovery week (single-spaced) or a note-only cell (block-spaced).
        sep = "\n" if text.startswith("Recovery week") else "\n\n"
        return sep.join(_sentences(text))

    pre, rest = text.split(_QUALITY, 1)
    rest = rest.strip()
    # The quality clause list is "A; B." — terminated by the first ". " (clauses carry no periods).
    idx = rest.find(". ")
    if idx == -1:
        quality_part, notes = rest.rstrip("."), ""
    else:
        quality_part, notes = rest[:idx], rest[idx + 2:].strip()

    clauses = [c.strip().rstrip(".") for c in quality_part.split("; ") if c.strip()]
    blocks: list[str] = []
    if pre.strip():
        blocks.append(pre.strip())
    blocks.append(_QUALITY + "\n" + "\n".join(f"• {c}." for c in clauses))
    if notes:
        blocks.extend(_sentences(notes))
    return "\n\n".join(blocks)


def _sheet_id(svc, ss: str, title: str) -> int | None:
    meta = svc.spreadsheets().get(spreadsheetId=ss).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tab", action="append", required=True, help="tab title (repeatable)")
    ap.add_argument("--spreadsheet-id", default=SPREADSHEET_ID)
    args = ap.parse_args()

    svc = sheets_service()
    ss = args.spreadsheet_id

    for tab in args.tab:
        sid = _sheet_id(svc, ss, tab)
        if sid is None:
            print(f"  skip: tab {tab!r} not found", file=sys.stderr)
            continue
        qd = f"'{tab}'"
        grid = svc.spreadsheets().values().get(spreadsheetId=ss, range=qd).execute().get("values", [])

        header = next((r for r in grid if len(r) > 1 and r[1] == "Wk"), None)
        why_col = header.index("Why") if header and "Why" in header else 11

        touched: list[int] = []
        for ri, row in enumerate(grid):
            b = row[1] if len(row) > 1 else ""
            if isinstance(b, str) and _WEEK_RE.match(b) and why_col < len(row) and row[why_col]:
                new = reflow_why(row[why_col])
                if new != row[why_col]:
                    row[why_col] = new
                    touched.append(ri)

        svc.spreadsheets().values().update(
            spreadsheetId=ss, range=f"{qd}!A1", valueInputOption="RAW", body={"values": grid}
        ).execute()
        if touched:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=ss,
                body={"requests": [
                    {"autoResizeDimensions": {"dimensions": {"sheetId": sid, "dimension": "ROWS",
                                                             "startIndex": r, "endIndex": r + 1}}}
                    for r in touched
                ]},
            ).execute()
        print(f"{tab}: reflowed {len(touched)} Why cells (col {why_col}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
