"""Verbatim Hansons Marathon Method ch.4 — 18-wk daily grids.

Transcribed day-by-day from Hansons Marathon Method pp.124–126 (Tables 4.2–4.4).
"""

from __future__ import annotations

from .models import GridCell, WorkoutKind

# 18-wk weekly totals (mi) for Just Finish / Beginner / Advanced (as reference).
JUST_FINISH_18WK_MI: tuple[float, ...] = (
    12.0, 16.0, 21.0, 20.0, 24.0, 34.0,
    34.0, 39.0, 41.0, 41.0, 47.0, 41.0,
    45.0, 41.0, 45.0, 38.0, 37.0, 48.2,
)

BEGINNER_18WK_MI: tuple[float, ...] = (
    10.0, 15.0, 21.0, 21.0, 24.0, 39.0,
    38.0, 41.0, 47.0, 46.0, 54.0, 49.0,
    56.0, 49.0, 57.0, 50.0, 49.0, 50.0,
)

ADVANCED_18WK_MI: tuple[float, ...] = (
    26.0, 41.0, 46.0, 45.0, 47.0, 47.0,
    54.0, 49.0, 57.0, 51.0, 59.0, 54.0,
    61.0, 54.0, 62.0, 55.0, 52.0, 52.0,
)


JUST_FINISH_GRID: tuple[str, ...] = (
    "—|Easy 2 mi.|—|Easy 3 mi.|—|Easy 3 mi.|Easy 4 mi.",
    "—|Easy 3 mi.|—|Easy 3 mi.|Easy 3 mi.|Easy 3 mi.|Easy 4 mi.",
    "—|Easy 4 mi.|—|Easy 4 mi.|Easy 4 mi.|Easy 4 mi.|Easy 5 mi.",
    "—|Easy 5 mi.|—|Easy 3 mi.|Easy 3 mi.|Easy 5 mi.|Easy 4 mi.",
    "—|Easy 5 mi.|—|Easy 4 mi.|Easy 5 mi.|Easy 4 mi.|Easy 6 mi.",
    "Easy 4 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 4 mi.|Easy 8 mi.|Easy 8 mi.",
    "Easy 4 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 4 mi.|Easy 6 mi.|Long 10 mi.",
    "Easy 6 mi.|Easy 6 mi.|—|Easy 6 mi.|Easy 5 mi.|Easy 6 mi.|Long 10 mi.",
    "Easy 5 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 6 mi.|Easy 5 mi.|Long 15 mi.",
    "Easy 7 mi.|Easy 5 mi.|—|Easy 6 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 5 mi.|Easy 7 mi.|—|Easy 5 mi.|Easy 6 mi.|Easy 8 mi.|Easy 16 mi.",
    "Easy 5 mi.|Easy 7 mi.|—|Easy 6 mi.|Easy 5 mi.|Easy 8 mi.|Easy 10 mi.",
    "Easy 7 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 6 mi.|Easy 6 mi.|Long 16 mi.",
    "Easy 5 mi.|Easy 7 mi.|—|Easy 6 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 7 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 6 mi.|Easy 6 mi.|Long 16 mi.",
    "Easy 5 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 7 mi.|Easy 5 mi.|—|Easy 5 mi.|Easy 6 mi.|Easy 6 mi.|Easy 8 mi.",
    "Easy 5 mi.|Easy 5 mi.|Rest|Easy 5 mi.|Easy 4 mi.|Easy 3 mi.|RACE!",
)

BEGINNER_GRID: tuple[str, ...] = (
    "—|—|OFF|Easy 3 mi.|OFF|Easy 3 mi.|Easy 4 mi.",
    "OFF|Easy 2 mi.|OFF|Easy 3 mi.|Easy 3 mi.|Easy 3 mi.|Easy 4 mi.",
    "OFF|Easy 4 mi.|OFF|Easy 4 mi.|Easy 4 mi.|Easy 4 mi.|Easy 5 mi.",
    "OFF|Easy 5 mi.|OFF|Easy 3 mi.|Easy 3 mi.|Easy 5 mi.|Easy 5 mi.",
    "OFF|Easy 5 mi.|OFF|Easy 4 mi.|Easy 5 mi.|Easy 4 mi.|Easy 6 mi.",
    "Easy 4 mi.|SPEED: 12 × 400 / 400 recovery|OFF|TEMPO: 5 mi.|Easy 4 mi.|Easy 8 mi.|Easy 8 mi.",
    "Easy 4 mi.|SPEED: 8 × 600 / 400 recovery|OFF|TEMPO: 5 mi.|Easy 4 mi.|Easy 6 mi.|Long 10 mi.",
    "Easy 6 mi.|SPEED: 6 × 800 / 400 recovery|OFF|TEMPO: 5 mi.|Easy 5 mi.|Easy 6 mi.|Long 10 mi.",
    "Easy 5 mi.|SPEED: 5 × 1K / 400 recovery|OFF|TEMPO: 8 mi.|Easy 6 mi.|Easy 5 mi.|Long 15 mi.",
    "Easy 7 mi.|SPEED: 4 × 1200 / 400 recovery|OFF|TEMPO: 8 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 5 mi.|STRENGTH: 6 × 1 mi. / 400 recovery|OFF|TEMPO: 8 mi.|Easy 5 mi.|Easy 8 mi.|Long 16 mi.",
    "Easy 5 mi.|STRENGTH: 4 × 1.5 mi. / 800 recovery|OFF|TEMPO: 9 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 7 mi.|STRENGTH: 3 × 2 mi. / 800 recovery|OFF|TEMPO: 9 mi.|Easy 6 mi.|Easy 6 mi.|Long 16 mi.",
    "Easy 5 mi.|STRENGTH: 2 × 3 mi. / 1-mi. recovery|OFF|TEMPO: 9 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 7 mi.|STRENGTH: 3 × 2 mi. / 800 recovery|OFF|TEMPO: 10 mi.|Easy 6 mi.|Easy 6 mi.|Long 16 mi.",
    "Easy 5 mi.|STRENGTH: 4 × 1.5 mi. / 800 recovery|OFF|TEMPO: 10 mi.|Easy 5 mi.|Easy 8 mi.|Long 10 mi.",
    "Easy 7 mi.|STRENGTH: 6 × 1 mi. / 400 recovery|OFF|TEMPO: 10 mi.|Easy 6 mi.|Easy 6 mi.|Easy 8 mi.",
    "Easy 5 mi.|Easy 5 mi.|OFF|Easy 6 mi.|Easy 5 mi.|Easy 3 mi.|RACE!",
)

ADVANCED_GRID: tuple[str, ...] = (
    "—|—|OFF|Easy 6 mi.|Easy 6 mi.|Easy 6 mi.|Easy 8 mi.",
    "Easy 6 mi.|SPEED: 12 × 400 / 400 recovery|OFF|Easy 6 mi.|Easy 6 mi.|Easy 6 mi.|Easy 8 mi.",
    "Easy 6 mi.|SPEED: 8 × 600 / 400 recovery|OFF|TEMPO: 6 mi.|Easy 7 mi.|Easy 6 mi.|Long 10 mi.",
    "Easy 6 mi.|SPEED: 6 × 800 / 400 recovery|OFF|TEMPO: 6 mi.|Easy 6 mi.|Easy 8 mi.|Easy 8 mi.",
    "Easy 6 mi.|SPEED: 5 × 1 km / 400 recovery|OFF|TEMPO: 6 mi.|Easy 7 mi.|Easy 6 mi.|Long 12 mi.",
    "Easy 6 mi.|SPEED: 4 × 1200 / 400 recovery|OFF|TEMPO: 7 mi.|Easy 6 mi.|Easy 10 mi.|Easy 8 mi.",
    "Easy 6 mi.|SPEED: 400-800-1200-1600-1200-800 / 400 recovery|OFF|TEMPO: 7 mi.|Easy 7 mi.|Easy 8 mi.|Long 14 mi.",
    "Easy 6 mi.|SPEED: 3 × 1600 / 600 recovery|OFF|TEMPO: 7 mi.|Easy 6 mi.|Easy 10 mi.|Easy 10 mi.",
    "Easy 8 mi.|SPEED: 6 × 800 / 400 recovery|OFF|TEMPO: 8 mi.|Easy 7 mi.|Easy 8 mi.|Long 15 mi.",
    "Easy 8 mi.|SPEED: 4 × 1200 / 400 recovery|OFF|TEMPO: 8 mi.|Easy 7 mi.|Easy 10 mi.|Long 10 mi.",
    "Easy 8 mi.|STRENGTH: 6 × 1 mi. / 400 recovery|OFF|TEMPO: 8 mi.|Easy 7 mi.|Easy 10 mi.|Long 16 mi.",
    "Easy 8 mi.|STRENGTH: 4 × 1.5 mi. / 800 recovery|OFF|TEMPO: 9 mi.|Easy 7 mi.|Easy 10 mi.|Long 10 mi.",
    "Easy 8 mi.|STRENGTH: 3 × 2 mi. / 800 recovery|OFF|TEMPO: 9 mi.|Easy 8 mi.|Easy 8 mi.|Long 16 mi.",
    "Easy 8 mi.|STRENGTH: 2 × 3 mi. / 1-mi. recovery|OFF|TEMPO: 9 mi.|Easy 7 mi.|Easy 10 mi.|Long 10 mi.",
    "Easy 8 mi.|STRENGTH: 3 × 2 mi. / 800 recovery|OFF|TEMPO: 10 mi.|Easy 8 mi.|Easy 8 mi.|Long 16 mi.",
    "Easy 8 mi.|STRENGTH: 4 × 1.5 mi. / 800 recovery|OFF|TEMPO: 10 mi.|Easy 7 mi.|Easy 10 mi.|Long 10 mi.",
    "Easy 8 mi.|STRENGTH: 6 × 1 mi. / 400 recovery|OFF|TEMPO: 10 mi.|Easy 8 mi.|Easy 8 mi.|Easy 8 mi.",
    "Easy 6 mi.|Easy 6 mi.|OFF|Easy 6 mi.|Easy 5 mi.|Easy 3 mi.|RACE!",
)


def parse_token(tok: str) -> GridCell:
    t = tok.strip()
    if t in ("", "—", "OFF", "Rest"):
        return GridCell(WorkoutKind.REST, text="Rest")
    if t == "RACE!":
        return GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon")
    
    t_lower = t.lower()
    if t_lower.startswith("easy"):
        parts = t.split()
        mi = float(parts[1])
        return GridCell(WorkoutKind.EASY, miles=mi, text=f"Easy {mi:g} mi run")
    if t_lower.startswith("long"):
        parts = t.split()
        mi = float(parts[1])
        return GridCell(WorkoutKind.LONG, miles=mi, text=f"Long run {mi:g} mi")
    if t_lower.startswith("tempo"):
        parts = t.split()
        mi = float(parts[1].replace(":", ""))
        return GridCell(WorkoutKind.MARATHON_PACE, miles=mi, text=f"Tempo run {mi:g} mi @ goal MP")
    if t_lower.startswith("speed:"):
        desc = t[6:].strip()
        hints = []
        if "12 × 400" in desc or "12 x 400" in desc:
            hints = [{"reps": 12, "pace_label": "I", "distance_m": 400.0, "recovery": "400m jog"}]
        elif "8 × 600" in desc or "8 x 600" in desc:
            hints = [{"reps": 8, "pace_label": "I", "distance_m": 600.0, "recovery": "400m jog"}]
        elif "6 × 800" in desc or "6 x 800" in desc:
            hints = [{"reps": 6, "pace_label": "I", "distance_m": 800.0, "recovery": "400m jog"}]
        elif "5 × 1" in desc or "5 x 1" in desc:
            hints = [{"reps": 5, "pace_label": "I", "distance_m": 1000.0, "recovery": "400m jog"}]
        elif "4 × 1200" in desc or "4 x 1200" in desc:
            hints = [{"reps": 4, "pace_label": "I", "distance_m": 1200.0, "recovery": "400m jog"}]
        elif "3 × 1600" in desc or "3 x 1600" in desc:
            hints = [{"reps": 3, "pace_label": "I", "distance_m": 1600.0, "recovery": "600m jog"}]
        elif "400-800" in desc:
            hints = [
                {"reps": 1, "pace_label": "I", "distance_m": 400.0, "recovery": "400m jog"},
                {"reps": 1, "pace_label": "I", "distance_m": 800.0, "recovery": "400m jog"},
                {"reps": 1, "pace_label": "I", "distance_m": 1200.0, "recovery": "400m jog"},
                {"reps": 1, "pace_label": "I", "distance_m": 1600.0, "recovery": "400m jog"},
                {"reps": 1, "pace_label": "I", "distance_m": 1200.0, "recovery": "400m jog"},
                {"reps": 1, "pace_label": "I", "distance_m": 800.0, "recovery": "400m jog"},
            ]
        return GridCell(WorkoutKind.INTERVAL, text=t, segment_hints=hints)
    if t_lower.startswith("strength:"):
        desc = t[9:].strip()
        hints = []
        if "6 × 1 mi" in desc or "6 x 1 mi" in desc:
            hints = [{"reps": 6, "pace_label": "T", "distance_m": 1609.344, "recovery": "400m jog"}]
        elif "4 × 1.5 mi" in desc or "4 x 1.5 mi" in desc:
            hints = [{"reps": 4, "pace_label": "T", "distance_m": 2414.016, "recovery": "800m jog"}]
        elif "3 × 2 mi" in desc or "3 x 2 mi" in desc:
            hints = [{"reps": 3, "pace_label": "T", "distance_m": 3218.688, "recovery": "800m jog"}]
        elif "2 × 3 mi" in desc or "2 x 3 mi" in desc:
            hints = [{"reps": 2, "pace_label": "T", "distance_m": 4828.032, "recovery": "1 mi jog"}]
        return GridCell(WorkoutKind.THRESHOLD, text=t, segment_hints=hints)
    
    raise ValueError(f"Unknown Hanson token: {tok}")


def parse_grid(grid: tuple[str, ...]) -> list[list[GridCell]]:
    return [[parse_token(t) for t in row.split("|")] for row in grid]


PROGRAMS: dict[str, list[list[GridCell]]] = {
    "just_finish": parse_grid(JUST_FINISH_GRID),
    "beginner": parse_grid(BEGINNER_GRID),
    "advanced": parse_grid(ADVANCED_GRID),
}
