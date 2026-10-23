"""Nutrition / hydration pointers for marathon blocks.

Provides evidence-based fueling and hydration guidance references.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NutritionNote:
    key: str
    topic: str
    ref: str
    hint: str


NUTRITION: dict[str, NutritionNote] = {
    "pfitz_carb": NutritionNote(
        key="pfitz_carb",
        topic="carbohydrate loading & race fueling",
        ref="Pfitzinger & Douglas, Advanced Marathoning — ch.2",
        hint="Target 8-10 g/kg carbohydrate 48-72h pre-race; 60-90g/hr exogenous carbs during race.",
    ),
    "higdon_fluid": NutritionNote(
        key="higdon_fluid",
        topic="hydration / sports drink",
        ref="Higdon, Marathon — ~p.80",
        hint="Practice race-day electrolyte and fluid intake on all long runs >90 minutes.",
    ),
    "hanson_race_fuel": NutritionNote(
        key="hanson_race_fuel",
        topic="race-week fueling",
        ref="Hansons Marathon Method — ~p.225",
        hint="Increase carbohydrate percentage over final 3 days while tapering fiber and fat.",
    ),
}


def all_notes() -> tuple[NutritionNote, ...]:
    return tuple(NUTRITION.values())
