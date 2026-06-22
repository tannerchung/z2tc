# Plan engine

Deterministic marathon block builder: **VDOT → paces → weekly structure** (Daniels 2Q, Pfitzinger, Higdon, or Hansons). Club long run day is **Saturday** for Daniels/Pfitzinger; **Sunday** long in the Hansons layout matches ch.4’s published week shape.

## Entry point

[`engine/plan/__init__.py`](../../engine/plan/__init__.py) exports `build_plan`:

1. `resolve_intake_defaults(inputs)` — fills optional preference slugs (`engine/plan/intake.py`).
2. `assign_method(inputs)` — auto `daniels` vs `pfitzinger` from `p_history` + `days_per_week` (override via `inputs.method`; includes `higdon` / `hanson`).
3. `training_paces(inputs.vdot)` — Daniels table-backed paces (`engine/paces.py`).
4. Dispatch to `build_daniels_plan`, `build_pfitzinger_plan`, `build_higdon_plan`, or `build_hanson_plan`.
5. Optional: `emit_peak_scenarios` (Daniels) sets `PlanScenarioMeta` + sibling plans at **P+5** / **P+10**; `append_post_marathon_recovery` appends five recovery weeks (`common.append_post_marathon_recovery`, Pfitz p.290).

## Shared building blocks

[`engine/plan/common.py`](../../engine/plan/common.py) holds transcribed formula reference logic:

- Method assignment, peak mileage (`max(p_history, w_now)` with optional `coach_target_mpw`), weekly volume progression, taper fractions.
- `comeback_peak_mpw(inputs)` — optional `coach_floor_mpw` raises the Daniels ch.15 fast-regain ceiling.
- Daniels long-run time/share cap, session caps (T/M/I/R), MP from goal time, recovery constants.
- `assemble_week` — maps `days_per_week` to Mon..Sun template with fixed quality / LR slots.

## Generators

| Module | Structure |
|--------|-----------|
| [engine/plan/daniels.py](../../engine/plan/daniels.py) | 2Q-style: two qualities in build weeks (threshold / intervals + Saturday long with MP finish where applicable), every 4th week down. |
| [engine/plan/pfitzinger.py](../../engine/plan/pfitzinger.py) | Mesocycle progression + Saturday long. **ch.8 / ≤55 / 18 wk:** verbatim daily grid in `engine/plan/pfitz_grids.py` (pp.292-295); other tiers use mesocycle rules. |
| [engine/plan/higdon.py](../../engine/plan/higdon.py) | Verbatim grids in `engine/plan/higdon_grids.py` (Novice/Intermediate); `WorkoutKind.CROSS` for cross days. |
| [engine/plan/hanson.py](../../engine/plan/hanson.py) | Verbatim daily grids in `engine/plan/hanson_grids.py` (Just Finish, Beginner, Advanced); Wed off, Sun long ≤16 mi, Tue/Thu SOS. |
| [engine/plan/recommend.py](../../engine/plan/recommend.py) | Deterministic coach/program ranking from days + base. |

All generators emit the same [`PlannedWeek`](../../engine/plan/models.py) / [`Workout`](../../engine/plan/models.py) vocabulary for renderers and tests.

## Model

[`engine/plan/models.py`](../../engine/plan/models.py):

- **`AthleteInputs`** — engine contract; includes optional Google Form fields (see intake doc).
- **`TrainingPlan`** — athlete name, method, goal payload, paces snapshot, `weeks`, `flags` (warnings), `notes` (informational rationale/citations, e.g. the long-run time-on-feet justification), optional `scenario` / `sibling_scenarios` (Daniels peak variants), `generated_at`.

Secondary marathons: `secondary_races` + `training_plan_goal_payload` / `secondary_marathon_flags` (ordering hints; block still keys off primary `race_date`).

## Tests as spec anchor

[`tests/test_plan.py`](../../tests/test_plan.py):

- **Kelly §7** — long-run formula determinism (`test_kelly_long_run_formula`).
- Method assignment matrix, volume progression, caps, recovery days, full-plan smoke (Daniels + Pfitzinger), determinism, Saturday LR, secondary marathon flags.

[`tests/test_intake_defaults.py`](../../tests/test_intake_defaults.py) — optional intake slug defaults.

## Intake boundary

Engine does **not** scrape Strava or read Google Sheets. Intake merge policy and field matrix: [`docs/intake-and-engine.md`](../intake-and-engine.md).

## Per-methodology reference engines

The goal is to compare a **z2tc synthesis** (which draws cited rules from all four authors — e.g. the time-on-feet long-run window in [formula-reference.md](formula-reference.md)) against **pure, single-author reference engines** run on the same `AthleteInputs`, turning "the art into a science": every divergence from a book becomes an explicit, comparable, testable choice.

Status: `build_plan` dispatches on `inputs.method`:

- **Daniels** (`engine/plan/daniels.py`) — the most complete engine and internally coherent: VDOT *is* Daniels', plus the 2Q structure, ⅓ long run, p.219 ramp, single-session caps, and the ch.15 **comeback** (re-enter at ½ demonstrated peak, regain it fast, slow only in new territory).
- **Pfitzinger** (`engine/plan/pfitzinger.py`) — **tiered** like the book (ch.8–11). **ch.8 / 18 wk:** verbatim daily grid in `engine/plan/pfitz_grids.py` (pp.292-295); other tiers use mesocycle rules. Flags below-entry-base, uncharted-peak, or sub-5-day athletes.
- **Higdon** (`engine/plan/higdon.py`) — **verbatim grids** for Novice 1/2 + Intermediate 1/2 from `engine/plan/higdon_grids.py`; cross days use `WorkoutKind.CROSS`. Flags when demonstrated base is above Novice entry (~25 mpw).
- **Hanson** (`engine/plan/hanson.py`) — **verbatim daily grids** for Just Finish, Beginner, and Advanced from `engine/plan/hanson_grids.py` (pp.124-126); Wed off, Sun long ≤16 mi, Tue/Thu SOS. Flags when goal MP is faster than threshold or marathon pace.

### Single-author fidelity audit (book vs. engine)

✓ faithful · ⚠ diverges / not modeled. The aim is that every ⚠ is a *known* choice, not an accident.

| dimension | Daniels | Pfitzinger | Higdon (Novice 1) | Hanson |
|---|---|---|---|---|
| **pace basis** | VDOT ✓ | LT pace + HR (p.39,44) — engine uses VDOT ⚠ | by feel/easy (p.50) — engine shows VDOT easy ⚠ | goal-time tables, not VDOT |
| **peak mpw** | P from demonstrated capacity ✓ | tiered ≤55/55–70/70–85/>85 (ch.8–11) ✓ | emergent, no P ✓ | beginner 35–40 / adv 45–55 (p.19) |
| **ramp** | p.219 hold-then-step + ch.15 comeback ✓ | p.50 (cites Daniels) ✓ | LR ladder + stepback (p.75) ✓ | cumulative fatigue |
| **starting mileage** | re-entry ½·P (ch.15) ✓ | tier week-1 (~33/54/65/82; p.285+), flags below-base ✓ | Novice entry ~6-mi LR (p.46) ✓ | — |
| **long-run cap** | 150 min / ⅓ week (p.63) ✓ | 20–22 mi by distance (p.43) ✓ | 20 mi by distance (p.28) ✓ | 16 mi, ≤25–30% week (p.62,66) |
| **block weeks** | 18 ✓ | 12 or 18 (p.62) ✓ | 18 ✓ | 18 |
| **runs/week** | uses `days_per_week` ✓ | 5–7, doubles >75 (p.271) — accepts 4 ⚠ | Novice 3–5 (p.46) ✓ | 4–5 typical, adv 6 (p.28) |
| **speed/quality** | T/I/R + 2Q ✓ | LT/VO2max + MP ✓ | none (Novice) ✓ | SOS speed/strength/tempo (synthetic) ⚠ |

The remaining ⚠ are the **pace basis** (both Pfitzinger and Higdon are rendered with Daniels VDOT paces rather than Pfitz's LT/HR or Higdon's by-feel) and Pfitzinger **frequency** (the engine accepts a 4-day week but flags it). Hansons uses a **synthetic** mileage/SOS spine until verbatim ch.4 tables are transcribed. The citation layer (`engine/plan/citations.py`) and methodology-tagged caps are the shared seam.

## See also

- [overview.md](overview.md) — system context.
- [formula-reference.md](formula-reference.md) — book-cited provenance for every [`engine/plan/common.py`](../../engine/plan/common.py) constant (and known divergences).
- [feeds-and-analysis.md](feeds-and-analysis.md) — where `vdot`, `w_now`, `p_history` are produced before merge.
