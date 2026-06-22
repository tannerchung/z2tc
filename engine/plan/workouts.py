"""Shared SOS / quality session catalog (ids + citations) — extend per coach.

Engines may reference these ids from verbatim grids once day-by-day tables land in
``*_grids.py``. Today Hansons/Pfitzinger still compose SOS in their builders.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkoutTemplate:
    coach: str
    key: str
    label: str
    citation: str


CATALOG: tuple[WorkoutTemplate, ...] = (
    WorkoutTemplate("hanson", "speed_ladder", "SOS Speed ladder (400–1200m)", "Hansons pp.76–82"),
    WorkoutTemplate("hanson", "strength_mp10", "SOS Strength @ MP−10s/mi", "Hansons pp.88–94"),
    WorkoutTemplate("hanson", "tempo_mp", "SOS Tempo @ goal MP", "Hansons p.100"),
    WorkoutTemplate("daniels", "threshold_cruise", "Threshold / cruise intervals", "Daniels Table 4.2 p.69"),
)
