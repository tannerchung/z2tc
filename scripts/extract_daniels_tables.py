"""Extract Daniels' Running Formula Table 5.2 (Training Intensities by VDOT) from the
book PDF into engine/data/daniels_table_5_2.json.

This is a one-time data generator, re-runnable if the source changes. Output values are
the book's printed paces (facts used as engine fixtures); the PDF itself is not committed.

Table 5.2 is printed across two facing pages:
  - left page:  VDOT | E(km,mile range) | M(km,mile) | T(400m,km,mile)
  - right page: I(400m,km,1200m,mile) | R(200m,300m,400m,600m,800m) | VDOT

Run: python scripts/extract_daniels_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "Daniels-running-formula.pdf"
OUT = ROOT / "engine" / "data" / "daniels_table_5_2.json"
EMT_PAGE, IR_PAGE = 98, 99


def _lines(doc: fitz.Document, page: int) -> list[str]:
    return [ln.strip() for ln in doc[page - 1].get_text().splitlines() if ln.strip()]


def _is_vdot(token: str) -> bool:
    return token.isdigit() and 30 <= int(token) <= 85


def _parse_emt(doc: fitz.Document) -> dict[int, dict]:
    """Rows are 8 tokens: VDOT, E-km-range, E-mile-range, M-km, M-mile, T-400, T-km, T-mile.
    The two E cells contain a hyphenated range, which anchors a valid row."""
    out: dict[int, dict] = {}
    ls = _lines(doc, EMT_PAGE)
    i = 0
    while i < len(ls):
        if _is_vdot(ls[i]) and i + 7 < len(ls) and "-" in ls[i + 1] and "-" in ls[i + 2]:
            v, row = int(ls[i]), ls[i + 1 : i + 8]
            out[v] = {"E_mile": row[1], "M_mile": row[3], "T_mile": row[6]}
            i += 8
        else:
            i += 1
    return out


def _parse_ir(doc: fitz.Document) -> dict[int, dict]:
    """The right page streams 10 tokens per row (VDOT trailing):
    I-400, I-km, I-1200, I-mile, R-200, R-300, R-400, R-600, R-800, VDOT."""
    ls = _lines(doc, IR_PAGE)
    start = ls.index("800 m") + 1  # data begins after the last column sub-header
    toks = [t for t in ls[start:] if t != "(continued)"]
    # Drop a trailing page-number token if present (not part of a 10-wide row).
    if len(toks) % 10 == 1:
        toks = toks[:-1]
    out: dict[int, dict] = {}
    for c in range(0, len(toks) - 9, 10):
        row = toks[c : c + 10]
        if not _is_vdot(row[9]):
            continue
        out[int(row[9])] = {
            "I_400m": row[0],
            "I_km": row[1],
            "I_mile": row[3],
            "R_200m": row[4],
            "R_400m": row[6],
        }
    return out


def main() -> int:
    doc = fitz.open(PDF)
    emt, ir = _parse_emt(doc), _parse_ir(doc)
    vdots = sorted(set(emt) & set(ir))
    table = {str(v): {**emt[v], **ir[v]} for v in vdots}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(table)} VDOT rows ({vdots[0]}-{vdots[-1]}) to {OUT}")
    for v in (30, 43, 50, 62):
        print(f"  {v}: {table[str(v)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
