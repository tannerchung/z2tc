"""Verbatim Hal Higdon marathon grids (miles), transcribed from halhigdon.com (2026).

Each row is Mon..Sun pipe-separated tokens:
  Rest, X (cross 60 min), E3 (easy 3 mi), L6 (long 6 mi), P5 (marathon pace 5 mi),
  Run5 (easy 5 mi \"run\"), HM (half tune-up), M (marathon race).
"""

from __future__ import annotations

NOVICE_1: tuple[str, ...] = (
    "Rest|E3|E3|E3|Rest|L6|X",
    "Rest|E3|E3|E3|Rest|L7|X",
    "Rest|E3|E4|E3|Rest|L5|X",
    "Rest|E3|E4|E3|Rest|L9|X",
    "Rest|E3|E5|E3|Rest|L10|X",
    "Rest|E3|E5|E3|Rest|L7|X",
    "Rest|E3|E6|E3|Rest|L12|X",
    "Rest|E3|E6|E3|Rest|Rest|HM",
    "Rest|E3|E7|E4|Rest|L10|X",
    "Rest|E3|E7|E4|Rest|L15|X",
    "Rest|E4|E8|E4|Rest|L16|X",
    "Rest|E4|E8|E5|Rest|L12|X",
    "Rest|E4|E9|E5|Rest|L18|X",
    "Rest|E5|E9|E5|Rest|L14|X",
    "Rest|E5|E10|E5|Rest|L20|X",
    "Rest|E5|E8|E4|Rest|L12|X",
    "Rest|E4|E6|E3|Rest|L8|X",
    "Rest|E3|E4|E2|Rest|Rest|M",
)

NOVICE_2: tuple[str, ...] = (
    "Rest|E3|P5|E3|Rest|L8|X",
    "Rest|E3|E5|E3|Rest|L9|X",
    "Rest|E3|P5|E3|Rest|L6|X",
    "Rest|E3|P6|E3|Rest|L11|X",
    "Rest|E3|E6|E3|Rest|L12|X",
    "Rest|E3|P6|E3|Rest|L9|X",
    "Rest|E4|P7|E4|Rest|L14|X",
    "Rest|E4|E7|E4|Rest|L15|HM",
    "Rest|E4|P7|E4|Rest|Rest|X",
    "Rest|E4|P8|E4|Rest|L17|X",
    "Rest|E5|E8|E5|Rest|L18|X",
    "Rest|E5|P8|E5|Rest|L13|X",
    "Rest|E5|P5|E5|Rest|L19|X",
    "Rest|E5|E8|E5|Rest|L12|X",
    "Rest|E5|P5|E5|Rest|L20|X",
    "Rest|E5|P4|E5|Rest|L12|X",
    "Rest|E4|E3|E4|Rest|L8|X",
    "Rest|E3|E2|Rest|Rest|Run2|M",
)

INTERMEDIATE_1: tuple[str, ...] = (
    "X|E3|E5|E3|Rest|P5|L8",
    "X|E3|E5|E3|Rest|Run5|L9",
    "X|E3|E5|E3|Rest|P5|L6",
    "X|E3|E6|E3|Rest|P6|L11",
    "X|E3|E6|E3|Rest|Run6|L12",
    "X|E3|E5|E3|Rest|P6|L9",
    "X|E4|E7|E4|Rest|P7|L14",
    "X|E4|E7|E4|Rest|Run7|L15",
    "X|E4|E5|E4|Rest|Rest|HM",
    "X|E4|E8|E4|Rest|P8|L17",
    "X|E5|E8|E5|Rest|Run8|L18",
    "X|E5|E5|E5|Rest|P8|L13",
    "X|E5|E8|E5|Rest|P5|L20",
    "X|E5|E5|E5|Rest|Run8|L12",
    "X|E5|E8|E5|Rest|P5|L20",
    "X|E5|E6|E5|Rest|P4|L12",
    "X|E4|E5|E4|Rest|Run3|L8",
    "X|E3|E4|Rest|Rest|Run2|M",
)

INTERMEDIATE_2: tuple[str, ...] = (
    "X|E3|E5|E3|Rest|P5|L10",
    "X|E3|E5|E3|Rest|Run5|L11",
    "X|E3|E6|E3|Rest|P6|L8",
    "X|E3|E6|E3|Rest|P6|L13",
    "X|E3|E7|E3|Rest|Run7|L14",
    "X|E3|E7|E3|Rest|P7|L10",
    "X|E4|E8|E4|Rest|P8|L16",
    "X|E4|E8|E4|Rest|Run8|L17",
    "X|E4|E9|E4|Rest|Rest|HM",
    "X|E4|E9|E4|Rest|P9|L19",
    "X|E5|E10|E5|Rest|Run10|L20",
    "X|E5|E6|E5|Rest|P6|L12",
    "X|E5|E10|E5|Rest|P10|L20",
    "X|E5|E6|E5|Rest|Run6|L12",
    "X|E5|E10|E5|Rest|P10|L20",
    "X|E5|E8|E5|Rest|P4|L12",
    "X|E4|E6|E4|Rest|Run4|L8",
    "X|E3|E4|Rest|Rest|Run2|M",
)

from .models import GridCell, WorkoutKind

def parse_token(tok: str) -> GridCell:
    t = tok.strip()
    if t == "Rest":
        return GridCell(WorkoutKind.REST, text="Rest")
    if t == "X":
        return GridCell(WorkoutKind.CROSS, text="Cross training (60 min)")
    if t == "HM":
        return GridCell(WorkoutKind.RACE, miles=13.1, text="Half marathon (tune-up) — re-anchor VDOT after")
    if t == "M":
        return GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon")
    if t.startswith("E"):
        mi = float(t[1:])
        return GridCell(WorkoutKind.EASY, miles=mi, text=f"Easy {mi:g} mi run")
    if t.startswith("L"):
        mi = float(t[1:])
        return GridCell(WorkoutKind.LONG, miles=mi, text=f"Long run {mi:g} mi")
    if t.startswith("P"):
        mi = float(t[1:])
        return GridCell(WorkoutKind.MARATHON_PACE, miles=mi, text=f"Marathon pace run {mi:g} mi")
    if t.startswith("Run"):
        mi = float(t[3:])
        return GridCell(WorkoutKind.EASY, miles=mi, text=f"Easy {mi:g} mi run")
    raise ValueError(f"Unknown Higdon token: {tok}")

def parse_grid(grid: tuple[str, ...]) -> list[list[GridCell]]:
    return [[parse_token(t) for t in row.split("|")] for row in grid]

PROGRAMS: dict[str, list[list[GridCell]]] = {
    "novice1": parse_grid(NOVICE_1),
    "novice2": parse_grid(NOVICE_2),
    "intermediate1": parse_grid(INTERMEDIATE_1),
    "intermediate2": parse_grid(INTERMEDIATE_2),
}
