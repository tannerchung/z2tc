# Feeds and analysis

How Strava data is collected and how **`training.jsonl`** turns into calendars, stats, and **`marathon-report`** JSON (including signals that later populate `AthleteInputs`).

## Strava feed

| Module | Responsibility |
|--------|------------------|
| [`feeds/strava/session.py`](../../feeds/strava/session.py) | Playwright context, `storage_state` path (`auth/strava_state.json`), `login` / `check` helpers. |
| [`feeds/strava/athlete.py`](../../feeds/strava/athlete.py) | Profile page → `AthleteProfile` + recent `WorkoutPost` list (`preFetchedEntries` JSON). |
| [`feeds/strava/training.py`](../../feeds/strava/training.py) | Walk ISO weeks from `start`..`end` via `/athletes/{id}/interval?interval=YYYYWW...` → `TrainingWeek` rows. |

**CLI:** `main.py scrape`, `training`, `marathon-report` (latter two call `scrape_training_history`).

**Practical notes:** group activities are de-duplicated to the profile owner; treadmill runs may lack per-activity Distance; use `--delay` between week fetches.

## Analysis stack

[`engine/analyze.py`](../../engine/analyze.py):

- **`summarize(weeks)`** — weekly run miles, longest run, races from titles, best efforts at benchmark distances.
- **`build_marathon_report`** — finds latest **Marathon** race in range, slices `block_weeks` before it, summarizes block + post-marathon window, **`recommended_vdot`** (prefers recent half when available).
- **`load_weeks`**, **`build_calendar`** — helpers for `analyze` command output.

[`engine/vdot.py`](../../engine/vdot.py) — VDOT from race performance (used by report / plan inputs).

[`engine/paces.py`](../../engine/paces.py) — table-backed Daniels training paces from VDOT.

## Mapping to `AthleteInputs` (merge layer)

The plan engine expects typed **`AthleteInputs`**. Typical sourcing:

| Field | Primary source | Notes |
|-------|----------------|-------|
| `vdot` | `recommended_vdot` from `marathon-report` (or `analyze` races) | May override with coach judgment. |
| `w_now` | Trailing ~4-week average run miles from `weekly_run_miles` | Low weeks (injury/off) may need merge policy. |
| `p_history` | **Max** weekly run miles inside the detected **last marathon block** (`training_block.weekly_run_miles`) | Demonstrated peak capacity for `peak_mileage()`. |
| `longest_run_mi` | Longest **training** run in a recent window (merge should exclude marathon race day if appropriate) | Still on model for contract completeness. |
| `goal_marathon_s`, `race_date`, `days_per_week` | Google Form (required) | See `docs/intake-and-engine.md`. |

**Race detection limits:** titles drive marathon/half classification; workout-like titles are rejected (`detect_race` in `engine/analyze.py`). If a marathon is missing from the report, widen `--scan-start` or fix activity naming.

## CLI cross-links

See [cheatsheet: CLI](../cheatsheets/01%20-%20CLI%20Quick%20Reference.md).

## See also

- [overview.md](overview.md)
- [plan-engine.md](plan-engine.md)
- [Intake vs engine](../intake-and-engine.md)
