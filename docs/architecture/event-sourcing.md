# Event sourcing and replan contract

This document is the **contract** between the Strava monitor, Sheet read-back, the typed LLM boundary, and the deterministic plan engine. Numbers always come from code; events only **parameterize** a re-derivation.

## Model

- **Baseline** — `SurveyInputs` / `AthleteInputs` at intake (§0 inputs).
- **Append-only log** — `events` table (`store/db.py`): each row has `event_type`, `payload_json`, `source`, `status`, `ts`.
- **Replan** — `replan(baseline, store, athlete_id)` in [`engine/plan/replan.py`](../../engine/plan/replan.py) folds **approved** and **applied** events (skips `proposed`) into a working `AthleteInputs`, then calls `build_plan`. Pure math stays in `engine/plan/`; folding is deterministic and ordered by `ts`.

## Event catalog

| Payload kind | Source typical | Effect on baseline / plan |
|--------------|----------------|---------------------------|
| `SetDays` | Form / coach / sheet | Updates `days_per_week` (3–7). Redistributes sessions via existing `assemble_week` rules. |
| `SetGoal` | Form / coach | Updates `goal_marathon_s` (goal MP and caps follow). |
| `SetRaceDate` | Form / coach | Updates `race_date` (block anchor). |
| `TuneUpResult` | Monitor / coach | Updates `vdot` from a race or time-trial result. |
| `Injury` | Coach / LLM (approved) | Sets `injury_prone=True`; optional `days_off` recorded on plan flags (ramp rules §3c to be expanded). |
| `Difficulty` | Coach / sheet | Nudges `w_now` (volume lever, bounded); see `replan.apply_payload`. |
| `ManualOverride` | Coach | Sets a single allowed `AthleteInputs` field by name (validated). |
| `Unavailable` | Form / coach | **MVP:** recorded on plan flags only; future: week mask / reshuffle quality. |
| `AdherenceFlag` | Monitor | Informational + flags; future: drive cutback events. |
| `EasyPaceDrift` | Monitor | Informational; future: `FatigueFlag` coupling. |
| `MissedQuality` | Monitor | Informational; future: recovery / deload. |
| `LongRunIncomplete` | Monitor | Informational; future: cap next LR. |
| `FatigueFlag` / `OverreachFlag` | Monitor | Composite signals; future: merge policy → `Difficulty` or `Injury`. |

## LLM and coach approval

- NL-derived events enter as `status=proposed` (`llm/boundary.py`).
- Orchestrator or coach tool flips to `approved` then re-runs `replan`.
- The LLM **never** outputs paces or weekly miles as authority — only structured event payloads validated against [`store/events.py`](../../store/events.py).

## Related

- [overview.md](overview.md)
- [feeds-and-analysis.md](feeds-and-analysis.md)
- [Intake vs engine](../intake-and-engine.md)
