# Interpretation & coaching layer (design)

How coach knowledge and live data get *applied* to an athlete's numbers — without ever
making the plan engine non-deterministic.

> **Status.** Built: **Stage A** — `RaceEstimate`, `CoachNote`, `EffortQuality`,
> `DataExclude`, `FitnessAnchor`, `WeeklyEvaluation` events; the pure `select_fitness_vdot` resolver
> (`engine/readiness.py`); and the `coach-note` / `mark-race` / `fitness-select` CLI commands
> (see [`docs/architecture/event-sourcing.md`](event-sourcing.md)). Sections marked
> **(proposed)** — race-condition adjustments, the NL boundary, live-monitor signals, and
> coach briefs — are the agreed design, not yet implemented.

Canonical neighbours: the reasoning layer → [`docs/architecture/athlete-readiness.md`](athlete-readiness.md);
the event log + replan fold → [`docs/architecture/event-sourcing.md`](event-sourcing.md); feeds + VDOT
selection → [`docs/architecture/feeds-and-analysis.md`](feeds-and-analysis.md).

---

## 1. The core principle

Two kinds of data, kept strictly separate:

- **Facts** — what the feeds report: Strava activities, sheet rows, race results. Immutable,
  re-pullable, no judgement.
- **Interpretation** — how a coach (or, at the edges, an LLM) says those facts should be
  *read*: "that marathon was run sick," "that half wasn't a max effort," "ignore that
  GPS-glitched run," "she's been nailing the plan — encourage her."

**The interpretation layer is the event log.** Facts flow in from feeds; interpretation
flows in as events; `replan` folds events onto the baseline; `engine/plan` stays pure and
regression-tested. Nothing below changes that guarantee.

The design rule the whole layer obeys:

> **Deterministic where it matters; natural language only at the input edges.**

Every value that affects a plan is recomputed by deterministic code from *structured*
inputs. Natural language (race notes, a text from the athlete, a coach's sentence) is only
ever used to **produce** a structured directive — never to directly set a pace or a mileage.

```
feeds (facts) ─────────────┐
                           ├─► replan fold ─► engine/plan (pure) ─► plan
coach/LLM (interpretation) ─┘        ▲
        ▲                            │
   NL → structured (LLM, proposed)   │  deterministic recompute
        │                            │
   coach approves ──────────────────┘
```

---

## 2. Directive vocabulary (the "which data / how to read it" events)

All directives share one shape: **a reference + an interpretation**, and all fold at
`replan`. References point at a specific activity by **Strava activity id** (the reports
already carry it as `url`) or, for a window, an ISO date range.

| Event | Status | What it says | Deterministic effect |
|-------|--------|--------------|----------------------|
| `RaceEstimate` | **built** | "This race was really worth time T" (sick / sandbagged). See [`docs/architecture/event-sourcing.md`](event-sourcing.md). | Sets `vdot` to the detrained `effective_vdot`. |
| `CoachNote` | **built** | Free-text observation. | Provenance only → `coach_note` plan flag. |
| `EffortQuality` | **built** | Tag a race `max \| submaximal \| compromised`. | Non-`max` races are dropped from VDOT selection (`select_fitness_vdot`). |
| `FitnessAnchor` | **built** | Pin *the* race (or VDOT) that sets fitness. | Resolved by `fitness-select`; folds `vdot` into the baseline. |
| `WeeklyEvaluation` | **built** | Weekly coach calibration (ISO `week_start` + optional `calibrated_vdot`, `estimated_mpw`, `easy_pace_override_s`, `note`). | Folds into `AthleteInputs` before `build_plan` (`replan`); see [event-sourcing](event-sourcing.md). |
| `DataExclude` | **built** | "Ignore this race." | Dropped from `select_fitness_vdot`. (Volume-read exclusion is future.) |

This directly closes the Cindy case: her 2:08 half and 10K carried no note saying "easy
effort," so `recommended_vdot` (recency-first, in `engine/analyze.py`) anchored her to a soft race. An
`EffortQuality(submaximal)` on those two — or a `FitnessAnchor` on her marathon — makes the
selector ignore them. (Today we patched it with a `RaceEstimate`; the directives make it the
normal path, not a manual correction.)

---

## 3. Race-condition adjustments (proposed)

A coach shouldn't have to hand-guess "clean ≈ 3:55." When a race was run under a known
condition, the model should back out the clean-effort estimate itself. A small **condition
taxonomy** maps to a deterministic time penalty that we *remove* to estimate the clean VDOT:

| Condition | Typical marathon cost (tunable house default) | Source of magnitude |
|-----------|----------------------------------------------|---------------------|
| Illness (GI / food poisoning) | +3–8% finish time | coaching heuristic — **tune** |
| Heat (well above ~12 °C) | +2–6% | Daniels notes heat cost; magnitude house |
| Strong wind / hilly course | +1–4% | house |
| In-race injury / cramping | coach-set, often DNF-adjacent | coach judgement |

The magnitudes are **house heuristics, coach-overridable** — same discipline as the
diminishing-return curve in `engine/readiness.py`. The flow: a structured
`RaceCondition(race_ref, kind, severity)` → deterministic clean-time estimate → the same
`effective_vdot` path `RaceEstimate` already uses. The coach can always override the
resulting number (as we did by setting 3:55 directly).

**Why this matters for determinism:** the *adjustment* is a lookup, not a vibe. Given the
same condition + severity, the recompute is identical every time.

---

## 4. The natural-language boundary (where the LLM is allowed)

Some interpretation lives in prose — a race recap ("blew up at 30k, stomach was wrecked"),
or, as with Cindy, a *conversation* the coach has off-platform ("she said the halves were
easy"). The LLM's only job is **NL → structured directive**, never NL → number.

- The LLM reads notes / a pasted conversation and proposes directives
  (`RaceCondition`, `EffortQuality`, `Injury`, …) as events with `status=proposed`
  (the mechanism already exists — see [`docs/architecture/event-sourcing.md`](event-sourcing.md)
  §"LLM and coach approval" and [`llm/boundary.py`](../../llm/boundary.py)).
- The coach reviews and flips to `approved`/`applied`. Only then does the deterministic
  recompute run.
- If there's nothing to extract (Cindy's recent races had no such note), the LLM proposes
  nothing — the coach enters an `EffortQuality` directly after talking to her.

So: **LLM at the edge to structure language; deterministic everywhere a value is produced;
a human gate between the two.**

---

## 5. Live training-block ingestion → readjust (proposed)

`monitor` already turns weekly Strava actuals into `AdherenceFlag` / `MissedQuality` events
that `replan` folds. Two gaps:

- **Emit the signals already defined but unused** in `store/events.py`: `EasyPaceDrift`
  (easy runs creeping toward threshold), `LongRunIncomplete`, `FatigueFlag` /
  `OverreachFlag` (week-over-week load spikes). `engine/monitor.py` is pure; wire these from
  the weekly feed.
- **A refresh loop:** `scrape training → monitor → replan`, on demand or scheduled, so a
  real layoff or a run of missed quality reshapes the *remaining* block automatically
  instead of waiting for the next manual rebuild.

---

## 6. Coach briefs / athlete nudges (proposed)

A new **advisory** output (engine stays pure) — `coach-brief <athlete>` reads the latest
plan + recent monitor/coach events and emits athlete-facing messages. Because §1–§5 have
already converted everything to **structured signals**, the briefs themselves are
**deterministic templates** keyed off those signals:

- adherence ≥ 0.92 → encouragement + name this week's anchor session;
- `EasyPaceDrift` → "keep easy easy so the quality lands";
- `MissedQuality` → reschedule guidance;
- `FatigueFlag` → back-off prompt.

LLM polish (tone, phrasing) is optional and, if used, enters as `proposed` for coach
approval — never inventing the *content*, only the wording.

---

## 7. Staging

1. **A — Directives** (`EffortQuality`, `FitnessAnchor`, `DataExclude`) — **done.** Finishes the
   data-selection story; makes Cindy's fix the normal path (directive-derived VDOT via
   `select_fitness_vdot` + `fitness-select`).
2. **A′ — Race-condition adjustments** (§3) + the NL boundary (§4): conditions auto-derive
   clean-effort estimates; LLM structures notes/conversation into proposed directives.
3. **B — Live monitor signals + refresh loop** (§5).
4. **C — Coach briefs** (§6).

Each stage is additive and preserves the determinism guarantee: directives, signals, and
briefs all live as events / advisory output; `engine/plan` never changes.
