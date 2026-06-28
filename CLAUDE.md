# z2tc — agent / contributor guide

**Zone 2 Track Club** training platform: Strava-backed ingestion, deterministic analysis (VDOT, paces, marathon-block reports), and a **pure** marathon week engine (Daniels 2Q + Pfitzinger). The numeric plan path has **no LLM** — same `AthleteInputs` always yields the same `TrainingPlan`.

**Python:** use a **3.11–3.13** venv (see `README.md`). Playwright + `greenlet` do not support 3.14 yet.

## Read order

1. This file — scope, important paths, conventions.
2. [`docs/README.md`](docs/README.md) — docs table of contents (what each doc owns; read to avoid duplication).
3. [`docs/architecture/overview.md`](docs/architecture/overview.md) — layers and data flow.
4. Task-specific:
   - Coaching decision model (fitness vs volume, P/tiers, re-entry, goal realism, breaks) → [`docs/architecture/athlete-readiness.md`](docs/architecture/athlete-readiness.md)
   - Plan math / generators → [`docs/architecture/plan-engine.md`](docs/architecture/plan-engine.md); book-cited constants → [`docs/architecture/formula-reference.md`](docs/architecture/formula-reference.md); workout dictionary + rotation → [`docs/architecture/workout-catalog.md`](docs/architecture/workout-catalog.md)
   - Event log + replan contract → [`docs/architecture/event-sourcing.md`](docs/architecture/event-sourcing.md)
   - Scraping, `analyze`, `marathon-report` → [`docs/architecture/feeds-and-analysis.md`](docs/architecture/feeds-and-analysis.md)
   - Intake form → `AthleteInputs` contract → [`docs/intake-and-engine.md`](docs/intake-and-engine.md)
5. Cheatsheets: [`docs/cheatsheets/01 - CLI Quick Reference.md`](docs/cheatsheets/01%20-%20CLI%20Quick%20Reference.md), [`docs/cheatsheets/08 - Schemas & Config Reference.md`](docs/cheatsheets/08%20-%20Schemas%20&%20Config%20Reference.md)

## Important files

| Area | Path |
|------|------|
| CLI entry | `main.py` |
| Strava session | `feeds/strava/session.py` |
| Profile scrape | `feeds/strava/athlete.py` |
| Week-by-week history | `feeds/strava/training.py` |
| Calendar / races / reports | `engine/analyze.py` |
| VDOT from races | `engine/vdot.py` |
| Daniels pace tables | `engine/paces.py` |
| Plan entry (pure dispatch `build_plan` + club `build_club_plan`) | `engine/plan/__init__.py` |
| Club engine (house policy over the pure engine: 2 quality/week + Base ramp) | `engine/plan/club.py` |
| `AthleteInputs` + `TrainingPlan` model | `engine/plan/models.py` |
| Event-sourced replan fold | `engine/plan/replan.py` |
| Next-season baseline seeding (carry-forward) | `store/carryforward.py` |
| Prescribed vs actual monitor payloads | `engine/monitor.py` |
| Optional intake defaults | `engine/plan/intake.py` |
| Coach readiness model (goal realism, breaks, re-entry, race-time prediction) | `engine/readiness.py` |
| Athlete dossier (read-only: demonstrated volume, VDOT-over-time + responder profile, goal realism) + `proposed_inputs` → `athlete-report --propose` proposed events | `engine/athlete_profile.py` (CLI `athlete-report`) |
| Pronoun handling for the third-person coach dossier (presentation only; never reaches `AthleteInputs`) | `engine/pronouns.py` |
| Execution summary (`summarize_execution` shortfall flags; `execution_from_actuals` scores every week → positive reinforcement) | `engine/execution.py` |
| Narrative capture/versioning (deterministic-vs-LLM record + per-surface distillation stats; CLI `narrative-log`) | `engine/narrative_capture.py` |
| Personalization context (number-safe bridge to optional LLM prose smoothing) | `engine/personalization.py` |
| Shared formulas (volume, LR, caps) | `engine/plan/common.py` |
| Book citations behind engine rules (long-run time window, etc.) | `engine/plan/citations.py` |
| Daniels generator | `engine/plan/daniels.py` |
| Pfitzinger generator + ch.8 mileage spine | `engine/plan/pfitzinger.py`, `engine/plan/pfitz_grids.py` |
| Higdon grids + generator | `engine/plan/higdon_grids.py`, `engine/plan/higdon.py` |
| Hansons generator + mileage spine | `engine/plan/hanson_grids.py`, `engine/plan/hanson.py` |
| Coach/program recommender | `engine/plan/recommend.py` |
| SOS catalog (extend per coach) | `engine/plan/workouts.py` |
| Nutrition pointers + `book_search.py cite nutrition` | `engine/plan/nutrition.py` |
| SQLite store + schema | `store/db.py` |
| Store Pydantic models | `store/models.py` |
| Event vocabulary + `parse_event_payload` | `store/events.py` |
| Historical training-block snapshot + demonstrated-capacity profile (athlete profiling; **not** wired into the engine) | `engine/analyze.py` (`compute_capacity_profile`), `store/models.py` (`TrainingBlock`), `store/db.py` (`save_/list_/latest_training_block`) |
| NYRR RMS API (chip times) | `lib/data_feeds/nyrr.py` |
| RTRT.me live-results client (chip times) | `lib/data_feeds/rtrt.py` |
| Race → results-API catalog (provider/slug lookup for chip feeds) | `lib/data_feeds/race_catalog.py` |
| Official marathon date lookup | `lib/marathon_calendar.py` |
| Intake Sheet → `SurveyInputs` reader | `store/intake_sheet.py` |
| Plan JSON serde | `store/serialization.py` |
| Typed LLM boundary (stub) | `llm/boundary.py` |
| Sheets style harvest + `StyleSpec` bridge | `render/style.py` |
| Sheets plan writer + feedback read | `render/sheets.py` |
| Coach-facing plan brief (method choice, P, paces, flags preamble) | `render/plan_brief.py` |
| Stacked "workout card" cell renderer (warm-up / main / cool-down from the cell label) | `render/workout_cell.py` |
| Workout pace/effort glossary + legend (shared by the dictionary tab and cells) | `render/workout_glossary.py` |
| Club "Long Runs" tab (union of athlete plans on a shared Saturday calendar; divergent-race tokens) | `render/long_runs.py` |
| Club "Read Me First" orientation tab generator | `render/read_me.py` |
| Club "Workout Dictionary" tab (engine-generated from the catalog + glossary) | `render/workout_dictionary.py` |
| Plan-engine regression/determinism tests (Kelly fixture) | `tests/test_plan.py` |
| Intake default tests | `tests/test_intake_defaults.py` |
| Docs table of contents | `docs/README.md` |
| Intake ↔ engine contract (canonical) | `docs/intake-and-engine.md` |
| Google Form / Sheets ops | `docs/intake-google-form.md` |
| Architecture map | `docs/architecture/overview.md` |
| Readiness → plan decision model | `docs/architecture/athlete-readiness.md` |
| Plan engine deep-dive | `docs/architecture/plan-engine.md` |
| Book-cited formula provenance | `docs/architecture/formula-reference.md` |
| Page-indexed book search (citations) | `scripts/book_search.py` |
| Event-sourcing contract | `docs/architecture/event-sourcing.md` |
| Sheets credential helper | `render/runtime.py` |
| Form / Sheet / table scripts | `scripts/google_oauth_z2tc.py`, `scripts/setup_club_intake_sheet.py`, `scripts/update_marathon_intake_form.py`, `scripts/extract_daniels_tables.py`, `scripts/run_kelly_demo.py`, `scripts/merge_report_nyrr_survey.py`, `scripts/import_all_athletes.py`, `scripts/backfill_db.py`, `scripts/compare_cindy_plans.py`, `scripts/book_search.py` |
| One-off store migration (pre-season → season-scoped schema) | `scripts/migrate_db_to_seasons.py` |
| Workout-naming harvest + sheet-format samplers | `scripts/read_runna_calendar.py`, `scripts/retro_reflow_why.py`, `scripts/sample_workout_format.py` |
| Book citation search (Daniels/Pfitz/Hanson/Higdon PDFs; `cite` subcommand) | `scripts/book_search.py` |
| Dependency pin | `requirements.txt` |
| Doc path verifier | `bin/check-doc-refs` |

## What `output/` stores (generated artifacts)

Not version-controlled; layout depends on commands run:

- `output/athletes.jsonl` — `scrape` (one JSON object per athlete line).
- `output/training.jsonl` — default path for `training` (one ISO week per line).
- `output/training_summary.json` — `analyze` summary + calendar.
- `output/marathon/` — default `--out-dir` for `marathon-report`: `training_<id>.jsonl`, `report_<id>.json`, `marathon_reports.json`.
- `output/z2tc.db` — default SQLite store for athletes, survey baselines, `plan_artifacts` (with `engine_version`), append-only `events`, `training_blocks` (durable per-athlete history snapshots: raw scraped weeks + report + a demonstrated-capacity `profile`, keyed per marathon; also backs the dossier's race/feed history), append-only `narrative_renders` (deterministic-vs-LLM narrative capture for the distillation loop, linked to `plan_artifact_id`), append-only `publications` (plan-artifact → published sheet lineage), `weekly_actuals` (per-week run miles, upsert per `(season, week_start)`, so execution scoring replays from the store; written by `monitor` / `publish-sheet --training`), and a `config` kv (e.g. the cached club style bundle under `STYLE_BUNDLE_KEY`). `store/db.py`, `SCHEMA_VERSION` ↔ `PRAGMA user_version`; column adds handled by `_migrate()`.
- `output/club_workbook_style.json` — optional file copy of the `ingest-style` bundle (`style_spec` + `spreadsheet_id`). The store's `config` kv is the source of truth; `publish-sheet` / `publish-club` use an explicit `--style-bundle` file when present, else fall back to the store.
- Custom directories (e.g. per-athlete runs) follow the same per-file naming inside the chosen `--out-dir`. after `login`, Strava cookies live under `auth/` as Playwright storage state (see `feeds/strava/session.py`).

## Conventions

- **Determinism:** `engine/plan` is pure; regression tests lock behavior (same inputs → same plan). `engine.plan.ENGINE_VERSION` versions that behavior — bump it (with the updated `tests/test_plan.py` fixtures) when `build_plan` output can change for the same inputs; it's stamped onto every `plan_artifacts.engine_version`.
- **Club seam:** the per-coach generators in `engine/plan/` (Daniels, Pfitzinger, Hanson, Higdon) stay **pure/textbook**. Any cross-cutting coaching behavior that isn't one coach's own rule — i.e. anything *outside the coach engines* — must be wired into the **club engine** (`engine/plan/club.py`, `apply_club_policy`), not bolted onto a single generator or only the render layer. Production always builds through `build_club_plan` / `apply_club_policy` (`build-plan`, `start-season`, `replan`, `resolve_inputs`), so add new club-wide policy there as a resolvable default a coach override can still win over (mirror `weekday_quality_sessions`). New plan-affecting features belong here. Cross-cutting placement that must work for *every* method (e.g. seating tune-up races into the plan) is a **club post-process over the built plan** (`place_tune_up_races`, run by `build_club_plan`), not per-generator code — and it should defer to a method that already covers the behavior natively (Pfitzinger/Higdon prescribe their own tune-up races) rather than double up.
- **Strava:** manual login once; reuse `storage_state`; keep `--delay` reasonable.
- **Intake:** optional form fields are filled by `resolve_intake_defaults()` before `build_plan()`; full merge (Sheet row → `AthleteInputs`) is still a documented contract, not a single module.
- **Anti-duplication:** do not copy the full intake field matrix into other docs — link `docs/intake-and-engine.md`. CLI flag tables live in the cheatsheet; README keeps narrative + links.

After renames or new first-class modules, run `bin/check-doc-refs`.
