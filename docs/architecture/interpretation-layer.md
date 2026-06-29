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

## 6a. Plan-sheet narrative personalization (built)

The plan sheet's four narrative surfaces — the summary, "How this plan is personalized to you",
the notes/cautions block, and the per-week "Why" — now consume the same structured signals:

- The **athlete dossier** (`engine/athlete_profile.py`) feeds the three paragraph surfaces: the
  responder profile (volume-sensitive / speed-dominant / stable), the volume↔VDOT correlation, and
  the short-vs-marathon endurance gap shape the framing (e.g. speed-dominant → bias the block toward
  durability over peak mileage).
- The **execution summary** (`engine/execution.py`) folds the accumulating monitor signals into
  per-week feedback. Two builders: `summarize_execution(payloads)` sees only the monitor's shortfall
  flags (`AdherenceFlag` / `MissedQuality` / `WeeklyEvaluation`), while
  `execution_from_actuals(plan, weekly_actuals)` scores **every elapsed week** against its
  prescription. The latter's `weekly_actuals` are persisted to the store's `weekly_actuals` table by
  `monitor` and `publish-sheet --training` (upsert per `(season, week_start)`), so scoring **replays
  from the store** when no feed is supplied — the feed file is an input, not the source of truth. It
  lets the narrative give **earned positive reinforcement** — on-plan weeks get a "nice work" note in
  their "Why" and the notes block leads with the consistency tally — and frames any shortfalls as the
  reason for conservative choices, rather than only listing misses. Positive reinforcement is only
  emitted when we scored the week from actuals (never inferred from the mere absence of a flag).
  Weeks with no data render exactly as before.

This stays true to §6's contract: the **content is deterministic** (number-safe templates, test-locked).
The optional `publish-sheet --llm-narrative` pass only smooths the wording of the three paragraph
surfaces through `llm.boundary.narrate_personalization`, and a number-subset guard
(`validate_numbers_subset`) rejects any output that introduces a figure not already in the facts — so
the LLM can never fabricate a pace, mileage, or finish time. No API key → deterministic text. (The
per-week "Why" and execution feedback are **already fully deterministic** — the LLM only touches the
three paragraph surfaces.)

### 6b. Narrative versioning + the distillation loop (built)

The goal is to **shrink the LLM's job over time**: whatever it reliably does, graduate into a
deterministic template. To know what's safe to graduate, every render is captured.

- **Versioning.** `render.plan_layout.NARRATIVE_TEMPLATE_VERSION` (bump on any deterministic-template
  change), `llm.boundary.NARRATE_PROMPT_VERSION` + the active model (`active_narrate_model()`), and
  the store's `SCHEMA_VERSION` (mirrored to SQLite `PRAGMA user_version`) tag each record so a later
  shift in output can be attributed to a template revision, a prompt change, or a model swap. Plan
  artifacts already carry the resolved-inputs fingerprint; the narrative records carry it too.
- **Capture.** `engine/narrative_capture.py` (pure) packages, per surface, the **deterministic draft
  and the final text** plus those versions and the non-numeric signals (responder, execution tally)
  into a `NarrativeRender`. `publish-sheet` appends one per smoothable surface to the append-only
  `narrative_renders` table (best-effort — capture never breaks a render). Each render carries the
  `plan_artifact_id` it described, so a captured narrative joins back to the exact plan.
- **Lineage.** Every `publish-sheet` also writes a `publications` row tying the published
  `plan_artifact_id` to where it went (spreadsheet + sheet title/url) and the engine/template/prompt/
  model versions in force (`narrative_source` ∈ deterministic/llm/mixed). Read via
  `Store.list_publications(athlete, plan_artifact_id=…)`. This closes the loop "which plan, built by
  which engine, with which narrative, did this sheet show?" — the join key for outcome analysis.
- **Monitor / pattern.** `python main.py narrative-log [athlete]` folds the log into per-surface
  stats: how often the LLM actually changed the deterministic text (`llm_change_rate`), the mean edit
  size, and the guard pass rate. A surface the LLM rarely changes (≥5 renders, <20% changed) is
  flagged a **`det-candidate`** — drop the LLM there and keep the template. High-variance surfaces are
  genuinely complex and stay on the LLM. This is the offline loop: capture → analyze → graduate
  patterns into `engine`/`render` deterministic templates → re-measure.

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
