"""Strava marathon-report + chip feeds → enriched ``SurveyInputs``.

This is the intake **merge** brain documented in ``docs/intake-and-engine.md``: form row
(``pull-intake``) plus Strava block metrics, optional NYRR / external chip overrides, and
returning-marathoner fitness + volume decay.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from engine.analyze import _filter_weeks, fmt_duration, summarize
from engine.readiness import (
    decayed_volume_capacity,
    resolve_merge_vdot,
)
from engine.vdot import recommended_vdot
from lib.data_feeds.chip_lookup import ChipRace, build_chip_index
from store.models import SurveyInputs

_log = logging.getLogger(__name__)


def detect_returning_marathoner(
    base: SurveyInputs,
    report: dict[str, Any],
) -> bool:
    """True when intake, Strava, or prior marathon times indicate a completed marathon."""
    if base.returning_marathoner:
        return True
    if base.latest_marathon_time_s or base.latest_marathon_race_text:
        return True
    latest = report.get("latest_marathon")
    return isinstance(latest, dict) and bool(latest.get("date"))


def _w_now_post_marathon(weeks: list[dict], marathon_date: date, today: date) -> float:
    post = _filter_weeks(weeks, marathon_date + timedelta(days=1), today)
    summ = summarize(post)
    weekly = sorted(summ.weekly_run_miles.items(), key=lambda kv: kv[0])
    if not weekly:
        return 0.0
    last_n = [m for _, m in weekly[-4:]]
    return round(sum(last_n) / len(last_n), 1)


def _weeks_since_peak(peak_week_iso: str | None, today: date) -> int:
    if not peak_week_iso:
        return 0
    try:
        peak_monday = date.fromisoformat(peak_week_iso[:10])
    except ValueError:
        return 0
    return max(0, (today - peak_monday).days // 7)


def _apply_chip_to_races(
    races: list[dict], chip_index: dict[tuple[str, str], ChipRace]
) -> tuple[list[dict], int, list[str]]:
    patched: list[dict] = []
    n = 0
    log: list[str] = []
    for r in races:
        cat = r.get("category")
        d = r.get("date")
        if not isinstance(cat, str) or not isinstance(d, str):
            patched.append(dict(r))
            continue
        chip = chip_index.get((d[:10], cat))
        if chip is None:
            patched.append(dict(r))
            continue
        old = r.get("duration_s")
        if isinstance(old, int) and old == chip.duration_s:
            patched.append(dict(r))
            continue
        nr = dict(r)
        nr["duration_s"] = chip.duration_s
        nr["time"] = fmt_duration(chip.duration_s)
        nr["chip_source"] = chip.source
        patched.append(nr)
        n += 1
        log.append(f"chip override {d} {cat}: {chip.source} ({chip.race_name})")
    return patched, n, log


def merge_strava_report(
    base: SurveyInputs,
    report: dict[str, Any],
    weeks: list[dict],
    *,
    today: date | None = None,
    chip_search_name: str | None = None,
    include_nyrr: bool = True,
    activities: list[dict] | None = None,
    returning_marathoner: bool | None = None,
) -> tuple[SurveyInputs, list[str]]:
    """Merge Strava report + training weeks into ``base``. Returns ``(survey, provenance)``."""
    today = today or date.today()
    provenance: list[str] = []

    latest_m = report.get("latest_marathon")
    if not isinstance(latest_m, dict) or not latest_m.get("date"):
        raise ValueError("Report has no latest_marathon date; cannot derive block metrics.")

    m_date = date.fromisoformat(str(latest_m["date"])[:10])
    returning = (
        returning_marathoner
        if returning_marathoner is not None
        else detect_returning_marathoner(base, report)
    )

    tb = report.get("training_block") or {}
    weekly = tb.get("weekly_run_miles") or {}
    peak_mi = 0.0
    if isinstance(weekly, dict) and weekly:
        peak_mi = max(float(v) for v in weekly.values() if isinstance(v, (int, float)))

    longest = tb.get("longest_run") or {}
    lr_mi = longest.get("miles")
    longest_mi = float(lr_mi) if isinstance(lr_mi, (int, float)) else base.longest_run_mi

    post = report.get("post_marathon") or {}
    races = list(post.get("races") or [])

    chip_index: dict[tuple[str, str], ChipRace] = {}
    if chip_search_name and chip_search_name.strip():
        chip_index, chip_log = build_chip_index(chip_search_name.strip(), include_nyrr=include_nyrr)
        provenance.extend(chip_log)
        races, n_chip, chip_notes = _apply_chip_to_races(races, chip_index)
        provenance.extend(chip_notes)
        if n_chip:
            provenance.append(f"applied {n_chip} chip override(s) on post-marathon races")

    w_now = _w_now_post_marathon(weeks, m_date, today)

    weeks_off_peak = _weeks_since_peak(tb.get("peak_week"), today)
    decayed_peak = decayed_volume_capacity(peak_mi, weeks_off_peak) if returning else None

    resolution = resolve_merge_vdot(
        races,
        weeks,
        marathon_date=m_date,
        today=today,
        activities=activities,
    )
    if resolution is not None:
        vdot = resolution.vdot
        raw_vdot = resolution.raw_vdot
        break_days = resolution.break_days
        crossed = resolution.cross_trained
        cross_note = resolution.cross_training_note
        provenance.append(
            f"VDOT {vdot} from {resolution.fitness.source} "
            f"(raw {raw_vdot}; break {break_days}d since {resolution.break_window})"
        )
        if resolution.freshness.trust_race_vdot:
            provenance.append("freshness: trust race VDOT")
        else:
            provenance.append("freshness: Table 15.1 adjustment applied")
        provenance.extend(resolution.notes)
    else:
        vd = recommended_vdot(races)
        if not vd:
            raise ValueError("Could not compute VDOT from post-marathon races.")
        vdot = float(vd["vdot"])
        raw_vdot = vdot
        break_days = 0
        crossed, cross_note = False, None
        src = vd["source_race"]
        provenance.append(f"VDOT {vdot} from {src.get('category')} {src.get('time')}")

    mar_name = str(latest_m.get("name") or "") or None
    mar_raw = latest_m.get("duration_s")
    mar_secs = int(mar_raw) if isinstance(mar_raw, int) else None
    chip_m = chip_index.get((m_date.isoformat(), "Marathon"))
    if chip_m is not None:
        mar_secs = chip_m.duration_s
        provenance.append(f"last marathon chip: {chip_m.source} {fmt_duration(mar_secs)}")

    half_name: str | None = None
    half_secs: int | None = None
    for r in races:
        if r.get("category") != "Half Marathon":
            continue
        ds = r.get("duration_s")
        if not isinstance(ds, int):
            continue
        if half_secs is None or ds < half_secs:
            half_secs = ds
            half_name = str(r.get("name") or "") or None

    race_fit = returning and (peak_mi > w_now + 1.0 or bool(base.race_fit))

    if returning:
        provenance.append(
            f"returning marathoner: block {tb.get('start')} → {tb.get('end')} "
            f"peak {peak_mi:g} mpw"
        )
        if decayed_peak is not None and decayed_peak < peak_mi:
            provenance.append(
                f"decayed volume capacity ≈ {decayed_peak:g} mpw ({weeks_off_peak} wk since peak week)"
            )

    merge_note = "; ".join(provenance)
    prev_notes = (base.free_notes or "").strip()
    free_notes = f"{prev_notes}\n\n[merge] {merge_note}".strip() if prev_notes else f"[merge] {merge_note}"

    merged = base.model_copy(
        update={
            "returning_marathoner": returning,
            "race_fit": race_fit,
            "vdot": vdot,
            "w_now": w_now,
            "p_history": round(peak_mi, 1),
            "longest_run_mi": round(longest_mi, 1),
            "latest_half_race_text": half_name,
            "latest_half_time_s": half_secs,
            "latest_marathon_race_text": mar_name,
            "latest_marathon_time_s": mar_secs,
            "last_marathon_date": m_date.isoformat(),
            "last_marathon_time_s": mar_secs,
            "decayed_peak_mpw": decayed_peak,
            "recent_break_days": break_days,
            "cross_trained_during_break": crossed,
            "cross_training_note": cross_note,
            "free_notes": free_notes,
        }
    )
    return merged, provenance
