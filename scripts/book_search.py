#!/usr/bin/env python3
"""Page-indexed full-text search over the training books in the repo.

Lets us cite the *actual* text (Daniels' Running Formula, Pfitzinger's Advanced
Marathoning, Hansons Marathon Method, Higdon's Marathon) by page instead of quoting from
memory. Builds a one-time per-page text cache, then searches it and prints page numbers +
snippets, dumps a whole page for an exact quote, or prints the curated citations the engine
encodes (``cite``).

Usage::

    python scripts/book_search.py build                      # extract text cache (once)
    python scripts/book_search.py search "long run" --book daniels
    python scripts/book_search.py search "2.5 hours|150 min" --regex --book daniels
    python scripts/book_search.py page --book daniels --page 147
    python scripts/book_search.py cite long-run              # engine's long-run citations

``--book`` accepts: daniels, pfitz/pfitzinger, hanson, higdon, all (default for search), or
a PDF path. The cache lives under ``output/book_index/`` (gitignored). Page numbers are the
PDF's 1-based page index; the printed page is usually visible in the snippet's running header.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "output" / "book_index"

BOOKS = {
    "daniels": PROJECT_ROOT / "Daniels-running-formula.pdf",
    "pfitz": PROJECT_ROOT / "Advanced Marathoning - Pfitzinger, Pete.pdf",
    "pfitzinger": PROJECT_ROOT / "Advanced Marathoning - Pfitzinger, Pete.pdf",
    "hanson": PROJECT_ROOT / "Hansons Marathon Method - Luke Humphrey.pdf",
    "hansons": PROJECT_ROOT / "Hansons Marathon Method - Luke Humphrey.pdf",
    "higdon": PROJECT_ROOT / "Marathon, Revised and Updated_ The Ultimat - Hal Higdon.pdf",
}

ALL_BOOKS = ["daniels", "pfitz", "hanson", "higdon"]


def _resolve_books(book: str | None) -> list[tuple[str, Path]]:
    if not book or book == "all":
        return [(k, BOOKS[k]) for k in ALL_BOOKS]
    key = book.strip().lower()
    if key in BOOKS:
        return [(key, BOOKS[key])]
    p = Path(book)
    if p.is_file():
        return [(p.stem, p)]
    raise SystemExit(
        f"Unknown book {book!r}. Use: {' | '.join(ALL_BOOKS)} | all | <pdf path>"
    )


def _cache_path(pdf: Path) -> Path:
    return CACHE_DIR / f"{pdf.stem}.jsonl"


def build_index(pdf: Path, *, force: bool = False) -> Path:
    import fitz  # pymupdf (already a project dep; see scripts/extract_daniels_tables.py)

    out = _cache_path(pdf)
    if out.exists() and not force:
        return out
    if not pdf.is_file():
        raise SystemExit(f"Missing PDF: {pdf}")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    with out.open("w", encoding="utf-8") as fh:
        for i in range(1, doc.page_count + 1):
            try:
                text = doc[i - 1].get_text() or ""
            except Exception as exc:  # one bad page should not kill the build
                text = ""
                print(f"[warn] {pdf.name} page {i}: {exc}", file=sys.stderr)
            fh.write(json.dumps({"page": i, "text": text}, ensure_ascii=False) + "\n")
    print(f"Indexed {pdf.name} -> {out} ({doc.page_count} pages)", file=sys.stderr)
    return out


def load_index(pdf: Path) -> list[dict]:
    path = _cache_path(pdf)
    if not path.exists():
        build_index(pdf)
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read index {path}: {exc}")
    return rows


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def search(books, pattern: str, *, regex: bool, context: int, max_hits: int) -> int:
    flags = re.IGNORECASE
    rx = re.compile(pattern if regex else re.escape(pattern), flags)
    total = 0
    for label, pdf in books:
        rows = load_index(pdf)
        hits = 0
        for row in rows:
            text = row["text"]
            for m in rx.finditer(text):
                start = max(0, m.start() - context)
                end = min(len(text), m.end() + context)
                snippet = _norm(text[start:end])
                print(f"[{label} p.{row['page']}] …{snippet}…")
                hits += 1
                total += 1
                if hits >= max_hits:
                    break
            if hits >= max_hits:
                break
        print(f"# {label}: {hits} hit(s){' (capped)' if hits >= max_hits else ''}\n", file=sys.stderr)
    if total == 0:
        print("No matches.", file=sys.stderr)
    return 0


def show_citations(topic: str) -> int:
    """Print the curated, page-verified citations the engine encodes (engine/plan/citations.py)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from engine.plan import citations as C

    if topic in ("long-run", "long_run", "longrun"):
        cites = C.long_run_citations()
    elif topic in ("nutrition", "fuel", "hydration"):
        from engine.plan import nutrition as N

        for n in N.all_notes():
            print(f"[{n.ref} — {n.topic}]\n  {n.hint}\n")
        return 0
    elif topic == "all":
        cites = list(C.CITATIONS.values())
    elif topic in C.CITATIONS:
        cites = [C.CITATIONS[topic]]
    else:
        raise SystemExit(
            f"Unknown topic {topic!r}. Use: long-run | nutrition | all | {' | '.join(sorted(C.CITATIONS))}"
        )
    for c in cites:
        print(f"[{c.ref}]\n  rule:  {c.rule}\n  quote: \u201c{c.quote}\u201d\n")
    return 0


def show_page(books, page: int) -> int:
    for label, pdf in books:
        rows = load_index(pdf)
        match = next((r for r in rows if r["page"] == page), None)
        if match is None:
            print(f"# {label}: no page {page}", file=sys.stderr)
            continue
        print(f"===== {label} — PDF page {page} =====")
        print(match["text"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Extract per-page text cache for one or all books.")
    p_build.add_argument("--book", default="all")
    p_build.add_argument("--force", action="store_true", help="Rebuild even if cache exists.")

    p_search = sub.add_parser("search", help="Search the text cache; prints page + snippet.")
    p_search.add_argument("pattern")
    p_search.add_argument("--book", default="all")
    p_search.add_argument("--regex", action="store_true", help="Treat pattern as a regex.")
    p_search.add_argument("--context", type=int, default=160, help="Chars of context around a hit.")
    p_search.add_argument("--max", type=int, default=20, help="Max hits per book.")

    p_page = sub.add_parser("page", help="Dump the full text of one PDF page (for an exact quote).")
    p_page.add_argument("--book", required=True)
    p_page.add_argument("--page", type=int, required=True)

    p_cite = sub.add_parser("cite", help="Print curated, page-verified citations the engine encodes.")
    p_cite.add_argument("topic", nargs="?", default="long-run", help="long-run | nutrition | all | <citation key>")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        for _label, pdf in _resolve_books(args.book):
            build_index(pdf, force=args.force)
        return 0
    if args.cmd == "search":
        return search(_resolve_books(args.book), args.pattern, regex=args.regex,
                      context=args.context, max_hits=args.max)
    if args.cmd == "page":
        return show_page(_resolve_books(args.book), args.page)
    if args.cmd == "cite":
        return show_citations(args.topic)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
