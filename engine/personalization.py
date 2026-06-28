"""Personalization context — the number-safe bridge between the deterministic narrative and the
optional LLM smoothing pass.

The render layer builds the four plan-sheet narrative surfaces deterministically (numbers and all),
then packages the smoothable paragraph surfaces here together with ``allowed_numbers`` — every
numeric token the deterministic facts legitimately contain. ``llm/boundary.narrate_personalization``
may rephrase the prose for tone/cohesion, but the subset guard rejects any output that introduces a
number not already in ``allowed_numbers`` — so the LLM can never invent paces, mileage, or finish
times. With no API key (or any guard failure) the deterministic surfaces are used verbatim.

Pure and render-free so the LLM boundary can import it without a cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    """All numeric tokens in ``text`` (integers and decimals), as strings."""
    return set(_NUMBER.findall(text or ""))


@dataclass
class PersonalizationContext:
    """Smoothable narrative surfaces + the numbers the LLM is allowed to echo.

    ``surfaces`` maps a surface name (``"summary"``, ``"personalized"``, ``"notes"``) to its
    deterministic prose. ``signals`` carries non-numeric grounding (e.g. responder type) the LLM may
    use for tone but not for facts."""

    surfaces: dict[str, str] = field(default_factory=dict)
    signals: dict[str, str] = field(default_factory=dict)
    allowed_numbers: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, surfaces: dict[str, str], *, signals: dict[str, str] | None = None) -> "PersonalizationContext":
        kept = {k: v for k, v in surfaces.items() if v}
        allowed: set[str] = set()
        for text in kept.values():
            allowed |= numbers_in(text)
        return cls(surfaces=kept, signals=dict(signals or {}), allowed_numbers=allowed)

    @property
    def has_content(self) -> bool:
        return bool(self.surfaces)
