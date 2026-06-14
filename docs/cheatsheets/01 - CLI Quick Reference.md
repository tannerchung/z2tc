# CLI quick reference

All commands: `python main.py <command> …` from repo root. Global option: `--state-path PATH` (default `auth/strava_state.json`).

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

Load the saved survey baseline + append-only events (skips `status=proposed`), fold inputs, `build_plan`, save a new artifact.

```bash
python main.py replan 42251408
```

## `monitor <athlete_id> --training PATH`

Latest stored plan vs `training.jsonl` weekly run miles → `AdherenceFlag` / monitor payloads appended as `applied` Strava-sourced events.

```bash
python main.py monitor 42251408 --training output/marathon/training_42251408.jsonl
```

## `publish-sheet <athlete_id>`

Render latest `PlanArtifact` to a tab using the style bundle from `ingest-style` (default `--style-bundle output/club_workbook_style.json`).

```bash
python main.py publish-sheet 42251408 --sheet-title "Plan_Jane"
```

## Related

- [`README.md`](../../README.md) — setup, responsible use, longer examples.
- [`docs/architecture/feeds-and-analysis.md`](../architecture/feeds-and-analysis.md) — pipeline detail.
