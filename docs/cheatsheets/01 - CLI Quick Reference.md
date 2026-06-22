# CLI quick reference

All commands: `python main.py <command> …` from repo root. Global option: `--state-path PATH` (default `auth/strava_state.json`).

## `pull-intake`

Read the linked **Intake_responses** tab from the club workbook (Sheets API). Non-empty cells overlay a **defaults** `SurveyInputs` JSON (use Strava / `marathon-report` numerics there).

```bash
python main.py pull-intake --defaults tests/fixtures/survey_kelly.json --match-name Kelly --out /tmp/kelly_merged.json
python main.py pull-intake --defaults path/to/strava_fill.json --match-strava-id 42251408 --tab Intake_responses
```

Defaults path is required. At least one of `--match-name` or `--match-strava-id`. Tab defaults to `Intake_responses`; spreadsheet defaults to `Z2TC_CLUB_SPREADSHEET_ID` or the canonical club workbook.

## `nyrr-races`

Official chip times from the same RMS API used by [results.nyrr.org](https://results.nyrr.org/) (read-only). Sends a browser-like `User-Agent` (the settings endpoint blocks the default Python UA).

```bash
python main.py nyrr-races --search "Kelly Hession"
python main.py nyrr-races --search "Jane Doe" --include-virtual
```

Merge Strava `marathon-report` + NYRR into `SurveyInputs` before `build-plan`:

```bash
python scripts/merge_report_nyrr_survey.py --base /tmp/intake.json \\
  --report output/kelly_strava/report_42251408.json \\
  --training output/kelly_strava/training_42251408.jsonl \\
  --nyrr-search "Kelly Hession" -o /tmp/survey_merged.json
```

## Multi-engine comparison (`scripts/compare_cindy_plans.py`)

Raw survey vs SQLite event-folded inputs, all four methods (forced programs for Higdon/Hanson columns):

```bash
PYTHONPATH=. python scripts/compare_cindy_plans.py
PYTHONPATH=. python scripts/compare_cindy_plans.py --athlete-id kelly-hession
```

## `login`

One-time headed browser Strava login; saves Playwright storage state.

```bash
python main.py login
```

## `check`

Verify saved session still works (headless).

```bash
python main.py check
```

## `scrape <athlete_ids…>`

Profile feed → JSONL (default `output/athletes.jsonl`).

```bash
python main.py scrape 12345 67890
python main.py scrape 12345 --headed --debug --max-workouts 30 --delay 4 --out output/run1.jsonl
```

## `training <athlete_id>`

ISO-week history `--start` .. `--end` (required dates `YYYY-MM-DD`).

```bash
python main.py training 42251408 --start 2025-06-09 --end 2025-11-09
python main.py training 42251408 --start 2025-01-01 --end 2026-06-14 --out output/training.jsonl --delay 1.0 --headed
```

## `analyze`

Read `training.jsonl`, print calendar/stats, write summary JSON.

```bash
python main.py analyze --in output/training.jsonl --out output/training_summary.json
python main.py analyze --in output/training.jsonl --no-calendar
```

## `marathon-report <athlete_ids…>`

Wide scrape + latest-marathon block report per athlete.

```bash
python main.py marathon-report 135690507 107176083 --scan-start 2025-01-01
python main.py marathon-report 61628075 --scan-start 2025-01-01 --end 2026-06-12 --block-weeks 18 --out-dir output/marathon --delay 0.6 --headed
```

Defaults: `--scan-start` 2025-01-01, `--end` today, `--block-weeks` 20, `--out-dir` `output/marathon`.

## `ingest-style`

Harvest sampled fonts/fills from the club spreadsheet (Sheets API + Hermes token). Writes `style_spec` + `spreadsheet_id` JSON for `publish-sheet`.

```bash
python main.py ingest-style
python main.py ingest-style --spreadsheet-id <id> --out output/club_workbook_style.json
```

Flags: `--include-harvest` (embed full grid sample), `--llm-assist` (reserved; no live LLM in-repo).

Env: `Z2TC_CLUB_SPREADSHEET_ID` overrides the default club workbook id.

## `build-plan <athlete_id>`

Persist `SurveyInputs` JSON as the athlete baseline, run `build_plan`, save `PlanArtifact` to `output/z2tc.db` (override with `--db`).

```bash
python main.py build-plan 42251408 --survey path/to/survey.json
python main.py build-plan 42251408 --survey survey.json --strava-id 42251408 --db /tmp/z.db
```

## `replan <athlete_id>`

Load the saved survey baseline + append-only events (skips `status=proposed` and `rejected`), fold inputs, `build_plan`, save a new artifact.

```bash
python main.py replan 42251408
```

## `monitor <athlete_id> --training PATH`

Latest stored plan vs `training.jsonl` weekly run miles → `AdherenceFlag` / monitor payloads appended as `applied` Strava-sourced events.

```bash
python main.py monitor 42251408 --training output/marathon/training_42251408.jsonl
```

## `coach-note <athlete_id>`

Append a coach observation, or an **effort-corrected race estimate**, to the event log. A plain note is provenance only (surfaces as a `coach_note` flag). A race estimate computes the trained-peak VDOT the effort really showed and detrains it to today (Daniels Table 15.1); the next `replan` folds the `effective_vdot` into `vdot`. `--break-days` defaults to the athlete's `recent_break_days`.

```bash
# free-text note
python main.py coach-note 128394498 --text "Watch left achilles"

# a marathon run sick / aimed faster — re-anchor fitness, then apply
python main.py coach-note 128394498 \
  --race-name "Melbourne Marathon" --race-date 2025-10-11 \
  --distance marathon --estimated-time 3:55:00 --actual-time 4:00:25 \
  --text "Food poisoning; clean effort ~3:55"
python main.py replan 128394498
```

## `propose-notes <athlete_id>` / `interpret-activities <athlete_id>` / `review <athlete_id>`

Human-in-the-loop interpretation: store **raw** text as an applied `CoachNote` (audit trail), then append LLM **`proposed`** events (`llm/boundary.py`). `review` approves or rejects each proposal; on any approval, saves a new plan artifact via `replan`.

- **Gemini:** set `GEMINI_API_KEY` or `GOOGLE_API_KEY`; optional `Z2TC_GEMINI_MODEL` (default `gemini-3.5-flash`). Offline / CI: `Z2TC_DISABLE_GEMINI=1` and optional `Z2TC_LLM_STUB_EVENTS_JSON` (JSON array of event payloads).
- **Easy pace → VDOT:** a proposed `WeeklyEvaluation` with `easy_pace_override_s` and no `calibrated_vdot` gets `calibrated_vdot` filled from Daniels easy midpoint (`engine/paces.vdot_from_easy_pace`).

- **Non-interactive `review`:** `--yes-all` approves all proposals without prompts. Same behavior with env **`Z2TC_REVIEW_AUTO=all`** (scripts / trusted CI only).

```bash
python main.py propose-notes 128394498 --text "Easy pace is 9:30/mi this block; bump calibration."
python main.py interpret-activities 128394498 --training output/marathon/training_128394498.jsonl --weeks 4
python main.py review 128394498
python main.py review 128394498 --yes-all   # non-interactive: approve all, then replan
```

## `mark-race <athlete_id>` / `fitness-select <athlete_id>`

Coach **data-interpretation directives** and the resolver that turns them into the fitness VDOT. `mark-race` tags a race's effort or excludes it; `fitness-select` chooses the fitness source from the report's candidate races + recorded directives (`EffortQuality`/`DataExclude`/`RaceEstimate`), detrains it (Table 15.1), and with `--apply` writes a `FitnessAnchor` the next `replan` folds.

```bash
# tag the soft tune-ups so they stop setting fitness
python main.py mark-race 128394498 --race-date 2026-04-26 --quality submaximal
python main.py mark-race 128394498 --race-date 2026-06-06 --quality submaximal

# resolve fitness, anchoring the (coach-estimated) marathon, then apply + replan
python main.py fitness-select 128394498 --anchor-date 2025-10-11 --apply
python main.py replan 128394498
```

`--exclude` on `mark-race` drops a bad data point; `fitness-select --report PATH` overrides the default `output/marathon/report_<strava-id>.json`.

## `publish-sheet <athlete_id>`

Render latest `PlanArtifact` to a tab using the style bundle from `ingest-style` (default `--style-bundle output/club_workbook_style.json`).

```bash
python main.py publish-sheet 42251408 --sheet-title "Plan_Jane"
```

## `scripts/book_search.py` — cite the source books

Page-indexed search over the four training books (Daniels, Pfitzinger, Hanson, Higdon), plus the engine's curated, page-verified citations.

```bash
python scripts/book_search.py build                       # one-time text cache (all books)
python scripts/book_search.py search "long run" --book hanson
python scripts/book_search.py page --book daniels --page 64
python scripts/book_search.py cite long-run               # the long-run time-window citations the engine encodes
```

## Related

- [`README.md`](../../README.md) — setup, responsible use, longer examples.
- [`docs/architecture/feeds-and-analysis.md`](../architecture/feeds-and-analysis.md) — pipeline detail.
