# Event sourcing and replan contract

This document is the **contract** between the Strava monitor, Sheet read-back, the typed LLM boundary, and the deterministic plan engine. Numbers always come from code; events only **parameterize** a re-derivation.

## Model

- **Baseline** — `SurveyInputs` / `AthleteInputs` at intake (§0 inputs).
- **Append-only log** — `events` table (`store/db.py`): each row has `event_type`, `payload_json`, `source`, `status`, `ts`.
- **Replan** — `replan(baseline, store, athlete_id)` in [`engine/plan/replan.py`](../../engine/plan/replan.py) folds **approved** and **applied** events (skips `proposed` and `rejected`) into a working `AthleteInputs`, then calls `build_plan`. Pure math stays in `engine/plan/`; folding is deterministic and ordered by `ts`.

## Seasons (the scope of a baseline + log + artifacts)

The unit that a baseline, event log, and plan artifacts hang off is a **season** (one marathon
block), not the athlete. `athletes` is the person; `seasons` is the training cycle keyed to one
A-race (`store/models.Season`, `status`: `planned` | `active` | `archived`). Exactly one season
is **active** — the replan/publish target.

- Store methods take `athlete_id` and resolve the **active** season when `season_id` is omitted, so single-season callers are unchanged; a default season is created on first write.
- `replan` / `fold_events_to_inputs` accept an optional `season_id`; next season's events never fold into this season's plan.
- **Carry-forward** — `python main.py start-season` (→ `store.carryforward.build_next_season_survey`) archives the active season and seeds a fresh baseline from the prior **ending state**: calibrated VDOT, demonstrated peak → `p_history` / `recent_sustained_mpw`, a recovered `w_now`, `returning_marathoner=True`, `last_marathon_*`. It also scans race history (`engine.readiness.select_fitness_vdot`, Table 15.1 detraining) and takes the higher defensible VDOT. Seeding is auditable in the season's `meta.carry_forward`.
- **Resolved-inputs snapshot** — `plan_artifacts.resolved_inputs_json` stores the folded `AthleteInputs` that built the plan, so an artifact is self-describing/rebuildable even if fold logic changes.
- `python main.py list-seasons <id>` shows seasons (active marked `*`).

## Event catalog

| Payload kind | Source typical | Effect on baseline / plan |
|--------------|----------------|---------------------------|
| `SetDays` | Form / coach / sheet | Updates `days_per_week` (3–7). Redistributes sessions via existing `assemble_week` rules. |
| `SetGoal` | Form / coach | Updates `goal_marathon_s` (goal MP and caps follow). |
| `SetRaceDate` | Form / coach | Updates `race_date` (block anchor). |
| `TuneUpResult` | Coach (`record-tune-up`) / monitor | Updates `vdot` from a tune-up race/time-trial result (VDOT computed at write time so the engine stays pure). The CLI also reports the goal re-anchor verdict. |
| `RaceEstimate` | Coach | Effort-corrected read of a known race (run sick / submaximal). Stores the trained-peak VDOT it really showed and an `effective_vdot` detrained to today (Table 15.1); the latter folds into `vdot`. Surfaces a `coach_note` flag. |
| `CoachNote` | Coach | Free-text observation. Provenance only — surfaces as a `coach_note` plan flag, changes no numbers. |
| `EffortQuality` | Coach | Tags a race `max \| submaximal \| compromised`. Drops non-`max` efforts from VDOT selection (`select_fitness_vdot`). Flag only at fold; consumed by `fitness-select`. |
| `DataExclude` | Coach | Ignore a race/data point in fitness/volume reads. Flag only at fold; consumed by `fitness-select`. |
| `FitnessAnchor` | Coach (`fitness-select`) | The resolved fitness read: pins a race and/or carries a detrained `vdot`. Folds `vdot` into the baseline. |
| `WeeklyEvaluation` | Coach | Optional `calibrated_vdot`, `estimated_mpw` (sets `w_now` + `reentry_start_mpw`), `easy_pace_override_s` (s/mi); `week_start` + `note` for provenance. Folds into inputs before `build_plan`. |
| `Injury` | Coach / LLM (approved) | Sets `injury_prone=True`; optional `days_off` recorded on plan flags (ramp rules §3c to be expanded). |
| `Difficulty` | Coach / sheet | Nudges `w_now` (volume lever, bounded); see `replan.apply_payload`. |
| `ManualOverride` | Coach / **dossier** (`athlete-report --propose`) | Sets a single allowed `AthleteInputs` field by name (validated). The dossier proposes data-backed ones (e.g. `reentry_start_mpw` anchored on the demonstrated opener) as `proposed`; nothing changes until `review` approves. |
| `Unavailable` | Form / coach | **MVP:** recorded on plan flags only; future: week mask / reshuffle quality. |
| `AdherenceFlag` | Monitor | Informational + flags; future: drive cutback events. |
| `EasyPaceDrift` | Monitor | Informational; future: `FatigueFlag` coupling. |
| `MissedQuality` | Monitor | Informational; future: recovery / deload. |
| `LongRunIncomplete` | Monitor | Informational; future: cap next LR. |
| `FatigueFlag` / `OverreachFlag` | Monitor | Composite signals; future: merge policy → `Difficulty` or `Injury`. |

## LLM and coach approval

- NL-derived events enter as `status=proposed` (`llm/boundary.py`). Coach review may set `rejected` (ignored by fold) without deleting rows.
- `python main.py propose-notes` stores the raw text as an applied `CoachNote`, then appends proposed events; `python main.py interpret-activities` does the same for Strava activity text from `training.jsonl`. `python main.py review` approves/rejects proposals and runs `replan` when anything is approved. Non-interactive approval: **`--yes-all`**, or env **`Z2TC_REVIEW_AUTO=all`** (same as `--yes-all`; scripts/CI only).
- **Dossier → proposed events (never silent):** `python main.py athlete-report --propose` turns the dossier's data-backed `ProposedInput`s (`engine/athlete_profile.proposed_inputs`) into `proposed` `ManualOverride` events plus one applied `CoachNote` capturing the rationale as an audit trail. The dossier informs plan creation only through the same `review` gate — it never mutates inputs on its own. Without `--propose`, `athlete-report` just prints the proposals.
- Orchestrator or coach tool flips to `approved` then re-runs `replan`.
- The LLM **never** outputs paces or weekly miles as authority — only structured event payloads validated against [`store/events.py`](../../store/events.py). `RaceEstimate` VDOTs and detraining are recomputed in code from distance + time; `WeeklyEvaluation` with `easy_pace_override_s` and no `calibrated_vdot` gets VDOT from Daniels easy midpoint via `engine/paces.py`.
- **Gemini (optional):** set `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Optional `Z2TC_GEMINI_MODEL` (default `gemini-3.5-flash`). Tests / offline: `Z2TC_DISABLE_GEMINI=1` forces the stub path; `Z2TC_LLM_STUB_EVENTS_JSON` is a JSON array of payload objects for deterministic tests. Live extraction prepends **date context** (today’s UTC calendar date plus the athlete’s goal-race window from the survey baseline) to steer ISO dates.
- **Date normalization (extraction only):** In `extract_events`, after payloads parse, grounded calendar fields (`_payload_date_fields`) that are **parseable** and **outside** the plausibility window are **rewritten** to a deterministic in-window ISO date (`normalize_payload_calendar_dates` in `llm/boundary.py`): prefer the same month-day when it exists inside the window for some calendar year; otherwise clamp to the window edge (`lo` if before, `hi` if after); `week_start` is then the **Monday in the window** minimizing distance to that resolved day (tie-break: earlier ISO Monday). `Unavailable` `start`/`end` are repaired if normalization inverts the range. Each rewrite prints **`Date normalized …`** to **stderr** (`was` / `now`). **`Date flag`** after this step is only for dates still outside the window (should be rare once parseable); monitor `week_start` payloads are **not** in `_payload_date_fields` and are unchanged.
- **`review`:** Recomputes the window from the saved survey baseline. Rows in SQLite are **not** auto-rewritten here — only **`!! date warning`** lines on **stdout** before each prompt for parseable dates still outside the window on grounded kinds (`WeeklyEvaluation`, `RaceEstimate`, `EffortQuality`, `DataExclude`, `FitnessAnchor` with `race_date`, `SetRaceDate`, `Unavailable`). No auto-reject. Monitor-generated flags (`AdherenceFlag`, `EasyPaceDrift`, `FatigueFlag`, `OverreachFlag`) are **not** date-grounded.

## Related

- [overview.md](overview.md)
- [feeds-and-analysis.md](feeds-and-analysis.md)
- [Intake vs engine](../intake-and-engine.md)
