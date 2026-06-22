"""Daniels training paces from VDOT, read straight from Table 5.2.

We use the book's printed values (engine/data/daniels_table_5_2.json) rather than a
%VO2max approximation: the approximation drifts up to ~15 s/mi on marathon pace, which
is too much for a prescribed pace. Fractional VDOT is linearly interpolated between the
two bracketing integer rows; VDOT outside the table range is clamped.

Paces are returned per mile. Easy/Long is a range; M and T are single values; Interval
is converted to a per-mile equivalent from the book's finest split (km, else 400 m).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "daniels_table_5_2.json"

METERS_PER_MILE = 1609.344


def _to_seconds(token: str | None) -> int | None:
    """'8:17' -> 497, '98' -> 98, '12:00' -> 720, '—'/'' -> None."""
    if not token or token == "\u2014":
        return None
    if ":" in token:
        m, s = token.split(":")
        return int(m) * 60 + int(s)
    return int(token) if token.isdigit() else None


def _fmt(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    m, s = divmod(round(seconds), 60)
    return f"{m}:{s:02d}"


@lru_cache(maxsize=1)
def _rows() -> dict[int, dict]:
    """VDOT -> per-mile pace seconds: easy_low/high, marathon, threshold, interval, rep."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    rows: dict[int, dict] = {}
    for vdot_s, cell in raw.items():
        low, _, high = cell["E_mile"].partition("-")
        # Interval per-mile from the finest available split (km preferred, then 400 m).
        i_km, i_400 = _to_seconds(cell.get("I_km")), _to_seconds(cell.get("I_400m"))
        if i_km is not None:
            interval = i_km * (METERS_PER_MILE / 1000)
        elif i_400 is not None:
            interval = i_400 * (METERS_PER_MILE / 400)
        else:
            interval = None
        # Repetition per-mile from the 400 m split (preferred), else the 200 m split.
        r_400, r_200 = _to_seconds(cell.get("R_400m")), _to_seconds(cell.get("R_200m"))
        if r_400 is not None:
            rep = r_400 * (METERS_PER_MILE / 400)
        elif r_200 is not None:
            rep = r_200 * (METERS_PER_MILE / 200)
        else:
            rep = None
        rows[int(vdot_s)] = {
            "easy_low": _to_seconds(low),
            "easy_high": _to_seconds(high),
            "marathon": _to_seconds(cell["M_mile"]),
            "threshold": _to_seconds(cell["T_mile"]),
            "interval": interval,
            "rep": rep,
        }
    return rows


# VDOT range covered by the encoded table.
def vdot_bounds() -> tuple[int, int]:
    keys = _rows().keys()
    return min(keys), max(keys)


def _interp(vdot: float, key: str) -> float | None:
    rows = _rows()
    lo, hi = vdot_bounds()
    v = max(lo, min(hi, vdot))
    low_v, high_v = int(v), min(int(v) + 1, hi)
    a, b = rows[low_v][key], rows[high_v][key]
    if a is None or b is None:
        return a if a is not None else b
    frac = v - low_v
    return a + (b - a) * frac


def _easy_midpoint_seconds(vdot: float) -> float:
    """Midpoint of Daniels easy range (easy_low / easy_high interpolated) in seconds per mile."""
    lo_s = _interp(vdot, "easy_low")
    hi_s = _interp(vdot, "easy_high")
    if lo_s is None or hi_s is None:
        raise ValueError("easy pace interpolation returned None for VDOT in range")
    return (lo_s + hi_s) / 2.0


def vdot_from_easy_pace(easy_pace_s: int) -> float:
    """VDOT whose Daniels easy-range midpoint matches ``easy_pace_s`` (seconds per mile).

    Uses the same fractional interpolation as :func:`training_paces`. Slower easy
    (higher seconds) implies lower VDOT. Values outside the feasible span of the
    encoded table clamp to the low or high VDOT bound.
    """
    if not isinstance(easy_pace_s, int) or easy_pace_s <= 0:
        raise ValueError("easy_pace_s must be a positive int (seconds per mile)")
    v_lo, v_hi = vdot_bounds()
    slow_lo = _easy_midpoint_seconds(float(v_lo))
    fast_hi = _easy_midpoint_seconds(float(v_hi))
    if easy_pace_s >= slow_lo:
        return float(v_lo)
    if easy_pace_s <= fast_hi:
        return float(v_hi)
    lo, hi = float(v_lo), float(v_hi)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        m = _easy_midpoint_seconds(mid)
        if m > float(easy_pace_s):
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 1)


def _round_or_none(seconds: float | None) -> int | None:
    return None if seconds is None else round(seconds)


def training_paces(vdot: float) -> dict:
    """Per-mile Daniels paces for a (possibly fractional) VDOT.

    Single-value zones carry both a formatted ``m:ss`` string and ``*_s`` seconds so
    callers (the plan engine) can do arithmetic on them; Easy is a low/high range.
    """
    easy_low, easy_high = _interp(vdot, "easy_low"), _interp(vdot, "easy_high")
    marathon, threshold = _interp(vdot, "marathon"), _interp(vdot, "threshold")
    interval, rep = _interp(vdot, "interval"), _interp(vdot, "rep")
    return {
        "vdot": round(vdot, 1),
        "easy": f"{_fmt(easy_low)}-{_fmt(easy_high)}",
        "easy_low_s": _round_or_none(easy_low),
        "easy_high_s": _round_or_none(easy_high),
        "marathon": _fmt(marathon),
        "marathon_s": _round_or_none(marathon),
        "threshold": _fmt(threshold),
        "threshold_s": _round_or_none(threshold),
        "interval": _fmt(interval),
        "interval_s": _round_or_none(interval),
        "rep": _fmt(rep),
        "rep_s": _round_or_none(rep),
    }


def daniels_paces(vdot: float) -> dict[str, str]:
    """Compatibility shape used by reports: {Easy, Marathon, Threshold, Interval, Repetition}.
    Easy is the book's range; the others are single per-mile paces."""
    p = training_paces(vdot)
    return {
        "Easy": p["easy"],
        "Marathon": p["marathon"],
        "Threshold": p["threshold"],
        "Interval": p["interval"],
        "Repetition": p["rep"],
    }
