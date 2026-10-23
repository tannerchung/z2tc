"""Training paces (E, M, T, I, R) computed continuously via Daniels & Gilbert (1979) equations.

Rather than loading a static JSON lookup table, this module evaluates the inverse of the
Daniels & Gilbert (1979) quadratic oxygen-cost equation:

    VO2(v) = -4.60 + 0.182258 * v + 0.000104 * v^2    (v in m/min)

at each training zone's physiological fraction of VO2max (%VO2max(VDOT)), and linearly
interpolates between integer VDOT anchors (30..85) for fractional VDOTs.
"""

from __future__ import annotations

import math
from functools import lru_cache

METERS_PER_MILE = 1609.344
VDOT_MIN = 30
VDOT_MAX = 85

# Continuous %VO2max(VDOT) polynomial coefficients on normalized domain x = (VDOT - 30) / 55,
# derived from the Daniels & Gilbert (1979) duration-intensity and running-economy curves:
#   - Easy (E):      ~63.0% to ~73.5% VO2max
#   - Marathon (M):  ~77.8% (at VDOT 30) to ~84.2% VO2max (at VDOT 85)
#   - Threshold (T): ~88.0% VO2max
#   - Interval (I):  ~97.5% VO2max
#   - Repetition (R): ~104.6% to ~111.5% VO2max (anaerobic economy / speed reps)
_PCT_VO2MAX_POLY: dict[str, tuple[float, ...]] = {
    "easy_low": (
        -0.491474970326,
        1.573509776617,
        -1.895664006450,
        1.041969312011,
        -0.255594899994,
        0.041824312891,
        0.723795458929,
    ),
    "easy_high": (
        0.650103604821,
        -1.877850026776,
        1.996181869280,
        -0.960420895853,
        0.225202490809,
        -0.037316744076,
        0.634661074266,
    ),
    "marathon": (
        0.938262886720,
        -2.889940984126,
        3.238703513851,
        -1.464841154430,
        0.088148675769,
        0.153931283985,
        0.777771263917,
    ),
    "threshold": (
        1.519393192607,
        -4.463497125585,
        4.828524430270,
        -2.265039616111,
        0.376695452720,
        0.004840624813,
        0.880495072701,
    ),
    "interval": (
        -2.717198563361,
        8.589157385861,
        -10.171445323145,
        5.526780260936,
        -1.342762182782,
        0.117748570534,
        0.972569141301,
    ),
    "rep": (
        4.517591942994,
        -14.550623961479,
        16.405304757449,
        -7.313173664007,
        0.840328459965,
        0.169086549941,
        1.046080781804,
    ),
}


def _eval_poly(coeffs: tuple[float, ...], x: float) -> float:
    acc = 0.0
    for c in coeffs:
        acc = acc * x + c
    return acc


def _velocity_m_per_min_from_vo2(vo2: float) -> float:
    """Positive root of Daniels & Gilbert (1979): 0.000104*v^2 + 0.182258*v - (4.60 + vo2) = 0."""
    a = 0.000104
    b = 0.182258
    c = -(4.60 + vo2)
    return (-b + math.sqrt(b * b - 4.0 * a * c)) / (2.0 * a)


def _sec_per_mile_from_equation(vdot: float, zone: str) -> float:
    x = (vdot - 30.0) / 55.0
    pct = _eval_poly(_PCT_VO2MAX_POLY[zone], x)
    v_m_per_min = _velocity_m_per_min_from_vo2(pct * vdot)
    return (METERS_PER_MILE / v_m_per_min) * 60.0


def _fmt_mmss(seconds: float) -> str:
    s = int(round(seconds))
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


@lru_cache(maxsize=1)
def _rows() -> dict[int, dict[str, float]]:
    """Compute integer VDOT pace rows (30..85) from the continuous Daniels-Gilbert equations."""
    out: dict[int, dict[str, float]] = {}
    for v in range(VDOT_MIN, VDOT_MAX + 1):
        vf = float(v)
        out[v] = {
            "easy_low": float(round(_sec_per_mile_from_equation(vf, "easy_low"))),
            "easy_high": float(round(_sec_per_mile_from_equation(vf, "easy_high"))),
            "marathon": float(round(_sec_per_mile_from_equation(vf, "marathon"))),
            "threshold": float(round(_sec_per_mile_from_equation(vf, "threshold"))),
            "interval": float(round(_sec_per_mile_from_equation(vf, "interval"))),
            "rep": float(round(_sec_per_mile_from_equation(vf, "rep"))),
        }
    return out


def vdot_bounds() -> tuple[int, int]:
    return VDOT_MIN, VDOT_MAX


def _interp(vdot: float, key: str) -> float:
    rows = _rows()
    lo_k, hi_k = vdot_bounds()
    v = max(float(lo_k), min(float(hi_k), float(vdot)))
    lo = int(math.floor(v))
    hi = int(math.ceil(v))
    a = rows[lo][key]
    b = rows[hi][key]
    if lo == hi:
        return a
    frac = v - lo
    return a + frac * (b - a)


def training_paces(vdot: float) -> dict:
    """Return per-mile paces for `vdot`, computed via Daniels-Gilbert (1979) equations.

    Keys:
      easy          "M:SS-M:SS" (faster–slower per-mile range)
      marathon      "M:SS"
      threshold     "M:SS"
      interval      "M:SS"
      rep           "M:SS"
      easy_low_s, easy_high_s, marathon_s, threshold_s, interval_s, rep_s  (int seconds/mi)
    """
    e_lo = _interp(vdot, "easy_low")
    e_hi = _interp(vdot, "easy_high")
    m = _interp(vdot, "marathon")
    t = _interp(vdot, "threshold")
    i = _interp(vdot, "interval")
    r = _interp(vdot, "rep")

    e_lo_i = int(round(e_lo)) if e_lo is not None else None
    e_hi_i = int(round(e_hi)) if e_hi is not None else None
    m_i = int(round(m)) if m is not None else None
    t_i = int(round(t)) if t is not None else None
    i_i = int(round(i)) if i is not None else None
    r_i = int(round(r)) if r is not None else None

    return {
        "easy": f"{_fmt_mmss(e_lo)}-{_fmt_mmss(e_hi)}",
        "marathon": _fmt_mmss(m),
        "threshold": _fmt_mmss(t),
        "interval": _fmt_mmss(i),
        "rep": _fmt_mmss(r) if r is not None else None,
        "easy_low_s": e_lo_i,
        "easy_high_s": e_hi_i,
        "marathon_s": m_i,
        "threshold_s": t_i,
        "interval_s": i_i,
        "rep_s": r_i,
    }


def vdot_from_easy_pace(easy_pace_s_per_mi: int) -> float:
    """Invert easy-zone midpoint (seconds/mile) -> VDOT (1 decimal), clamped to bounds."""
    rows = _rows()
    lo_k, hi_k = vdot_bounds()
    pts: list[tuple[int, float]] = []
    for k in range(lo_k, hi_k + 1):
        el, eh = rows[k]["easy_low"], rows[k]["easy_high"]
        if el is not None and eh is not None:
            pts.append((k, 0.5 * (float(el) + float(eh))))
    s = float(easy_pace_s_per_mi)
    if s >= pts[0][1]:
        return float(pts[0][0])
    if s <= pts[-1][1]:
        return float(pts[-1][0])
    for idx in range(len(pts) - 1):
        v0, m0 = pts[idx]
        v1, m1 = pts[idx + 1]
        if m0 >= s >= m1:
            t = (m0 - s) / (m0 - m1) if m0 != m1 else 0.0
            return round(v0 + t * (v1 - v0), 1)
    return float(lo_k)


def daniels_paces(vdot: float) -> dict[str, str | None]:
    """Compatibility shape used by reports: {Easy, Marathon, Threshold, Interval, Repetition}."""
    p = training_paces(vdot)
    return {
        "Easy": p["easy"],
        "Marathon": p["marathon"],
        "Threshold": p["threshold"],
        "Interval": p["interval"],
        "Repetition": p["rep"],
    }
