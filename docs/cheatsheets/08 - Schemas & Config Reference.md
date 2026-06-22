# Schemas and config reference

## Inputs: `AthleteInputs`

The engine contract is `AthleteInputs` in [`engine/plan/models.py`](../../engine/plan/models.py).

**Do not duplicate** the full field matrix here — it changes with intake. Canonical mapping, required vs optional, slugs, and Strava-vs-form precedence:

- [`docs/intake-and-engine.md`](../intake-and-engine.md)

## Store: `SurveyInputs` + SQLite

- [`store/models.py`](../../store/models.py) — `SurveyInputs` (Pydantic) mirrors the engine-facing fields plus optional intake extras; `to_athlete_inputs()` drops unknown keys and builds `AthleteInputs`.
- [`store/db.py`](../../store/db.py) — default DB path `output/z2tc.db` (anchored to repo root): `athletes`, `survey_baselines`, `plan_artifacts`, `events`.
- [`store/intake_sheet.py`](../../store/intake_sheet.py) — read **Intake_responses** via Sheets API → merge with defaults → `SurveyInputs`; used by `main.py pull-intake`.

## Outputs: `TrainingPlan` tree

All in [`engine/plan/models.py`](../../engine/plan/models.py).

| Type | Purpose |
|------|---------|
| `TrainingPlan` | `athlete`, `method`, `goal` dict, `vdot`, `paces`, `peak_miles`, `block_weeks`, `weeks`, `flags`, `generated_at` |
| `PlannedWeek` | `index` (1-based), `phase`, `label`, `target_miles`, `is_down_week`, `days` (`PlannedDay` list), `flags` |
| `PlannedDay` | `day` (`DAY_NAMES`), `workout` |
| `Workout` | `kind` (`WorkoutKind`), `label`, optional `distance_mi` / `duration_min`, `pace`, `pace_s`, `segments`, `flags` |
| `Segment` | Structured reps (threshold / interval / MP blocks): `reps`, `pace_label`, `pace_s`, `distance_m`, etc. |

`WorkoutKind` drives quality detection via `QUALITY_KINDS` (threshold, interval, rep, marathon_pace, race).

## Paces dict

`training_paces(vdot)` in [`engine/paces.py`](../../engine/paces.py) returns seconds + display strings used on workouts (Easy low/high, Marathon, Threshold, Interval, Repetition).

## Config files

- `requirements.txt` — Python dependencies (Playwright, Google APIs, pytest, pydantic, PyMuPDF for table extraction scripts).

Env vars used by the Sheets path:

- `Z2TC_GOOGLE_TOKEN`, `Z2TC_GOOGLE_CLIENT_SECRET` — see [`README.md`](../../README.md).
- `Z2TC_CLUB_SPREADSHEET_ID` — club workbook for `ingest-style` / `publish-sheet` defaults.

No `config/*.json` Pydantic layer in this repo yet.

## Related

- [`docs/architecture/plan-engine.md`](../architecture/plan-engine.md)
- [`CLAUDE.md`](../../CLAUDE.md)
