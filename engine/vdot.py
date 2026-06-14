"""VDOT from a race performance, and selecting the most appropriate race for a plan.

VDOT uses Jack Daniels' formula (validated against Table 5.1 to within ~0.1 VDOT across
5K--marathon); paces for the chosen VDOT come from the table-backed ``paces`` module.
"""

from __future__ import annotations

import math

from .paces import daniels_paces

# Official distances in meters for VDOT (use these, not noisy GPS distance).
RACE_METERS = {"5K": 5000.0, "10K": 10000.0, "Half Marathon": 21097.5, "Marathon": 42195.0}


def vdot_from_race(distance_m: float, time_s: float) -> float | None:
    """Jack Daniels' VDOT from a race distance (m) and time (s)."""
    if not distance_m or not time_s:
        return None
    t = time_s / 60.0
    v = distance_m / t  # m/min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(
        -0.1932605 * t
    )
    return round(vo2 / pct, 1)


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
