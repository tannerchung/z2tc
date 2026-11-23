"""Marathon long-run fueling & hydration prescription.

Pure rules from Burke/Jeukendrup (2011, 2014) carbohydrate guidelines,
ACSM fluid replacement guidelines, and Detour's structured fuel catalog
(`fuel_catalog.json`) so long runs prescribe exact packet timing and water
pairing based on each athlete's preferred gel and stomach comfort profile.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import AthleteInputs, NutritionGuidance

_CATALOG_PATH = Path(__file__).with_name("fuel_catalog.json")


def _lookup_fuel_spec(preferred_gel: str | None) -> dict:
    """Resolve an athlete's preferred gel string to carb/water/hydrogel specs."""
    default = {
        "name": "Standard Gel (25g)",
        "carbs_g": 25,
        "water_required_ml": 150,
        "is_hydrogel": False,
        "is_isotonic": False,
    }
    if not preferred_gel:
        return default
    q = preferred_gel.lower()
    if _CATALOG_PATH.exists():
        try:
            data = json.loads(_CATALOG_PATH.read_text())
            for item in data.get("core_fuels", []):
                item_name = (item.get("name", "") + " " + item.get("id", "")).lower()
                if item["id"] in q or item.get("name", "").lower() in q or item.get("brand", "").lower() in q:
                    # Disambiguate Maurten 160 vs 100
                    if "160" in q and "160" not in item["id"]:
                        continue
                    if "caf" in q and "caf" not in item["id"] and item.get("brand") == "Maurten":
                        continue
                    return item
        except Exception:
            pass
    # Fallback heuristics
    if "160" in q or "beta fuel" in q:
        return {"name": preferred_gel, "carbs_g": 40, "water_required_ml": 200, "is_hydrogel": "maurten" in q, "is_isotonic": False}
    if "pf 30" in q or "precision" in q or "neversecond" in q or "c30" in q:
        return {"name": preferred_gel, "carbs_g": 30, "water_required_ml": 120, "is_hydrogel": False, "is_isotonic": "c30" in q}
    if "sis" in q or "isotonic" in q:
        return {"name": preferred_gel, "carbs_g": 22, "water_required_ml": 0, "is_hydrogel": False, "is_isotonic": True}
    if "huma" in q or "gu" in q or "bpn" in q:
        return {"name": preferred_gel, "carbs_g": 22, "water_required_ml": 180, "is_hydrogel": False, "is_isotonic": False}
    return default


def _hydration_targets(athlete: AthleteInputs) -> tuple[tuple[int, int], tuple[int, int], str]:
    """Compute informal (fluid_ml_per_hr, sodium_mg_per_hr, weather_hint) from sweat tier + temp."""
    fluid = (450, 800)
    sodium = (400, 800)
    hints: list[str] = []

    if athlete.enable_hydration_weather:
        temp = athlete.ambient_temp_f
        dew = athlete.ambient_dew_point_f
        if (temp is not None and temp >= 68.0) or (dew is not None and dew >= 60.0):
            fluid = (700, 1000)
            sodium = (600, 950)
            hints.append("warm/humid forecast: carry extra handheld or hit every park fountain")
        elif temp is not None and temp < 48.0:
            fluid = (400, 600)

        tier = (athlete.sweat_sodium_tier or "").lower()
        if tier == "salty":
            sodium = (max(sodium[0], 800), max(sodium[1], 1200))
            hints.append("salty-sweater profile: pre-load ~500mg sodium in 16oz water 60-90m pre-run")
        elif tier == "low":
            sodium = (300, 550)

        if athlete.sweat_rate_ml_per_hr:
            lo = int(round(athlete.sweat_rate_ml_per_hr * 0.65, -1))
            hi = int(round(athlete.sweat_rate_ml_per_hr * 0.85, -1))
            fluid = (max(350, lo), min(1200, max(lo + 100, hi)))

    suffix = f" ({'; '.join(hints)})" if hints else ""
    return fluid, sodium, suffix


def nutrition_for_long_run(
    duration_min: float,
    athlete: AthleteInputs,
) -> NutritionGuidance | None:
    """Return fuel/fluid target for a long run of `duration_min` minutes.

    Returns None when the run is short enough (<60 min) that water-only suffices.
    """
    if duration_min < 60:
        return None

    spec = _lookup_fuel_spec(athlete.preferred_gel)
    gel_name = spec.get("name", "Gel")
    gel_carbs = spec.get("carbs_g", 25)
    water_per_gel = spec.get("water_required_ml", 150)
    comfort = (athlete.fuel_comfort_profile or "").lower()
    sensitive_gut = "gradual" in comfort or "sensitive" in comfort
    gi_stepdown = (athlete.last_gi_distress_score or 0) >= 3

    if duration_min < 75:
        carbs = (20, 30)
        note = "Mouth rinse or 1 gel at 45 min if finishing hard."
    elif duration_min < 120:
        carbs = (30, 50) if sensitive_gut else (30, 60)
        interval_min = int(round((gel_carbs / 45.0) * 60))
        interval_min = max(25, min(35, interval_min))
        note = (
            f"1× {gel_name} ({gel_carbs}g) every ~{interval_min} min starting at 30 min. "
            f"Chase each non-isotonic gel with ~{water_per_gel}mL plain water (never sports drink)"
            f" to prevent gut hyperosmolarity."
        )
    elif duration_min < 150:
        carbs = (50, 70) if sensitive_gut else (60, 80)
        interval_min = int(round((gel_carbs / 65.0) * 60))
        interval_min = max(20, min(35, interval_min))
        note = (
            f"Race-rehearsal fueling: {gel_name} ({gel_carbs}g) every ~{interval_min} min from 25 min. "
            f"Pair every gel with {water_per_gel}mL plain water at fountains/stations—skipping water"
            f" slows gastric emptying and triggers Mile 18 hunger dips."
        )
    else:
        carbs = (60, 75) if sensitive_gut else (65, 90)
        interval_min = int(round((gel_carbs / 75.0) * 60))
        interval_min = max(20, min(32, interval_min))
        note = (
            f"Full marathon gut rehearsal ({carbs[0]}–{carbs[1]}g/hr): {gel_name} ({gel_carbs}g)"
            f" every ~{interval_min} min on a strict watch timer through the final 20 min. "
            f"Optional pre-load: Maurten 320 (80g in 500mL water) night before / morning of."
        )

    if gi_stepdown and duration_min >= 75:
        carbs = (max(25, carbs[0] - 10), max(35, carbs[1] - 10))
        note += " [Gut step-down: eased target by ~10g/hr after prior GI distress — sip plain water with every gel.]"

    fluid, sodium, weather_suffix = _hydration_targets(athlete)
    if weather_suffix:
        note += weather_suffix

    return NutritionGuidance(
        carbs_g_per_hr=carbs,
        fluid_ml_per_hr=fluid,
        sodium_mg_per_hr=sodium,
        notes=note,
    )