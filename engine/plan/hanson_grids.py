"""Algorithmic periodization generator for the Cumulative Fatigue (6-Day) paradigm.

Replaces verbatim book string tables with parametric equations:
- Tuesday SOS 1: Speed phase (3 miles / 4,800 m total at 5K-10K / I-pace: 12x400, 8x600,
  6x800, 5x1K, 4x1200, 3x1600, or ladder) transitioning in Week 11 to Strength phase
  (6 miles total at MP - 10s/mi / T-pace: 6x1 mi, 4x1.5 mi, 3x2 mi, 2x3 mi).
- Wednesday: Fixed midweek off/recovery anchor.
- Thursday SOS 2: Continuous goal Marathon-Pace (MP) Tempo stepping from 5 -> 8 -> 9 -> 10 mi.
- Sunday Endurance Anchor: Alternating 16-mile peak / 10-mile recovery waves.
"""

from __future__ import annotations

from .models import GridCell, WorkoutKind


def _speed_workout(reps: int, dist_m: int, rec_m: int = 400, unit_label: str | None = None) -> GridCell:
    u = unit_label or str(dist_m)
    return GridCell(
        WorkoutKind.INTERVAL,
        text=f"SPEED: {reps} × {u} / {rec_m} recovery",
        segment_hints=[{"reps": reps, "pace_label": "I", "distance_m": float(dist_m), "recovery": f"{rec_m}m jog"}],
    )


def _speed_ladder() -> GridCell:
    dists = [400.0, 800.0, 1200.0, 1600.0, 1200.0, 800.0]
    return GridCell(
        WorkoutKind.INTERVAL,
        text="SPEED: 400-800-1200-1600-1200-800 / 400 recovery",
        segment_hints=[{"reps": 1, "pace_label": "I", "distance_m": d, "recovery": "400m jog"} for d in dists],
    )


def _strength_workout(reps: int, miles_each: float) -> GridCell:
    rec_str = "400 recovery" if miles_each == 1.0 else ("1-mi. recovery" if miles_each == 3.0 else "800 recovery")
    rec_hint = "400m jog" if miles_each == 1.0 else ("1 mi jog" if miles_each == 3.0 else "800m jog")
    mi_str = f"{miles_each:g}"
    return GridCell(
        WorkoutKind.THRESHOLD,
        text=f"STRENGTH: {reps} × {mi_str} mi. / {rec_str}",
        segment_hints=[{"reps": reps, "pace_label": "T", "distance_m": round(miles_each * 1609.344, 3), "recovery": rec_hint}],
    )


def _tempo(miles: float) -> GridCell:
    return GridCell(WorkoutKind.MARATHON_PACE, miles=float(miles), text=f"Tempo run {miles:g} mi @ goal MP")


def _easy(miles: float) -> GridCell:
    return GridCell(WorkoutKind.EASY, miles=float(miles), text=f"Easy {miles:g} mi run")


def _long(miles: float) -> GridCell:
    return GridCell(WorkoutKind.LONG, miles=float(miles), text=f"Long run {miles:g} mi")


def _rest() -> GridCell:
    return GridCell(WorkoutKind.REST, text="Rest")


def _race() -> GridCell:
    return GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon")


# Strength progression cycle (Weeks 11..17: 6 miles total work volume at MP-10s)
_STRENGTH_ROTATION: tuple[tuple[int, float], ...] = (
    (6, 1.0),
    (4, 1.5),
    (3, 2.0),
    (2, 3.0),
    (3, 2.0),
    (4, 1.5),
    (6, 1.0),
)


def _generate_just_finish() -> list[list[GridCell]]:
    """Generate the 18-week aerobic-only 6-day progression."""
    # (Mon, Tue, Wed, Thu, Fri, Sat, Sun_miles, Sun_is_long)
    spec = [
        (0, 2, 0, 3, 0, 3, 4, False),
        (0, 3, 0, 3, 3, 3, 4, False),
        (0, 4, 0, 4, 4, 4, 5, False),
        (0, 5, 0, 3, 3, 5, 4, False),
        (0, 5, 0, 4, 5, 4, 6, False),
        (4, 5, 0, 5, 4, 8, 8, False),
        (4, 5, 0, 5, 4, 6, 10, True),
        (6, 6, 0, 6, 5, 6, 10, True),
        (5, 5, 0, 5, 6, 5, 15, True),
        (7, 5, 0, 6, 5, 8, 10, True),
        (5, 7, 0, 5, 6, 8, 16, False),
        (5, 7, 0, 6, 5, 8, 10, False),
        (7, 5, 0, 5, 6, 6, 16, True),
        (5, 7, 0, 6, 5, 8, 10, True),
        (7, 5, 0, 5, 6, 6, 16, True),
        (5, 5, 0, 5, 5, 8, 10, True),
        (7, 5, 0, 5, 6, 6, 8, False),
    ]
    rows: list[list[GridCell]] = []
    for mon, tue, wed, thu, fri, sat, sun, is_long in spec:
        r = [
            _easy(mon) if mon else _rest(),
            _easy(tue) if tue else _rest(),
            _rest(),
            _easy(thu),
            _easy(fri) if fri else _rest(),
            _easy(sat),
            _long(sun) if is_long else _easy(sun),
        ]
        rows.append(r)
    rows.append([_easy(5), _easy(5), _rest(), _easy(5), _easy(4), _easy(3), _race()])
    return rows


def _generate_beginner() -> list[list[GridCell]]:
    """Generate the 18-week Beginner Cumulative Fatigue progression via parametric phase rules."""
    rows: list[list[GridCell]] = []
    # Weeks 1-5: Base ramp
    base_spec = [
        (0, 0, 3, 0, 3, 4),
        (0, 2, 3, 3, 3, 4),
        (0, 4, 4, 4, 4, 5),
        (0, 5, 3, 3, 5, 5),
        (0, 5, 4, 5, 4, 6),
    ]
    for mon, tue, thu, fri, sat, sun in base_spec:
        rows.append([
            _easy(mon) if mon else _rest(),
            _easy(tue) if tue else _rest(),
            _rest(),
            _easy(thu),
            _easy(fri) if fri else _rest(),
            _easy(sat),
            _easy(sun),
        ])

    # Weeks 6-10: Speed Phase (4,800m interval volume + MP Tempo stepping 5 -> 8 mi)
    speed_weeks = [
        (4, _speed_workout(12, 400), 5, 4, 8, _easy(8)),
        (4, _speed_workout(8, 600), 5, 4, 6, _long(10)),
        (6, _speed_workout(6, 800), 5, 5, 6, _long(10)),
        (5, _speed_workout(5, 1000, unit_label="1K"), 8, 6, 5, _long(15)),
        (7, _speed_workout(4, 1200), 8, 5, 8, _long(10)),
    ]
    for mon, tue_cell, tempo_mi, fri, sat, sun_cell in speed_weeks:
        rows.append([_easy(mon), tue_cell, _rest(), _tempo(tempo_mi), _easy(fri), _easy(sat), sun_cell])

    # Weeks 11-17: Strength Phase (6 mi threshold intervals + MP Tempo stepping 8 -> 9 -> 10 mi + 16/10 long run wave)
    for idx, (reps, dist_mi) in enumerate(_STRENGTH_ROTATION):
        wk = 11 + idx
        is_peak_long = (wk % 2 == 1) and wk <= 15
        mon = 7 if (wk % 2 == 1 and wk >= 13) else 5
        tempo_mi = 8 if wk == 11 else (9 if wk <= 14 else 10)
        fri = 6 if (wk % 2 == 1 and wk >= 13) else 5
        sat = 6 if (wk % 2 == 1 and wk >= 13) else 8
        sun_cell = _long(16) if is_peak_long else (_easy(8) if wk == 17 else _long(10))
        rows.append([
            _easy(mon),
            _strength_workout(reps, dist_mi),
            _rest(),
            _tempo(tempo_mi),
            _easy(fri),
            _easy(sat),
            sun_cell,
        ])

    # Week 18: Taper & Race
    rows.append([_easy(5), _easy(5), _rest(), _easy(6), _easy(5), _easy(3), _race()])
    return rows


def _generate_advanced() -> list[list[GridCell]]:
    """Generate the 18-week Advanced Cumulative Fatigue progression via parametric phase rules."""
    rows: list[list[GridCell]] = []
    # Week 1-2 intro
    rows.append([_rest(), _rest(), _rest(), _easy(6), _easy(6), _easy(6), _easy(8)])
    rows.append([_easy(6), _speed_workout(12, 400), _rest(), _easy(6), _easy(6), _easy(6), _easy(8)])

    # Weeks 3-10: Speed Phase
    adv_speed = [
        (6, _speed_workout(8, 600), 6, 7, 6, _long(10)),
        (6, _speed_workout(6, 800), 6, 6, 8, _easy(8)),
        (6, _speed_workout(5, 1000, unit_label="1 km"), 6, 7, 6, _long(12)),
        (6, _speed_workout(4, 1200), 7, 6, 10, _easy(8)),
        (6, _speed_ladder(), 7, 7, 8, _long(14)),
        (6, _speed_workout(3, 1600, rec_m=600), 7, 6, 10, _easy(10)),
        (8, _speed_workout(6, 800), 8, 7, 8, _long(15)),
        (8, _speed_workout(4, 1200), 8, 7, 10, _long(10)),
    ]
    for mon, tue_cell, tempo_mi, fri, sat, sun_cell in adv_speed:
        rows.append([_easy(mon), tue_cell, _rest(), _tempo(tempo_mi), _easy(fri), _easy(sat), sun_cell])

    # Weeks 11-17: Strength Phase
    for idx, (reps, dist_mi) in enumerate(_STRENGTH_ROTATION):
        wk = 11 + idx
        tempo_mi = 8 if wk == 11 else (9 if wk <= 14 else 10)
        is_odd_peak = wk in (13, 15, 17)
        fri = 8 if is_odd_peak else 7
        sat = 8 if is_odd_peak else 10
        sun_cell = _long(16) if wk in (11, 13, 15) else (_easy(8) if wk == 17 else _long(10))
        rows.append([
            _easy(8),
            _strength_workout(reps, dist_mi),
            _rest(),
            _tempo(tempo_mi),
            _easy(fri),
            _easy(sat),
            sun_cell,
        ])

    # Week 18: Taper & Race
    rows.append([_easy(6), _easy(6), _rest(), _easy(6), _easy(5), _easy(3), _race()])
    return rows


PROGRAMS: dict[str, list[list[GridCell]]] = {
    "just_finish": _generate_just_finish(),
    "beginner": _generate_beginner(),
    "advanced": _generate_advanced(),
}
