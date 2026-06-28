# Schemas and config reference

## Inputs: `AthleteInputs`

The engine contract is `AthleteInputs` in [`engine/plan/models.py`](../../engine/plan/models.py).

**Do not duplicate** the full field matrix here — it changes with intake. Canonical mapping, required vs optional, slugs, and Strava-vs-form precedence:

- [`docs/intake-and-engine.md`](../intake-and-engine.md)

## Store: `SurveyInputs` + SQLite

- [`store/models.py`](../../store/models.py) — `SurveyInputs` (Pydantic) mirrors the engine-facing fields plus optional intake extras; `to_athlete_inputs()` drops unknown keys and builds `AthleteInputs`.
- [`store/db.py`](../../store/db.py) — default DB path `output/z2tc.db` (anchored to repo root): `athletes`, `seasons`, `survey_baselines`, `plan_artifacts`, `events`, `training_blocks`, `narrative_renders`, `publications`, `dossier_snapshots`. `SCHEMA_VERSION` is stamped into SQLite's `PRAGMA user_version`; column additions to existing tables run idempotently in `_migrate()` on open. `plan_artifacts.engine_version` records the `engine.plan.ENGINE_VERSION` that produced the plan (`None` for pre-versioning rows) and `plan_artifacts.club_policy_version` records the `ClubPolicy().version` in force, so a plan stays attributable to both the engine and the house policy that built it (queried via `Store.list_plan_artifacts`).
- **Dossier snapshots (fleet substrate):** `dossier_snapshots` is an append-only longitudinal record of each computed `AthleteDossier` (written by `athlete-report` and `publish-sheet`): `id, athlete_id, season_id, computed_at, dossier_version, inputs_fingerprint, full_json` plus flattened query columns (`responder`, `demonstrated_opener_mpw`, `peak_mpw`, `sustainable_low/high_mpw`, `volume_vdot_corr`, `endurance_gap`, `current_vdot`, `anchor_age_days`, `anchor_stale`, `injury_prone`). `engine.athlete_profile.DOSSIER_VERSION` stamps each row (bump when responder thresholds / `FRESH_ANCHOR_DAYS` / volume math change). `Store.append_/list_dossier_snapshots`; the `dossier-log` and `plan-log` CLIs read this substrate fleet-wide so engine/policy changes can be *earned* from accumulated data.
- **Lineage:** `narrative_renders.plan_artifact_id` links each captured narrative to the plan it described; `publications` records each `publish-sheet` (plan artifact → spreadsheet/sheet/url + engine/template/prompt/model versions + `narrative_source`). Read via `Store.list_publications(athlete, plan_artifact_id=…)`.
- **Weekly actuals:** `weekly_actuals` persists per-week run miles (`week_start` → miles, upsert keyed by `(season, week_start)`) so execution scoring (`engine.execution.execution_from_actuals`) is replayable from the store. Written by `monitor` and by `publish-sheet --training`; `publish-sheet` falls back to these stored actuals when no feed is supplied. `Store.upsert_/load_weekly_actuals`.
- **Config kv:** `config` (`key` → JSON `value`) holds club-wide settings. `ingest-style` folds the style bundle (`style_spec` + `spreadsheet_id`) in under `STYLE_BUNDLE_KEY`; `publish-sheet` / `publish-club` resolve it via `main._load_style_bundle` (explicit `--style-bundle` file wins, else the store). The `output/club_workbook_style.json` file is now an optional copy/override, not the source of truth. `Store.get_/set_config`.
- [`store/intake_sheet.py`](../../store/intake_sheet.py) — read **Intake_responses** via Sheets API → merge with defaults → `SurveyInputs`; used by `main.py pull-intake`.

## Club policy: `ClubPolicy`

House defaults live only in [`engine/plan/club.py`](../../engine/plan/club.py) (`ClubPolicy` + `apply_club_policy`); production builds club plans. Override-able `AthleteInputs` fields are **tri-state** (`None` = unset → club resolves; explicit value wins): `weekday_quality_sessions`, `base_quality_ramp`, `long_run_share_cap`, `aggressive_volume_ramp`, `tune_up_races`. Current policy: 2 weekday quality + Base ramp, `long_run_share_cap = 0.50`, `allow_aggressive_ramp = False` (textbook 3-wk hold; coach opts in), `schedule_tune_ups = True` (short/sharp 5K/10K/10K ladder when the goal needs verifying — no half near the goal; `TuneUpRace` specs seated by the club post-process `place_tune_up_races`, which annotates native Pfitzinger/Higdon races instead of double-scheduling). Bump `ClubPolicy.version` when rules change.

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

`training_paces(vdot)` in [`engine/paces.py`](../../engine/paces.py) returns seconds + display strings used on workouts (Easy low/high, Marathon, Threshold, Interval, Repetition). Here `marathon`/`marathon_s` are **VDOT-derived** (current fitness).

`build_plan` ([`engine/plan/__init__.py`](../../engine/plan/__init__.py)) then augments `plan.paces` with **goal-driven** marathon pace — `marathon_goal` / `marathon_goal_s` (the goal finish time ÷ marathon distance). Workouts and the pace card render `marathon_goal`; the gap between `marathon_goal_s` and `threshold_s` drives the goal-realism cautions. Keep the two distinct — never overwrite the VDOT `marathon` with the goal pace.

## Config files

- `requirements.txt` — Python dependencies (Playwright, Google APIs, pytest, pydantic, PyMuPDF for table extraction scripts).

Env vars used by the Sheets path:

- `Z2TC_GOOGLE_TOKEN`, `Z2TC_GOOGLE_CLIENT_SECRET` — see [`README.md`](../../README.md).
- `Z2TC_CLUB_SPREADSHEET_ID` — club workbook for `ingest-style` / `publish-sheet` defaults.

No `config/*.json` Pydantic layer in this repo yet.

## Related

- [`docs/architecture/plan-engine.md`](../architecture/plan-engine.md)
- [`CLAUDE.md`](../../CLAUDE.md)
