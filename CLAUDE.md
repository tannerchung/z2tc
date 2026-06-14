# z2tc — agent / contributor guide

**Zone 2 Track Club** training platform: Strava-backed ingestion, deterministic analysis (VDOT, paces, marathon-block reports), and a **pure** marathon week engine (Daniels 2Q + Pfitzinger). The numeric plan path has **no LLM** — same `AthleteInputs` always yields the same `TrainingPlan`.

**Python:** use a **3.11–3.13** venv (see `README.md`). Playwright + `greenlet` do not support 3.14 yet.

## Read order

1. This file — scope, important paths, conventions.
2. [`docs/architecture/overview.md`](docs/architecture/overview.md) — layers and data flow.
3. Task-specific:
   - Plan math / generators → [`docs/architecture/plan-engine.md`](docs/architecture/plan-engine.md)
   - Event log + replan contract → [`docs/architecture/event-sourcing.md`](docs/architecture/event-sourcing.md)
   - Scraping, `analyze`, `marathon-report` → [`docs/architecture/feeds-and-analysis.md`](docs/architecture/feeds-and-analysis.md)
   - Intake form → `AthleteInputs` contract → [`docs/intake-and-engine.md`](docs/intake-and-engine.md)
4. Cheatsheets: [`docs/cheatsheets/01 - CLI Quick Reference.md`](docs/cheatsheets/01%20-%20CLI%20Quick%20Reference.md), [`docs/cheatsheets/08 - Schemas & Config Reference.md`](docs/cheatsheets/08%20-%20Schemas%20&%20Config%20Reference.md)

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
| Plan entry | `engine/plan/__init__.py` |
| `AthleteInputs` + `TrainingPlan` model | `engine/plan/models.py` |
| Event-sourced replan fold | `engine/plan/replan.py` |
| Prescribed vs actual monitor payloads | `engine/monitor.py` |
| Optional intake defaults | `engine/plan/intake.py` |
| Shared formulas (volume, LR, caps) | `engine/plan/common.py` |
| Daniels generator | `engine/plan/daniels.py` |
| Pfitzinger generator | `engine/plan/pfitzinger.py` |
| SQLite store + schema | `store/db.py` |
| Store Pydantic models | `store/models.py` |
| Event vocabulary + `parse_event_payload` | `store/events.py` |
| Plan JSON serde | `store/serialization.py` |
| Typed LLM boundary (stub) | `llm/boundary.py` |
| Sheets style harvest + `StyleSpec` bridge | `render/style.py` |
| Sheets plan writer + feedback read | `render/sheets.py` |
| Golden tests (incl. Kelly §7 anchor) | `tests/test_plan.py` |
| Intake default tests | `tests/test_intake_defaults.py` |
| Intake ↔ engine contract (canonical) | `docs/intake-and-engine.md` |
| Google Form / Sheets ops | `docs/intake-google-form.md` |
| Architecture map | `docs/architecture/overview.md` |
| Plan engine deep-dive | `docs/architecture/plan-engine.md` |
| Event-sourcing contract | `docs/architecture/event-sourcing.md` |
| Sheets credential helper | `render/runtime.py` |
| Form / Sheet / table scripts | `scripts/google_oauth_z2tc.py`, `scripts/setup_club_intake_sheet.py`, `scripts/update_marathon_intake_form.py`, `scripts/extract_daniels_tables.py` |
| Dependency pin | `requirements.txt` |
| Doc path verifier | `bin/check-doc-refs` |

## What `output/` stores (generated artifacts)

Not version-controlled; layout depends on commands run:

- `output/athletes.jsonl` — `scrape` (one JSON object per athlete line).
- `output/training.jsonl` — default path for `training` (one ISO week per line).
- `output/training_summary.json` — `analyze` summary + calendar.
- `output/marathon/` — default `--out-dir` for `marathon-report`: `training_<id>.jsonl`, `report_<id>.json`, `marathon_reports.json`.
- `output/z2tc.db` — default SQLite store for athletes, survey baselines, `plan_artifacts`, append-only `events` (`store/db.py`).
- `output/club_workbook_style.json` — cached `ingest-style` bundle (`style_spec` + `spreadsheet_id`) for `publish-sheet`.
- Custom directories (e.g. per-athlete runs) follow the same per-file naming inside the chosen `--out-dir`. after `login`, Strava cookies live under `auth/` as Playwright storage state (see `feeds/strava/session.py`).

## Conventions

- **Determinism:** `engine/plan` is pure; golden tests lock behavior.
- **Strava:** manual login once; reuse `storage_state`; keep `--delay` reasonable.
- **Intake:** optional form fields are filled by `resolve_intake_defaults()` before `build_plan()`; full merge (Sheet row → `AthleteInputs`) is still a documented contract, not a single module.
- **Anti-duplication:** do not copy the full intake field matrix into other docs — link `docs/intake-and-engine.md`. CLI flag tables live in the cheatsheet; README keeps narrative + links.

After renames or new first-class modules, run `bin/check-doc-refs`.
