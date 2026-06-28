"""Render a one-line plan-cell label as a compact, stacked "workout card".

Athletes read a structured session as warm-up / main set / cool-down on their own
lines (the way Runna/most coaching apps lay it out). This turns the single-line
label produced by :func:`render.plan_layout._cell_label` into that stacked form,
using single newlines so the cell stays compact inside the calendar grid.

It operates on the rendered cell *string* (the one source of truth), so the same
transform applies whether the caller has a ``Workout`` object or only the label.
"""

from __future__ import annotations

import re

_EFFORT = {
    "E": "Easy",
    "M": "MP",
    "T": "Threshold",
    "I": "VO2max",
    "R": "Rep",
    "steady": "Steady",
}

_DIST_SUFFIX = re.compile(r"\s*\((\d+(?:\.\d+)?)\s*mi\)\s*$")
_INLINE_DIST = re.compile(r"(\d+(?:\.\d+)?)\s*mi\b")


def _titlecase(name: str) -> str:
    """Capitalize a session name while preserving tokens that carry their own casing
    (``VO2max``, ``MP``, ``w/``) or hyphen-joined words (``Broken-T``). Slash-joined
    words are capitalized per part (``Over/unders`` -> ``Over/Unders``)."""
    out: list[str] = []
    for w in name.split(" "):
        if not w or w == "w/" or w.isupper() or any(c.isdigit() for c in w) or "-" in w:
            out.append(w)
        elif "/" in w:
            out.append("/".join(p[:1].upper() + p[1:] if p else p for p in w.split("/")))
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def _stack(title: str, details: list[str]) -> str:
    """Title, a blank line, then the detail lines (single-spaced)."""
    details = [d for d in details if d]
    return title + "\n\n" + "\n".join(details) if details else title


def _name_and_distance(text: str) -> tuple[str, str | None, str]:
    body = text
    dist: str | None = None
    m = _DIST_SUFFIX.search(text)
    if m:
        dist = m.group(1)
        body = text[: m.start()].rstrip()
    head = body.split(":")[0].strip()
    name = re.split(r"\s+\d", head)[0].strip()
    if dist is None:
        mi = _INLINE_DIST.search(head)
        if mi:
            dist = mi.group(1)
    return name, dist, body


def _title(name: str, dist: str | None) -> str:
    name = _titlecase(name)
    return f"{name} — {dist} mi" if dist else name


def _clean_main(frag: str) -> str:
    """Tidy a main-set fragment for display: drop ``/mi`` and ``pace`` filler, use ``×``
    for rep counts and ``→`` for distance ladders, and collapse recovery to ``, …``."""
    s = frag.strip()
    s = s.replace("/mi)", ")")
    s = s.replace(" pace (", " (")
    s = re.sub(r"(\d)\s*x\s*", r"\1 × ", s)
    s = re.sub(r"(\d+(?:-\d+)+)\s*m\b", lambda mm: mm.group(1).replace("-", "→") + " m", s)
    s = re.sub(r"(\d+) × \((.*)\) nonstop", r"\1 × nonstop: \2", s)
    s = s.replace(" w/ ", ", ")
    s = re.sub(r"(\d+)\s+s jog", r"\1s jog", s)
    return s.strip()


# Grid-method labels (Pfitzinger / Hansons / Higdon) name the session in the book's own terms —
# "Lactate threshold 10 mi w/ 5 mi @ 15K to half marathon race pace" — and carry the concrete
# work pace on the Workout, not in the label text. These helpers stack that into a card and fold
# in the pace so the cell is executable at a glance, the way the Daniels recipes already are.
_GRID_PREFIXES = ("General aerobic", "Medium-long run", "Recovery")
# Map Pfitzinger/grid book pace phrases to (canonical zone, short descriptor). Leading the work line
# with the canonical zone (Threshold / Marathon pace / VO2max) keeps the card uniform with the Daniels
# recipes and lets the pace color-coder (render.plan_sheet_format) tint it by effort — book phrasing
# like "15K to half marathon race pace" otherwise fails to color as threshold and trips the
# marathon-pace rule on the word "marathon".
_ZONE_CANON: dict[str, tuple[str, str | None]] = {
    "15K to half marathon race pace": ("Threshold", "15K–half pace"),
    "half marathon race pace": ("Threshold", "half marathon pace"),
    "marathon race pace": ("Marathon pace", None),
    "5K race pace": ("VO2max", "5K pace"),
}


def _clean_recovery(rec: str) -> str:
    return re.sub(r"(\d+)\s+to\s+(\d+)", r"\1–\2", rec.strip())


def _canon_zone(zone: str) -> tuple[str, str | None]:
    """Canonical effort name + short descriptor for a grid pace phrase (drives color + uniformity)."""
    z = zone.strip()
    if z in _ZONE_CANON:
        return _ZONE_CANON[z]
    low = z.lower()
    if "5k" in low:
        return ("VO2max", z)
    if "15k" in low or "half marathon" in low:
        return ("Threshold", z)
    if "marathon" in low:
        return ("Marathon pace", None)
    return (z, None)


def _warmup_cooldown(total: str | None, work: str, is_reps: bool) -> tuple[str | None, str | None]:
    """Daniels-style explicit warm-up / cool-down lines for a grid session.

    Pfitzinger frames a session by total miles (e.g. an 8-mi run *with* 4 mi at threshold); the easy
    balance brackets the quality block as warm-up + cool-down. For a single distance block the balance
    is exact (total − work), split evenly. For rep workouts the jog recoveries also live inside the
    total, so the per-side mileage isn't clean — keep the lines but drop the figure.
    """
    if is_reps:
        return ("Warm-up: easy", "Cool-down: easy")
    wm = re.match(r"([\d.]+)\s*mi\b", work)
    try:
        if wm and total is not None:
            bal = float(total) - float(wm.group(1))
            if bal > 0.05:
                half = bal / 2
                return (f"Warm-up: {half:g} mi easy", f"Cool-down: {half:g} mi easy")
    except ValueError:
        pass
    return (None, None)


def _grid_card(name: str, dist: str | None, body: str, pace: str | None) -> str | None:
    """Stack a grid-method label into title + detail lines, folding in the concrete ``pace`` and
    naming the canonical zone so the card reads — and colors — like the Daniels recipes.
    Returns ``None`` if the label isn't a recognized grid shape (caller falls back)."""
    pace_sfx = f" ({pace})" if pace else ""
    if " w/ " in body:
        head, tail = body.split(" w/ ", 1)
        tail = tail.strip()
        pm = " p.m." if tail.endswith(" p.m.") else ""
        if pm:
            tail = tail[: -len(" p.m.")].strip()
        details: list[str] = []
        if " @ " in tail:
            work, rest = tail.split(" @ ", 1)
            zone, _, recovery = rest.partition(";")
            work_raw = work.strip()
            work_clean = re.sub(r"(\d)\s*x\s*", r"\1 × ", work_raw)
            is_reps = "×" in work_clean
            canon, desc = _canon_zone(zone)
            bits = ", ".join(b for b in (desc, pace) if b)
            wu, cd = _warmup_cooldown(dist, work_raw, is_reps)
            if wu:
                details.append(wu)
            details.append(f"{work_clean} @ {canon}" + (f" ({bits})" if bits else ""))
            if recovery.strip():
                details.append(_clean_recovery(recovery))
            if cd:
                details.append(cd)
        elif "strides" in tail:
            strides = re.sub(r"(\d)\s*x\s*", r"\1 × ", tail)
            details.append(f"@ Easy{pace_sfx}")
            details.append(f"+ {strides}")
        else:
            return None
        if pm:
            details.append("(second run, p.m.)")
        return _stack(_title(name, dist), details)
    if any(name.startswith(p) for p in _GRID_PREFIXES) or name.startswith("Medium-long"):
        return _stack(_title(name, dist), [f"@ Easy{pace_sfx}"])
    return None


def format_cell(text: str, pace: str | None = None) -> str:
    """Return the stacked, multi-line rendering of a plan cell label.

    ``pace`` is the workout's concrete per-mile pace (``Workout.pace``); grid-method labels
    (Pfitzinger/Hansons/Higdon) describe the work in the book's words but keep the number on the
    Workout, so it is threaded in here to make those cells executable at a glance.
    """
    text = (text or "").strip()
    if not text or text in {"Rest Day", "—"} or text.isupper():
        return text

    # Pfitzinger tune-up race ("8K-15K tune-up race (total 9-13 mi)"): the leading "8K" trips the
    # generic name/distance split, so handle it explicitly.
    if "tune-up race" in text.lower():
        rng = re.search(r"\(total\s*([\d\-–]+)\s*mi\)", text)
        title = re.split(r"\s*\(total", text)[0].strip()
        title = re.sub(r"tune-up race", "Tune-up Race", title, flags=re.I)
        title = re.sub(r"(\d+K)-(\d+K)", r"\1–\2", title)  # range dash, keep "Tune-up" hyphen
        note = f"total {rng.group(1).replace('-', '–')} mi" if rng else None
        return _stack(title, ([note] if note else []) + ["easy warm-up + cool-down, race the middle"])

    # Scheduled cross-training (a rest day turned into low-impact aerobic work).
    if text.lower().startswith(("cross training", "cross-training")):
        mins = re.search(r"\((\d+)\s*min\)", text)
        title = "Cross-training" + (f" — {mins.group(1)} min" if mins else "")
        return _stack(title, ["easy aerobic, low-impact (bike / elliptical / swim)"])

    name, dist, body = _name_and_distance(text)

    # Structured session: warm-up → main set(s) → cool-down.
    if " → " in body:
        parts = [p.strip() for p in body.split(":", 1)[1].split(" → ")]
        details: list[str] = []
        for p in parts:
            if "warm-up" in p:
                details.append("Warm-up: " + p.replace(" warm-up", "").strip())
            elif "cool-down" in p:
                details.append("Cool-down: " + p.replace(" cool-down", "").strip())
            else:
                details.append(_clean_main(p))
        return _stack(_title(name, dist), details)

    # Continuous blend: "… (nonstop): 4.8 E + 8 M + … (M @ 8:46/mi)".
    if "(nonstop):" in body:
        seg_text = body.split(":", 1)[1].strip()
        mp = re.search(r"\(M @ (\d+:\d+)", seg_text)
        mp_pace = mp.group(1) if mp else None
        seg_text = re.sub(r"\s*\(M @ [^)]*\)\s*$", "", seg_text)
        details = []
        for term in seg_text.split(" + "):
            term = term.strip()
            mt = re.match(r"([\d.]+)\s+(\S+)$", term)
            if not mt:
                details.append(term)
                continue
            n, lab = mt.group(1), mt.group(2)
            if lab == "M" and mp_pace:
                details.append(f"{n} mi @ MP ({mp_pace})")
            elif lab == "steady":
                # "Steady" isn't in the paces table and has no number in the label, so name the
                # effort band explicitly (the engine sets it to the easy↔MP midpoint).
                details.append(f"{n} mi @ Steady (between easy & MP)")
            else:
                details.append(f"{n} mi @ {_EFFORT.get(lab, lab)}")
        return _stack(_title(name, dist), details)

    # Long run with fartlek surges: an easy long run with short surges sprinkled in — you float
    # back to easy between them. Spell out the cadence (~one every N mi) so the athlete knows
    # when to start each surge without a watch prompt (auto-surge cueing is a future feature).
    if body.startswith("Long run w/ fartlek"):
        pace = re.search(r"@ Easy \((\d+:\d+)", body)
        surge = re.search(r"\+\s*(\d+) x 1 min surges", body)
        pace_str = pace.group(1) if pace else None
        details = [f"{dist} mi @ Easy ({pace_str})" if (dist and pace_str) else (f"@ Easy ({pace_str})" if pace_str else "@ Easy")]
        if surge:
            details.append(f"+ {surge.group(1)} × 1 min surges @ ~10K effort")
            try:
                spacing = float(dist) / int(surge.group(1))
                details.append(f"one ~every {spacing:.1f} mi, easy jog between")
            except (TypeError, ValueError, ZeroDivisionError):
                details.append("spaced ~evenly, easy jog between")
        return _stack(_title(name, dist), details)

    # Plain long run.
    if body.startswith("Long run"):
        pace = re.search(r"@ Easy \((\d+:\d+)", body)
        return _stack(_title(name, dist), [f"@ Easy ({pace.group(1)})"] if pace else [])

    # Easy run that finishes with strides.
    if "strides to finish" in body:
        s = re.search(r"(\d+) x 20 sec strides", body)
        n = s.group(1) if s else "6"
        title = f"Easy Run — {dist} mi" if dist else "Easy Run"
        return _stack(title, [f"+ {n} × 20 sec strides"])

    # Pre-race shakeout.
    if body.startswith("Shakeout"):
        rest = body.split(":", 1)[1].strip()
        note = ""
        nm = re.search(r"\s*\(([^)]*)\)\s*$", rest)
        if nm:
            note = nm.group(1)
            rest = rest[: nm.start()].strip()
        rest = re.sub(r"(\d+) x ", r"\1 × ", rest).replace("2 mi very easy", "very easy")
        pieces = rest.split(" + ")
        details = [pieces[0]] + [f"+ {p}" for p in pieces[1:]]
        if note:
            details.append(f"({note})")
        return _stack(_title(name, dist), details)

    # Grid-method sessions (Pfitzinger/Hansons/Higdon): "<name> <total> mi w/ <work> @ <zone>"
    # and the plain general-aerobic / medium-long runs. Fold in the concrete pace.
    grid = _grid_card(name, dist, body, pace)
    if grid is not None:
        return grid

    # Plain easy run (and any other simple session): name + distance only.
    return _title(name, dist)
