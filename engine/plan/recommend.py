"""Rank coach + program fit from ``AthleteInputs`` (advisory; deterministic)."""

from __future__ import annotations

from dataclasses import dataclass

from . import common
from .models import AthleteInputs


@dataclass(frozen=True)
class CoachRecommendation:
    method: str
    program: str | None
    score: float
    notes: str


def recommend_coaches(inputs: AthleteInputs) -> list[CoachRecommendation]:
    """Higher ``score`` = better structural fit (days, base, volume philosophy)."""
    base = max(inputs.w_now, inputs.p_history)
    out: list[CoachRecommendation] = []

    out.append(
        CoachRecommendation(
            common.DANIELS,
            None,
            100.0 - (5 if inputs.days_per_week >= 6 else 0),
            "Daniels 2Q: best default for ≤4 days / comeback ramps (club Q1 on Sat).",
        )
    )
    out.append(
        CoachRecommendation(
            common.HIGDON,
            "intermediate1" if base > 25 else "novice1",
            88.0 - (8 if inputs.days_per_week < 4 else 0) - (6 if base > 40 else 0),
            "Higdon: native 4-day Novice or 5-day Intermediate; distance-model long runs.",
        )
    )
    out.append(
        CoachRecommendation(
            common.PFITZINGER,
            "ch.8",
            72.0 - (15 if inputs.days_per_week < 5 else 0) - (10 if base < 33 else 0),
            "Pfitzinger: needs 5–7 days and ~33 mpw week-1 entry for ch.8 (p.271, p.285).",
        )
    )
    out.append(
        CoachRecommendation(
            common.HANSON,
            "beginner" if base < 50 else "advanced",
            60.0 - (25 if inputs.days_per_week < 6 else 0),
            "Hansons: 6-day cumulative-fatigue; poor structural fit if <6 days (p.61).",
        )
    )
    return sorted(out, key=lambda r: r.score, reverse=True)
