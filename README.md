# z2tc — Zone 2 Track Club training platform

Training-data ingestion and a **deterministic** VDOT / pace / marathon-plan engine for
Zone 2 Track Club. Strava is one **feed**; the engine that turns race results into
training paces is pure, testable code (no LLM in the number path).

**Current capabilities:** Strava feed (logged-in profile + week-by-week history), an
analysis engine (calendar, mileage, race detection, VDOT, Daniels paces, marathon-block
reports), a **deterministic plan engine** (`engine/plan/`: Daniels 2Q + Pfitzinger,
Saturday long run, primary + secondary marathons on the plan object), a **local SQLite
store** with append-only events + `replan` / `monitor` glue, a typed **LLM boundary**
(stub only — no live provider), and **Google Sheets** style harvest + plan tab publish
(`render/style.py`, `render/sheets.py`). **Planned:** NYRR feed, full form→store merge.

## Architecture and documentation

- **[CLAUDE.md](CLAUDE.md)** — canonical map for agents and contributors (read order, important files, `output/` layout).
- **[AGENTS.md](AGENTS.md)** — short pointer to `CLAUDE.md` (for tools that look for `AGENTS.md`).
- **[docs/architecture/overview.md](docs/architecture/overview.md)** — layers, data-flow diagram, implemented vs planned.
- **[docs/architecture/plan-engine.md](docs/architecture/plan-engine.md)** — `build_plan`, formulas, generators, tests.
- **[docs/architecture/feeds-and-analysis.md](docs/architecture/feeds-and-analysis.md)** — Strava feed, `analyze`, `marathon-report`.
- **Cheatsheets:** [CLI](docs/cheatsheets/01%20-%20CLI%20Quick%20Reference.md), [schemas](docs/cheatsheets/08%20-%20Schemas%20&%20Config%20Reference.md).

After adding or renaming paths under `engine/`, `feeds/`, or `docs/`, run `bin/check-doc-refs`.

**Athlete intake:** canonical merge policy and form→engine mapping live in
[docs/intake-and-engine.md](docs/intake-and-engine.md). Form/Sheet setup:
[docs/intake-google-form.md](docs/intake-google-form.md). Run `scripts/setup_club_intake_sheet.py`
with **python** once (Sheets auth) for the *Intake_setup* tab. To **edit the live Google Form** via API:
enable **Google Forms API** on your z2tc GCP project, run `scripts/google_oauth_z2tc.py` with **python**,
then `scripts/update_marathon_intake_form.py --dry-run` / `--apply` with **python**.

The Strava feed avoids handling your credentials entirely: you log in **manually once**
in a real browser window (email/password, 2FA, and any captcha handled by you), and the
session is saved as Playwright `storage_state` that every later run reuses.

## Responsible use

This tool drives a browser as you, against your own logged-in account. Before using
it, be aware:

- Strava's [Terms of Service](https://www.strava.com/legal/terms) restrict automated
  access/scraping. Use this only on data you're permitted to access, at low volume,
  for personal use.
- Respect other athletes' privacy and Strava's rate limits. Keep `--delay` sane and
  don't run large batches.
- You are responsible for how you use scraped data.

## Setup

Requires **Python 3.11–3.13**. Python 3.14 is not yet supported (Playwright's
`greenlet` dependency fails to build against it).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 1. Log in (one time)

```bash
python main.py login
```

A browser window opens. Log in to Strava normally. Once you land on your dashboard,
the session is captured to `auth/strava_state.json` (gitignored) and the window can
be closed. Re-run this anytime your session expires.

Verify it worked (headless, no window):

```bash
python main.py check
```

## 2. Scrape athlete profiles

An athlete ID is the number in a profile URL: `https://www.strava.com/athletes/12345`
→ `12345`.

```bash
# One or more IDs; results go to output/athletes.jsonl
python main.py scrape 12345 67890

# Watch it work in a visible browser, and dump HTML/screenshots for debugging
python main.py scrape 12345 --headed --debug

# Custom output and a longer polite delay between profiles
python main.py scrape 12345 67890 --out output/run1.jsonl --delay 4
```

Each output line is a JSON record. Workout posts are parsed from the profile's feed
micro-frontend **preFetchedEntries** JSON payload, which is richer and more stable than the
rendered DOM:

```json
{
  "athlete_id": "12345",
  "profile_url": "https://www.strava.com/athletes/12345",
  "name": "Jane Doe",
  "location": "Portland, OR",
  "followers": 412,
  "following": 388,
  "workouts": [
    {
      "activity_id": "18891743063",
      "url": "https://www.strava.com/activities/18891743063",
      "name": "Easy 30",
      "sport_type": "Run",
      "description": "Easy 3 miles with sweet G",
      "stats": { "Distance": "3.00 mi", "Pace": "10:01 /mi", "Time": "30m 8s" },
      "start_date": "2026-06-12T14:28:22Z",
      "elapsed_time_s": 2171,
      "display_date": "Today at 10:28 AM",
      "location": "Manhattan, New York",
      "kudos_count": 4,
      "comment_count": 0,
      "photo_count": 1,
      "device_name": "Garmin Forerunner 165"
    }
  ],
  "scraped_at": "2026-06-12T01:23:45+00:00"
}
```

Limit posts per athlete with `--max-workouts N` (default 20).

## 3. Reconstruct training history over a date range

The profile feed only surfaces recent posts, so for a full history (e.g. a marathon
training block) use the `training` command. It walks the profile's weekly-activities
widget one ISO week at a time, pulling each week's date label, Strava totals
(distance / time / elevation), and every activity with full detail.

```bash
# A 20-week NYC Marathon 2025 build (marathon was Nov 2, 2025)
python main.py training 42251408 --start 2025-06-09 --end 2025-11-09
```

Output is one ISO week per JSON line in `output/training.jsonl`:

```json
{
  "iso_year": 2025,
  "iso_week": 44,
  "week_start": "2025-10-27",
  "date_label": "Activities for Oct 27, 2025 - Nov 2, 2025",
  "total_distance": "36.8 mi",
  "total_time": "5h 31m",
  "total_elevation": "545 ft",
  "workouts": [ { "...": "WorkoutPost objects, oldest first" } ]
}
```

Notes:

- Activities that Strava bundles into a **group activity** (a run done with friends)
  are unpacked, and only the profile owner's activity is kept (not their friends').
- For runs without a GPS distance (e.g. treadmill), Strava reports Time as the primary
  stat, so the per-activity `Distance` may be absent even though it counts toward the
  weekly total.
- Be polite: `--delay` (default 1.0s) spaces out the weekly requests.

## 4. Analyze a training block

`analyze` reads a `training.jsonl` and prints a per-day calendar, weekly run mileage,
and best efforts at the standard race distances. It re-runs without re-scraping.

```bash
python main.py analyze --in output/training.jsonl            # calendar + stats
python main.py analyze --in output/training.jsonl --no-calendar
```

It also writes `output/training_summary.json` (`summary` + `calendar`).

### Races vs. logged runs

`analyze` reports race times two ways:

1. **Races detected from title/notes** — activities whose name/notes name a real race
   at a standard distance (e.g. `NYC MARATHON`, `Brooklyn Half`, `Grete's Gallop 10K`,
   `Turkey Trot 5K`). Workouts that only *mention* a distance as a pace target
   ("8 x 400 @ 5k pace", "marathon pace miles", "tempo @ half marathon pace") are
   rejected, as are "marathon training" long runs.
2. **Fastest logged run near each distance** — a fallback that ignores titles and just
   finds the quickest run within tolerance of each benchmark.

```
=== Races detected (from title/notes) ===
  2025-11-02  Marathon        3:51:00  (8:41 /mi, 26.70 mi)  NYC MARATHON

=== Best race times (by title/notes) ===
  Marathon        3:51:00  (8:41 /mi, 26.70 mi)  2025-11-02  NYC MARATHON

=== Stats ===
  Longest run:    26.70 mi in 3:51:00 (8:41 /mi)  2025-11-02  NYC MARATHON
  Fastest logged run near each distance (not necessarily a race):
    5K                29:29  (9:08 /mi, 3.22 mi)  2025-09-12  Afternoon Run
    ...
```

Neither uses Strava's best-effort splits (those live on each activity's
`/best-efforts` page and would require an extra fetch per run).

## 5. Auto marathon-block report (multi-athlete)

`marathon-report` does a wide scan per athlete, auto-detects the **latest marathon**,
isolates the training block (default 20 weeks before it) as its own entity, scans
everything after the marathon to today for race data (5K/10K/half/marathon), and computes
a recommended **VDOT** + Daniels training paces (preferring a recent half).

```bash
# Wide scan from 2025-01-01 to today for several athletes
python main.py marathon-report 135690507 107176083 --scan-start 2025-01-01

# Tune the block length and scan window
python main.py marathon-report 61628075 --scan-start 2025-01-01 --end 2026-06-12 --block-weeks 18
```

Writes per athlete to `output/marathon/`: `report_<id>.json` (marathons, block with full
per-day calendar, post-marathon races, recommended VDOT + paces), `training_<id>.jsonl`
(raw weeks, re-analyzable), plus a combined `marathon_reports.json`.

VDOT uses each athlete's best post-marathon half where available (most representative of
current fitness), falling back to in-block races. Race finish times come from the recap's
chip time when present ("Official time: 03:50:13"); otherwise the weekly feed's minute
precision is used.

## When fields come back `null`

Strava changes its markup frequently. If a field stops resolving, run with `--debug`
to dump `output/debug/athlete_<id>.html` and a screenshot, then update the selector
lists in `feeds/strava/athlete.py` (`scrape_athlete`, `_extract_*`).

## Project layout

```
main.py                    CLI: Strava + analysis + store/replan/monitor/Sheets
bin/
  check-doc-refs           Verify backticked repo paths in CLAUDE.md + docs
feeds/                     Data feeds (normalize external sources into the store)
  strava/session.py        Saved-session login (storage_state) management
  strava/athlete.py        Profile page → AthleteProfile + WorkoutPost records
  strava/training.py       Week-by-week history via the interval endpoint
store/                     SQLite + Pydantic (athletes, survey baselines, plans, events)
  db.py                    Store connection + CRUD
  models.py                SurveyInputs → AthleteInputs bridge, PlanArtifact, etc.
  events.py                Typed event payloads + parse_event_payload()
  serialization.py         TrainingPlan ↔ JSON for artifacts
engine/                    Deterministic training engine (pure, testable, no IO)
  vdot.py                  VDOT from a race + best-race selection (Daniels)
  paces.py                 Table-backed Daniels paces E/M/T/I/R (Table 5.2, interpolated)
  analyze.py               Calendar, weekly mileage, race detection, reports
  monitor.py               Prescribed vs actual → monitor event payloads
  plan/                    Marathon plan engine (build_plan -> TrainingPlan)
    models.py              Shared week/workout model + AthleteInputs (engine + intake fields)
    intake.py              resolve_intake_defaults() for optional form answers
    common.py              Formula blocks: method, volume, long run, caps, paces, recovery
    daniels.py             Daniels 2Q generator
    pfitzinger.py          Pfitzinger mesocycle generator
    replan.py              Fold events over baseline → build_plan
llm/
  boundary.py            Typed NL/style stubs (coach-approved proposed events)
render/                    Google Sheets (credentials + style + plan writer)
  runtime.py               Google API credential loading (reuses the Hermes token)
  style.py                 harvest_workbook_style, derive_style_spec
  sheets.py                render_plan, read_feedback_cells
docs/
  architecture/
    overview.md              System map + data flow (read after CLAUDE.md)
    plan-engine.md           build_plan, formulas, generators, tests
    feeds-and-analysis.md    Strava scrape, analyze, marathon-report
    event-sourcing.md        Event catalog ↔ engine rules
  cheatsheets/
    01 - CLI Quick Reference.md          main.py commands and flags
    08 - Schemas & Config Reference.md   TrainingPlan / AthleteInputs / store pointers
  intake-and-engine.md     Intake vs Strava vs engine (required/optional, slugs, policy)
  intake-google-form.md    Form API, Sheet linking, column order
requirements.txt
```

Planned packages as they land: **feeds/nyrr/**, **feeds/forms/** (automated merge).

## Google Sheets credentials

The renderer reuses an existing **authorized-user** token rather than running its own
OAuth consent flow. By default it reads `~/.hermes/google_token.json` (which already
grants the `spreadsheets` scope and carries a refresh token); expired tokens are
refreshed and written back automatically. Override the locations if needed:

```bash
export Z2TC_GOOGLE_TOKEN=/path/to/google_token.json
export Z2TC_GOOGLE_CLIENT_SECRET=/path/to/google_client_secret.json   # for re-consent
```

- [Intake vs engine (canonical)](docs/intake-and-engine.md)
- [Google Form / Sheets setup](docs/intake-google-form.md)
- [Architecture overview](docs/architecture/overview.md)

Quick connectivity check:

```bash
python -c "from render.runtime import whoami; print(whoami())"
```
