# Plan engine

Deterministic marathon block builder: **VDOT → paces → weekly structure** (Daniels 2Q or Pfitzinger mesocycles). Club long run day is **Saturday** (`common.LONG_RUN_DAY`).

## Entry point

[`engine/plan/__init__.py`](../../engine/plan/__init__.py) exports `build_plan`:

1. `resolve_intake_defaults(inputs)` — fills optional preference slugs (`engine/plan/intake.py`).
2. `assign_method(inputs)` — auto `daniels` vs `pfitzinger` from `p_history` + `days_per_week` (override via `inputs.method`).
3. `training_paces(inputs.vdot)` — Daniels table-backed paces (`engine/paces.py`).
4. Dispatch to `build_daniels_plan` or `build_pfitzinger_plan`.

## Shared building blocks

[`engine/plan/common.py`](../../engine/plan/common.py) holds transcribed formula reference logic:

- Method assignment, peak mileage (`max(p_history, w_now)`), weekly volume progression, taper fractions.
- Daniels long-run time/share cap, session caps (T/M/I/R), MP from goal time, recovery constants.
- `assemble_week` — maps `days_per_week` to Mon..Sun template with fixed quality / LR slots.

## Generators

| Module | Structure |
|--------|-----------|
| [engine/plan/daniels.py](../../engine/plan/daniels.py) | 2Q-style: two qualities in build weeks (threshold / intervals + Saturday long with MP finish where applicable), every 4th week down. |
| [engine/plan/pfitzinger.py](../../engine/plan/pfitzinger.py) | Mesocycle-style progression with medium-long + Saturday long. |

Both emit the same [`PlannedWeek`](../../engine/plan/models.py) / [`Workout`](../../engine/plan/models.py) vocabulary for renderers and tests.

## Model

[`engine/plan/models.py`](../../engine/plan/models.py):

- **`AthleteInputs`** — engine contract; includes optional Google Form fields (see intake doc).
- **`TrainingPlan`** — athlete name, method, goal payload, paces snapshot, `weeks`, `flags`, `generated_at`.

Secondary marathons: `secondary_races` + `training_plan_goal_payload` / `secondary_marathon_flags` (ordering hints; block still keys off primary `race_date`).

## Tests as spec anchor

[`tests/test_plan.py`](../../tests/test_plan.py):

- **Kelly §7** — long-run formula determinism (`test_kelly_long_run_formula`).
- Method assignment matrix, volume progression, caps, recovery days, full-plan smoke (Daniels + Pfitzinger), determinism, Saturday LR, secondary marathon flags.

[`tests/test_intake_defaults.py`](../../tests/test_intake_defaults.py) — optional intake slug defaults.

## Intake boundary

Engine does **not** scrape Strava or read Google Sheets. Intake merge policy and field matrix: [`docs/intake-and-engine.md`](../intake-and-engine.md).

## See also

- [overview.md](overview.md) — system context.
- [feeds-and-analysis.md](feeds-and-analysis.md) — where `vdot`, `w_now`, `p_history` are produced before merge.
