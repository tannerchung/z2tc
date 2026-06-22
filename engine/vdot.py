"""VDOT from a race performance, and selecting the most appropriate race for a plan.

VDOT uses Jack Daniels' formula (validated against Table 5.1 to within ~0.1 VDOT across
5K--marathon); paces for the chosen VDOT come from the table-backed ``paces`` module.
"""

from __future__ import annotations

import math

from .paces import daniels_paces

# Official distances in meters for VDOT (use these, not noisy GPS distance).
RACE_METERS = {"5K": 5000.0, "10K": 10000.0, "Half Marathon": 21097.5, "Marathon": 42195.0}


def _vdot_for_velocity(distance_m: float, t_min: float) -> float:
    """Daniels' VDOT for covering ``distance_m`` in ``t_min`` minutes (raw, unrounded).

    Forward model (Daniels' Running Formula, 3rd ed., app. via the standard fit):
    a velocity→VO2 cost curve divided by the fraction of VDOT sustainable for that
    duration. Shared by ``vdot_from_race`` (measured race → VDOT) and
    ``predict_race_time`` (VDOT → predicted race time, its inverse).
    """
    v = distance_m / t_min  # m/min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(
        -0.1932605 * t_min
    )
    return vo2 / pct


def vdot_from_race(distance_m: float, time_s: float) -> float | None:
    """Jack Daniels' VDOT from a race distance (m) and time (s)."""
    if not distance_m or not time_s:
        return None
    return round(_vdot_for_velocity(distance_m, time_s / 60.0), 1)


def predict_race_time(vdot: float, distance_m: float) -> int | None:
    """Predicted race time (seconds) at ``distance_m`` for a given VDOT — the inverse of
    ``vdot_from_race``.

    VDOT decreases monotonically as time rises (same distance), so we bisect on time.
    This is the "equivalent race performances across distances" idea behind Daniels'
    VDOT tables (Table 5.1, *Daniels' Running Formula* 3rd ed.): one VDOT maps to a full
    set of race times.
    """
    if not vdot or vdot <= 0 or not distance_m or distance_m <= 0:
        return None
    lo, hi = 2.0, 600.0  # minutes; brackets 5K..marathon for any realistic VDOT
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _vdot_for_velocity(distance_m, mid) > vdot:
            lo = mid  # too fast (VDOT too high) -> allow more time
        else:
            hi = mid
    return round((lo + hi) / 2.0 * 60.0)


def race_equivalent_times(vdot: float) -> dict[str, int]:
    """Equivalent race times (seconds) at each standard distance for a VDOT.

    Lets the coach answer "what does this fitness predict across distances?" — e.g. turn a
    half result into a realistic marathon estimate (``RACE_METERS["Marathon"]``).
    """
    out: dict[str, int] = {}
    for label, meters in RACE_METERS.items():
        t = predict_race_time(vdot, meters)
        if t is not None:
            out[label] = t
    return out


# Most appropriate race for marathon-plan VDOT: a recent half is the gold standard,
# then 10K, 5K; the marathon itself last (long races under-predict via this model).
_VDOT_PREFERENCE = ["Half Marathon", "10K", "5K", "Marathon"]


def recommended_vdot(races: list[dict]) -> dict | None:
    """Pick the most appropriate race for a marathon plan and compute VDOT + paces.
    Within a preferred distance, use the fastest performance."""
    by_cat: dict[str, dict] = {}
    for r in races:
        cat = r.get("category")
        meters = RACE_METERS.get(cat)
        vd = vdot_from_race(meters, r.get("duration_s"))
        if vd is None:
            continue
        r = {**r, "vdot": vd}
        if cat not in by_cat or vd > by_cat[cat]["vdot"]:
            by_cat[cat] = r
    for cat in _VDOT_PREFERENCE:
        if cat in by_cat:
            chosen = by_cat[cat]
            return {
                "source_race": chosen,
                "vdot": chosen["vdot"],
                "training_paces": daniels_paces(chosen["vdot"]),
            }
    return None
