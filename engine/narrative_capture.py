"""Narrative capture — the versioned, append-only record of what the plan-sheet narrative actually
said, so we can monitor the deterministic-vs-LLM split over time and decide what to graduate into
deterministic templates.

The plan sheet builds each narrative surface deterministically (the source of truth), then optionally
runs a number-safe LLM smoothing pass (`llm.boundary.narrate_personalization`). This module packages,
per surface, *both* texts plus the versions and signals that produced them into a `NarrativeRender`.
Persisting those (see `store.db.append_narrative_render`) lets the offline distillation loop ask: how
often does the LLM actually change the deterministic text, by how much, and for which signal patterns?
Surfaces the LLM rarely changes are candidates to make fully deterministic; high-variance surfaces are
genuinely complex and stay on the LLM.

Pure: it only compares strings and packages metadata — no IO, no model calls. The renderer feeds it
deterministic + final text; the CLI persists the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class NarrativeRender:
    """One surface's render: the deterministic draft, the text actually shown, and the provenance
    (template/prompt/model versions + the non-numeric signals) needed to analyze the difference."""

    athlete_id: str
    surface: str                       # "summary" | "personalized" | "notes"
    template_version: str
    source: str                        # "deterministic" | "llm" — which path produced final_text
    deterministic_text: str
    final_text: str
    changed: bool = False              # final differs from the deterministic draft
    char_delta: int = 0                # len(final) - len(deterministic), signed
    guard_passed: bool = True          # the number-subset guard accepted the LLM output
    prompt_version: str | None = None  # set only when source == "llm"
    llm_model: str | None = None       # set only when source == "llm"
    signals: dict[str, str] = field(default_factory=dict)
    inputs_fingerprint: str = ""
    season_id: str | None = None
    plan_artifact_id: str | None = None   # the plan this render described (set by the CLI at publish)
    created_at: str = field(default_factory=_now_iso)


def build_narrative_captures(
    deterministic: dict[str, str],
    final: dict[str, str],
    *,
    athlete_id: str,
    template_version: str,
    llm_applied: bool,
    llm_model: str | None = None,
    prompt_version: str | None = None,
    signals: dict[str, str] | None = None,
    inputs_fingerprint: str = "",
    season_id: str | None = None,
) -> list[NarrativeRender]:
    """One `NarrativeRender` per non-empty deterministic surface, comparing it to the final text.

    ``llm_applied`` is the global outcome of the smoothing pass: when True every surface's final text
    came from the (guard-passed) LLM output — even a surface the LLM left byte-identical is recorded as
    ``source="llm"`` with ``changed=False`` (a meaningful "LLM no-op" signal). When False the LLM was
    disabled, unavailable, or its output was rejected, and the deterministic draft is the final text."""
    sigs = {k: str(v) for k, v in (signals or {}).items() if v not in (None, "")}
    out: list[NarrativeRender] = []
    for surface, det in deterministic.items():
        det = det or ""
        if not det.strip():
            continue
        fin = (final.get(surface) or det)
        source = "llm" if llm_applied else "deterministic"
        out.append(
            NarrativeRender(
                athlete_id=athlete_id,
                surface=surface,
                template_version=template_version,
                source=source,
                deterministic_text=det,
                final_text=fin,
                changed=fin.strip() != det.strip(),
                char_delta=len(fin) - len(det),
                prompt_version=prompt_version if source == "llm" else None,
                llm_model=llm_model if source == "llm" else None,
                signals=dict(sigs),
                inputs_fingerprint=inputs_fingerprint,
                season_id=season_id,
            )
        )
    return out


_DEFAULT_STRAVA_TITLE_RE = re.compile(
    r"^\s*(morning|lunch|afternoon|evening|night)\s+(run|walk|virtual\s+run|trail\s+run|workout)\s*$",
    re.IGNORECASE,
)


def compute_narrative_sha256(activity: dict[str, Any]) -> str:
    """Deterministic SHA-256 fingerprint of an activity's unstructured narrative & metadata fields.
    Used to detect delayed Strava title/description/private_note edits (24–72h post-run) without
    re-running LLM extraction when nothing changed."""
    import hashlib

    name = str(activity.get("name") or "").strip()
    desc = str(activity.get("description") or "").strip()
    priv = str(activity.get("private_note") or "").strip()
    rpe = str(activity.get("perceived_exertion") or "").strip()
    wtype = str(activity.get("workout_type") or "").strip()
    gear = str(activity.get("gear_id") or "").strip()
    canonical = f"{name}\x1f{desc}\x1f{priv}\x1f{rpe}\x1f{wtype}\x1f{gear}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_default_strava_title(title: str | None) -> bool:
    """Return True if ``title`` is blank or a generic auto-generated Strava title ('Morning Run')."""
    if not title or not str(title).strip():
        return True
    return bool(_DEFAULT_STRAVA_TITLE_RE.match(str(title)))


def needs_post_run_narrative_nudge(
    activity: dict[str, Any],
    *,
    min_long_run_miles: float = 10.0,
) -> bool:
    """Return True when a paid coached athlete uploads a key session (Long Run >= ``min_long_run_miles``,
    Race ``workout_type == 1``, or Workout ``workout_type == 3``) with no description/private_note and
    only a default Strava title ('Morning Run'). Prevents spamming nudges on routine easy recovery runs."""
    desc = str(activity.get("description") or "").strip()
    priv = str(activity.get("private_note") or "").strip()
    if desc or priv:
        return False
    title = str(activity.get("name") or "").strip()
    if not is_default_strava_title(title):
        return False
    dist_m = float(activity.get("distance") or activity.get("distance_m") or 0.0)
    miles = dist_m / 1609.344 if dist_m > 100 else float(activity.get("miles") or 0.0)
    wtype = activity.get("workout_type")
    is_key_session = miles >= min_long_run_miles or wtype in (1, 2, 3)
    return bool(is_key_session)



@dataclass
class SurfaceStats:
    """Aggregate for one surface across captured renders — the read the distillation loop acts on."""

    surface: str
    n: int = 0
    llm_renders: int = 0          # renders where the LLM produced the final text
    llm_changed: int = 0          # of those, how many actually differed from the deterministic draft
    mean_abs_char_delta: float = 0.0
    guard_failures: int = 0

    @property
    def llm_change_rate(self) -> float | None:
        """Share of LLM renders that changed the deterministic text. Low ⇒ the LLM is mostly a no-op
        here ⇒ a candidate to drop the LLM and keep the deterministic template."""
        return round(self.llm_changed / self.llm_renders, 3) if self.llm_renders else None

    @property
    def deterministic_candidate(self) -> bool:
        """Heuristic: enough LLM renders observed and it changed the text <20% of the time."""
        return self.llm_renders >= 5 and (self.llm_change_rate or 0.0) < 0.2


def summarize_surface_stats(rows: list[dict]) -> list[SurfaceStats]:
    """Fold capture rows (dicts with surface/source/changed/char_delta/guard_passed) into per-surface
    stats. Accepts plain dicts so it works directly off the store rows or `NarrativeRender` dumps."""
    by: dict[str, SurfaceStats] = {}
    deltas: dict[str, list[int]] = {}
    for r in rows:
        surface = str(r.get("surface") or "")
        st = by.setdefault(surface, SurfaceStats(surface=surface))
        st.n += 1
        deltas.setdefault(surface, []).append(abs(int(r.get("char_delta") or 0)))
        if str(r.get("source")) == "llm":
            st.llm_renders += 1
            if r.get("changed"):
                st.llm_changed += 1
        if not r.get("guard_passed", True):
            st.guard_failures += 1
    for surface, st in by.items():
        d = deltas.get(surface) or []
        st.mean_abs_char_delta = round(sum(d) / len(d), 1) if d else 0.0
    return [by[k] for k in sorted(by)]
