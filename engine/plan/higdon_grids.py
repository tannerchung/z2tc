"""Algorithmic periodization generator for the Distance-Ladder (Higdon) paradigm.

Replaces verbatim string tables with parametric distance-ladder progression rules:
- Novice 1/2 (4 run days + 1 cross-training day): Tue/Thu short aerobic base (3 -> 5 mi),
  Wed midweek anchor (3 -> 10 mi Easy or MP), Sat Long Run ladder climbing to 20 mi
  with 3-week stepbacks and a mid-block Half Marathon tune-up.
- Intermediate 1/2 (5 run days + 1 cross-training day): Mon cross-training, Tue/Wed/Thu
  aerobic pyramid, Sat Marathon-Pace / Easy back-to-back pairing with Sun Long Run (to 20 mi).
"""

from __future__ import annotations

from .models import GridCell, WorkoutKind


def _rest() -> GridCell:
    return GridCell(WorkoutKind.REST, text="Rest")


def _cross() -> GridCell:
    return GridCell(WorkoutKind.CROSS, text="Cross training (60 min)")


def _easy(miles: float) -> GridCell:
    return GridCell(WorkoutKind.EASY, miles=float(miles), text=f"Easy {miles:g} mi run")


def _long(miles: float) -> GridCell:
    return GridCell(WorkoutKind.LONG, miles=float(miles), text=f"Long run {miles:g} mi")


def _mp(miles: float) -> GridCell:
    return GridCell(WorkoutKind.MARATHON_PACE, miles=float(miles), text=f"Marathon pace run {miles:g} mi")


def _hm() -> GridCell:
    return GridCell(WorkoutKind.RACE, miles=13.1, text="Half marathon (tune-up) — re-anchor VDOT after")


def _marathon() -> GridCell:
    return GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon")


def _generate_novice_1() -> list[list[GridCell]]:
    """Generate 18-week Novice 1 distance ladder via parametric stepback progression."""
    # (tue, wed, thu, sat_long_or_none_if_hm)
    ladder = [
        (3, 3, 3, 6),
        (3, 3, 3, 7),
        (3, 4, 3, 5),
        (3, 4, 3, 9),
        (3, 5, 3, 10),
        (3, 5, 3, 7),
        (3, 6, 3, 12),
        (3, 6, 3, None),  # Week 8: Half marathon tune-up on Sunday
        (3, 7, 4, 10),
        (3, 7, 4, 15),
        (4, 8, 4, 16),
        (4, 8, 5, 12),
        (4, 9, 5, 18),
        (5, 9, 5, 14),
        (5, 10, 5, 20),
        (5, 8, 4, 12),
        (4, 6, 3, 8),
    ]
    rows: list[list[GridCell]] = []
    for tue, wed, thu, sat_l in ladder:
        if sat_l is None:
            rows.append([_rest(), _easy(tue), _easy(wed), _easy(thu), _rest(), _rest(), _hm()])
        else:
            rows.append([_rest(), _easy(tue), _easy(wed), _easy(thu), _rest(), _long(sat_l), _cross()])
    rows.append([_rest(), _easy(3), _easy(4), _easy(2), _rest(), _rest(), _marathon()])
    return rows


def _generate_novice_2() -> list[list[GridCell]]:
    """Generate 18-week Novice 2 progression with midweek Marathon-Pace alternations."""
    # (tue, wed_mi, wed_is_mp, thu, sat_long, sun_kind)
    ladder = [
        (3, 5, True, 3, 8, "X"),
        (3, 5, False, 3, 9, "X"),
        (3, 5, True, 3, 6, "X"),
        (3, 6, True, 3, 11, "X"),
        (3, 6, False, 3, 12, "X"),
        (3, 6, True, 3, 9, "X"),
        (4, 7, True, 4, 14, "X"),
        (4, 7, False, 4, 15, "HM"),
        (4, 7, True, 4, None, "X"),
        (4, 8, True, 4, 17, "X"),
        (5, 8, False, 5, 18, "X"),
        (5, 8, True, 5, 13, "X"),
        (5, 5, True, 5, 19, "X"),
        (5, 8, False, 5, 12, "X"),
        (5, 5, True, 5, 20, "X"),
        (5, 4, True, 5, 12, "X"),
        (4, 3, False, 4, 8, "X"),
    ]
    rows: list[list[GridCell]] = []
    for tue, wed_mi, wed_mp, thu, sat_l, sun_k in ladder:
        wed_cell = _mp(wed_mi) if wed_mp else _easy(wed_mi)
        sat_cell = _rest() if sat_l is None else _long(sat_l)
        sun_cell = _hm() if sun_k == "HM" else _cross()
        rows.append([_rest(), _easy(tue), wed_cell, _easy(thu), _rest(), sat_cell, sun_cell])
    rows.append([_rest(), _easy(3), _easy(2), _rest(), _rest(), _easy(2), _marathon()])
    return rows


def _generate_intermediate(tier: int) -> list[list[GridCell]]:
    """Generate 18-week Intermediate 1 or 2 back-to-back weekend progression."""
    if tier == 1:
        spec = [
            (3, 5, 3, 5, True, 8),
            (3, 5, 3, 5, False, 9),
            (3, 5, 3, 5, True, 6),
            (3, 6, 3, 6, True, 11),
            (3, 6, 3, 6, False, 12),
            (3, 5, 3, 6, True, 9),
            (4, 7, 4, 7, True, 14),
            (4, 7, 4, 7, False, 15),
            (4, 5, 4, None, False, None),  # Week 9 HM
            (4, 8, 4, 8, True, 17),
            (5, 8, 5, 8, False, 18),
            (5, 5, 5, 8, True, 13),
            (5, 8, 5, 5, True, 20),
            (5, 5, 5, 8, False, 12),
            (5, 8, 5, 5, True, 20),
            (5, 6, 5, 4, True, 12),
            (4, 5, 4, 3, False, 8),
        ]
    else:
        spec = [
            (3, 5, 3, 5, True, 10),
            (3, 5, 3, 5, False, 11),
            (3, 6, 3, 6, True, 8),
            (3, 6, 3, 6, True, 13),
            (3, 7, 3, 7, False, 14),
            (3, 7, 3, 7, True, 10),
            (4, 8, 4, 8, True, 16),
            (4, 8, 4, 8, False, 17),
            (4, 9, 4, None, False, None),  # Week 9 HM
            (4, 9, 4, 9, True, 19),
            (5, 10, 5, 10, False, 20),
            (5, 6, 5, 6, True, 12),
            (5, 10, 5, 10, True, 20),
            (5, 6, 5, 6, False, 12),
            (5, 10, 5, 10, True, 20),
            (5, 8, 5, 4, True, 12),
            (4, 6, 4, 4, False, 8),
        ]
    rows: list[list[GridCell]] = []
    for tue, wed, thu, sat_mi, sat_mp, sun_l in spec:
        if sat_mi is None:
            rows.append([_cross(), _easy(tue), _easy(wed), _easy(thu), _rest(), _rest(), _hm()])
        else:
            sat_cell = _mp(sat_mi) if sat_mp else _easy(sat_mi)
            rows.append([_cross(), _easy(tue), _easy(wed), _easy(thu), _rest(), sat_cell, _long(sun_l)])
    rows.append([_cross(), _easy(3), _easy(4), _rest(), _rest(), _easy(2), _marathon()])
    return rows


PROGRAMS: dict[str, list[list[GridCell]]] = {
    "novice1": _generate_novice_1(),
    "novice2": _generate_novice_2(),
    "intermediate1": _generate_intermediate(1),
    "intermediate2": _generate_intermediate(2),
}
