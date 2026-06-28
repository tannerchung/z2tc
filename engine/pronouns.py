"""Pronoun handling for coach-facing prose (the athlete dossier).

Presentation metadata only — pronouns never reach ``AthleteInputs`` or the plan engine, so they
cannot affect a generated plan. The athlete-facing plan tab is written in the second person and
needs none of this; this exists so the third-person coach dossier refers to a runner correctly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pronouns:
    subject: str          # she / he / they
    object: str           # her / him / them
    possessive: str       # her / his / their   (possessive adjective)
    possessive_noun: str  # hers / his / theirs


SHE = Pronouns("she", "her", "her", "hers")
HE = Pronouns("he", "him", "his", "his")
THEY = Pronouns("they", "them", "their", "theirs")


def resolve(spec: str | None) -> Pronouns:
    """Map a spec like ``"she/her"`` / ``"he/him"`` / ``"they/them"`` to a ``Pronouns``.

    Unset or unrecognized specs fall back to gender-neutral ``they/their`` so the prose still
    reads correctly for an athlete the coach has not marked.
    """
    if not spec:
        return THEY
    first = spec.strip().lower().split("/")[0].strip()
    if first in ("she", "her", "hers"):
        return SHE
    if first in ("he", "him", "his"):
        return HE
    return THEY
