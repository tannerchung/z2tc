"""Nutrition / hydration pointers (see books; verify quotes with ``scripts/book_search.py``).

Do **not** treat ``quote`` fields as verbatim until checked against the indexed PDFs.
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
        hint="Search: `python scripts/book_search.py search \"carbohydrate loading\" --book pfitz`",
    ),
    "higdon_fluid": NutritionNote(
        key="higdon_fluid",
        topic="hydration / sports drink",
        ref="Higdon, Marathon — ~p.80",
        hint="Search: `python scripts/book_search.py search \"sports drink\" --book higdon`",
    ),
    "hanson_race_fuel": NutritionNote(
        key="hanson_race_fuel",
        topic="race-week fueling",
        ref="Hansons Marathon Method — ~p.225",
        hint="Search: `python scripts/book_search.py search \"race day\" --book hanson`",
    ),
}


def all_notes() -> tuple[NutritionNote, ...]:
    return tuple(NUTRITION.values())
