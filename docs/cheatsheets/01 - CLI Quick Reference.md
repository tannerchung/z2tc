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

Harvest sampled fonts/fills from the club spreadsheet (Sheets API + Hermes token). Caches the `style_spec` + `spreadsheet_id` bundle in the store's `config` kv (source of truth for `publish-sheet` / `publish-club`) and also writes a JSON copy.

```bash
python main.py ingest-style
python main.py ingest-style --spreadsheet-id <id> --out output/club_workbook_style.json
```

Flags: `--include-harvest` (embed full grid sample in the file copy), `--llm-assist` (reserved; no live LLM in-repo).

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

## `plan-export <athlete_id>`

Export the latest `PlanArtifact` to portable, platform-neutral artifacts under `output/export/<athlete_id>/`. Read-only on the store. Both exporters consume the same structured-workout IR (`export/structured.py`), which normalizes the engine's `Workout.segments` into steps with **pace bands** (fast/slow s/mi), preserves rep work as **repeat-loop blocks** (e.g. 5 × [1000 m @ I, 2:00 jog]), and pads quality blocks (e.g. the 4 mi @ T inside an 8 mi run) with warm-up/cool-down easy so each session's steps sum back to its total.

- `--format ics` → `<athlete_id>.ics`: an iCalendar feed (one all-day VEVENT per session; stable UIDs so re-export updates in place; rep blocks shown compactly as `N × (...)`). Subscribable in Google / Apple / Garmin Connect calendars.
- `--format fit` → `fit/*.fit`: one Garmin `.FIT` structured workout per running session, with per-step pace-target speed alerts and native repeat steps (the watch counts "rep 2 of 5"). Needs the optional `fit-tool` package (`pip install fit-tool`); cross-training days are skipped (no pace).
- `--format all` (default) writes both. `--running-only` drops cross-training from the calendar. `--out-dir` overrides the root.

```bash
python main.py plan-export kelly-hession                      # .ics + .fit under output/export/kelly-hession/
python main.py plan-export kelly-hession --format ics
python main.py plan-export kelly-hession --format fit --out-dir /tmp/garmin
```

## `publish-sheet <athlete_id>`

Render latest `PlanArtifact` to a tab using the style bundle from `ingest-style` (an explicit `--style-bundle` file wins, else the store's cached bundle; default file path `output/club_workbook_style.json`). Once `record-tune-up` results exist, each tune-up week shows an on-track/behind indicator: the race cell is tinted green (on track) / amber (B-goal) / red (behind) and the "Why" leads with the verdict (pairs landed results to tune-up weeks in order; same projection as `record-tune-up`).

`--training PATH` points at the current-block weekly feed (the same JSONL `monitor` reads). With it, every elapsed week is scored on-plan/short so the narrative gives **earned positive reinforcement** (on-plan weeks get praise in their "Why"; the notes block leads with the consistency tally) and frames shortfalls as the reason for conservative choices. Without it, the narrative uses the shortfall-only monitor events. `--llm-narrative` smooths the prose (number-safe; falls back to deterministic text without an API key).

The narrative is **personalized** from the athlete dossier and accumulating execution: the summary and "How this plan is personalized to you" reflect the responder profile (e.g. speed-dominant → durability framing, volume↔VDOT correlation, endurance gap); the notes block and per-week "Why" surface what `monitor` has seen (a week that came in short, a missed quality day, a coach `WeeklyEvaluation` note) — weeks with no signal render unchanged. `--llm-narrative` smooths the summary / personalization / notes prose via the LLM boundary; it is **number-safe** (a subset guard rejects any fabricated figure) and falls back to the deterministic text without an API key.

```bash
python main.py publish-sheet 42251408 --sheet-title "Plan_Jane"
python main.py publish-sheet 42251408 --training output/training.jsonl   # score every week → positive reinforcement
python main.py publish-sheet 42251408 --llm-narrative
```

## `athlete-report <athlete_id>`

Read-only **athlete dossier** — the deterministic, repeatable version of the manual "study the athlete's past" pass. From the last block's capacity profile + the `output/marathon/` race artifacts it reports: **demonstrated volume** (how the block actually opened, the sustainable mpw band, the peak, long-run dominance), **VDOT over time** (each race's VDOT + trailing 4-wk volume) with a **responder classification** (volume-sensitive / speed-dominant / stable / insufficient-data and the volume↔VDOT correlation), **goal realism** for A/B/C (via `goal_feasibility`), **fitness-anchor staleness**, and coach-facing **recommendations** (e.g. open near the demonstrated re-entry, treat a stretch goal as B/C, confirm a stale anchor with the tune-ups). Mutates nothing by default — `--json` emits the full dossier; `--report` / `--training` / `--strava-id` / `--marathon-dir` locate the artifacts (`engine.athlete_profile`).

`--propose` logs the dossier's data-backed input changes (the structured `ProposedInput`s, e.g. `reentry_start_mpw` anchored on the demonstrated opener) as **`proposed` `ManualOverride` events** plus one applied `CoachNote` for provenance. Nothing is applied — run `review` to fold any in. This is the dossier → plan-creation handoff: proposed events, never silent mutations.

```bash
python main.py athlete-report gaurav-goel
python main.py athlete-report cindy-kim --json
python main.py athlete-report gaurav-goel --propose      # log proposed input changes for review
```

## `narrative-log [athlete_id]`

Distillation monitor over the append-only `narrative_renders` log (written by `publish-sheet`). Per surface (summary / personalized / notes) it reports how often the optional LLM pass actually **changed** the deterministic draft (`llm_change_rate`), the mean edit size, and the guard pass rate. Surfaces flagged **`det-candidate`** (LLM seen ≥5× and changed the text <20% of the time) are candidates to drop the LLM for and keep the deterministic template; high-variance surfaces stay on the LLM. Omit `athlete_id` for fleet-wide analysis. Each record is versioned (`NARRATIVE_TEMPLATE_VERSION`, `NARRATE_PROMPT_VERSION`, model, inputs fingerprint) so output shifts trace to a template/prompt/model change. Read-only. `--surface` / `--limit` narrow the read; `--json` emits the aggregate.

```bash
python main.py narrative-log                 # fleet-wide
python main.py narrative-log cindy-kim --json
```

## `dossier-log [athlete_id]` / `plan-log`

Fleet/historical analytics over the accumulating `dossier_snapshots` and `plan_artifacts` (the "earn the engine change with data" surface). `dossier-log` reports the fleet responder distribution, anchor-staleness spread, demonstrated-opener-vs-plan gaps, and goal-realism spread; pass an `athlete_id` to see that athlete's snapshot trend across seasons. `plan-log` groups artifacts by `engine_version` / `club_policy_version` and joins them to `weekly_actuals` adherence (season-scoped attribution caveat for mid-season replans). Read-only; `--json` emits the aggregate.

```bash
python main.py dossier-log                 # fleet-wide responder / anchor / goal-realism spread
python main.py dossier-log cindy-kim --json
python main.py plan-log --json             # adherence by engine_version / club_policy_version
```

## `tune-up-plan <athlete_id>`

Forward-looking **tune-up race checkpoints** from the athlete's latest plan VDOT + goal: a short/sharp 5K (early) → 10K (mid) → 10K (race-prep) ladder, each with the week/date, the **on-track-for-goal** target time (straight line to the goal's required VDOT) and the **realistic** time (diminishing-return projection). The race-prep rung is a 10K, not a half — a half marathon that close costs the recovery a peak long-run block needs (cf. Pfitzinger/Higdon). A result at/under on-track keeps the A-goal alive; slower than realistic is the signal to re-anchor. Read-only (`engine.readiness.tune_up_ladder`); `--json` emits the full ladder.

```bash
python main.py tune-up-plan gaurav-goel
python main.py tune-up-plan gaurav-goel --json
```

## `record-tune-up <athlete_id>`

Log an **actual** tune-up race result and close the feedback loop. Computes the VDOT the effort showed (`vdot_from_race`), writes a `TuneUpResult` event (folded into the athlete's VDOT on the next `replan`), and prints the re-anchor verdict: the marathon-equivalent at this fitness, the VDOT the goal needs, and — projecting over the weeks left — whether the goal is on track or should move toward the projected-fitness equivalent. `--race-date` (ISO, defaults to today) stamps when the tune-up was run so the dossier **fitness anchor freshens** — the merged result becomes the newest race in the dossier timeline, which clears `anchor.stale` and the "confirm with a tune-up" recommendation. Assumes a genuine race effort. `--json` emits the result + verdict.

```bash
python main.py record-tune-up gaurav-goel --distance 10k --time 41:30 --race-date 2026-08-15
python main.py record-tune-up gaurav-goel --distance half --time 1:32:00 --json
python main.py replan gaurav-goel        # fold the new VDOT into the plan
```

## `publish-club`

Render the club-wide **Long Runs**, **Read Me First**, and **Workout Dictionary** tabs from every athlete's latest plan. The Long Runs grid is the **union** of every athlete's Saturdays — it spans the earliest block start and the latest race in the batch, so a longer block or a later marathon never blanks out. `Wk` is a **continuous running count** over that grid (week 1 = the first Saturday any plan starts), not a per-plan week number. Each cell is the athlete's **actual Saturday-session mileage** for the week, `26.2` on a goal-marathon race day (a marathon double shows it on both races, each anchored to its true date via `final_race_date`), and **blank** outside their block — no `recover`/`easy`/`bonus` tokens. Cells are **tinted only for the distinct cases** (goal marathon, tune-up race, recovery week) with a highlighted legend row, so a 5K/10K tune-up or a cutback week reads at a glance; ordinary long runs stay plain. **Each distinct marathon earns its own race-day band** (names/dates resolved from the plans). Phase bands and the shared `Workout` column are omitted: across mixed calendars/methods neither translates meaningfully across a row. The **Read Me** carries a "How to read this sheet" legend (columns, workout letters, phase bands, tune-up/over-capacity tinting, the slate-blue flagged-week marker, and the ~92% on-plan threshold) and a roster section built from `--athletes`. The **Workout Dictionary** is generated from the engine catalog (`engine/plan/workouts.py`) plus the pace legend and terminology in `render/workout_glossary.py`, so it never drifts from what the plans prescribe; do not hand-edit it.

```bash
python main.py publish-club                       # all athletes with a plan; spine = roster consensus race
python main.py publish-club --athletes 42251408,1234 --spine 42251408
python main.py publish-club --only readme         # regenerate just the Read Me First tab
python main.py publish-club --only dictionary     # regenerate just the Workout Dictionary tab
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
