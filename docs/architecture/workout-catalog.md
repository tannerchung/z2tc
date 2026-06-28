# Workout catalog (the repo's workout dictionary)

The catalog is the single, deterministic dictionary of every quality session the plan engine can
prescribe. It lives in [`engine/plan/workouts.py`](../../engine/plan/workouts.py) as
`CATALOG_WORKOUTS` — that tuple is **canonical**; this doc is the human-readable view of it. Each
entry carries a `purpose` (what it's for) and a `generation` note (how the engine sizes and paces
it), so a coach can read the dictionary without reading the builders.

See also: [plan-engine.md](plan-engine.md) (generators), [formula-reference.md](formula-reference.md)
(book-cited constants). On-sheet labels are decoded for coaches by
[`render/workout_glossary.py`](../../render/workout_glossary.py).

The club workbook's **Workout Dictionary** tab is generated from this catalog (plus the pace legend
and terminology in `render/workout_glossary.py`) by
[`render/workout_dictionary.py`](../../render/workout_dictionary.py) and published with
`publish-club`. It is engine-synced like the Long Runs and Read Me tabs, so do not hand-edit it.

## How the engine generates a workout

Every quality session is **paced off the athlete's numbers** and **sized off the week's mileage** —
nothing is hard-coded to a person:

- **Paces** come from the athlete's VDOT (`engine/paces.py`): `E` (easy), `T` (threshold), `I`
  (interval/VO2max), `R` (repetition). **Marathon pace (`M`) is the athlete's goal-race pace** (from
  the A-goal time), *not* VDOT marathon pace — that's the one pace tied to the goal rather than
  current fitness.
- **Volume** comes from `session_caps(target_miles, mp_s)` (`engine/plan/common.py`), which converts
  the week's target mileage into single-session ceilings by intensity: roughly **T ≤ 10%**, **I ≤ 8%
  (≤10 km)**, **R ≤ 5%**, plus a marathon-pace cap `M`. A builder turns its cap into a rep count
  (e.g. `T cap ÷ 1 mi` cruise reps) and brackets the work with a 1.5 mi easy warm-up and cool-down.
- **Long runs** are sized by `daniels_long_run()`: the smaller of ~3 h time-on-feet at the observed
  long-run pace, an 18 mi cap, and a 30→25% share of the week. Quality long runs then place goal-MP
  volume inside that distance, bounded by the `M` cap.

So the *same* catalog entry yields a 4 × 1 mi cruise for one athlete and 6 × 1 mi for a higher-volume
athlete, each at their own threshold pace — and the plan engine stays pure (same inputs → same plan).

## The catalog

<!-- The tables below are a view of CATALOG_WORKOUTS; engine/plan/workouts.py is the source of truth. -->

### Threshold (T)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `cruise_mile` | Cruise intervals | Mile threshold repeats with short 60 s jogs that bank T volume above a 20-min tempo (Daniels p.67). | reps = (10%-week T cap) ÷ 1 mi, at VDOT threshold pace, 60 s jog between. |
| `tempo` | Tempo run | One continuous comfortably-hard effort at threshold for confidence and lactate clearance (Daniels). | single block capped at ~20 min (T cap if shorter), at VDOT threshold pace. |
| `broken_t` | Broken-T intervals | Half-mile threshold repeats for more reps at the same T stimulus with a sharper feel (Daniels). Distinct label from `cruise_mile` so the rotation doesn't read as "all cruise intervals." | reps = T cap ÷ 0.5 mi, at VDOT threshold pace, 60 s jog. |
| `over_unders` | Over/unders | Alternate threshold (over) and marathon pace (under), nonstop, for rhythm changes at race paces (Runna). | ≈ T-cap reps of 0.5 mi @ T / 0.5 mi @ goal MP, nonstop. |
| `tempo_ladder` | Threshold ladder | Descending threshold blocks (long to short) with 60 s jogs for the same T effort in a varied shape (Runna 2-1-1). | T cap split 50/25/25 into 3 blocks at VDOT threshold pace, 60 s jog. |

### Interval (I / VO2max)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `vo2_intervals` | VO2max intervals | 1000 m reps at about 5K effort with equal-time jog for VO2max and aerobic power (Daniels I). | reps = (8%-week I cap) ÷ 1000 m, at VDOT interval pace, equal-time jog. |
| `vo2_1200` | VO2max intervals (1200s) | 1200 m reps at I pace, Daniels' preferred VO2max rep for slower runners (3 to 5 min work). | reps = I cap ÷ 1200 m, at VDOT interval pace, equal-time jog. |
| `vo2_pyramid` | VO2max pyramid | 400-800-1200-800-400 m pyramid at I pace for the same VO2max stimulus in varied rep lengths. | fixed pyramid (~3.6 km work) at VDOT interval pace, equal-time jog; wu/cd absorbs cap. |
| `descending_i` | Descending intervals | 1200-1000-800-600-400 m at I pace, where shortening reps keep pace honest as fatigue builds. | fixed descending set at VDOT interval pace, equal-time jog. |
| `drop_set` | Drop set | 1000-800-600-400-200 m descending ladder at I pace, short and sharp with a fast finish (Runna). | fixed drop ladder at VDOT interval pace, equal-time jog. |

### Repetition (R)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `speed_reps` | Speed reps | Short fast 400 m reps at Rep pace with full recovery for speed and running economy (Daniels R). | reps = (5%-week R cap) ÷ 400 m, at VDOT rep pace, full 400 m jog. |
| `short_reps` | Speed reps (200s) | 200 m reps at Rep pace for pure turnover and neuromuscular work (Daniels p.135). | reps = R cap ÷ 200 m (≥8), at VDOT rep pace, full 200 m jog. |
| `rolling_400s` | Rolling 400s | 400 m reps at Rep pace with only a 200 m jog float for continuous rhythm and turnover (Runna). | reps = R cap ÷ 400 m, at VDOT rep pace, short 200 m jog (no full recovery). |

### Marathon pace (M)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `mp_reps` | Race-pace reps | Short half-mile reps at goal marathon pace with 60 s jog, a low-fatigue race-rhythm rehearsal for the taper (Runna). | reps = (trimmed M cap, ≤3 mi) ÷ 0.5 mi, at goal MP, 60 s jog. |
| `mp_run` | Race-pace run | Continuous goal-marathon-pace miles, a midweek race-practice run for goal pace, rhythm and fueling (Pfitzinger MP; Higdon pace run). | min(M cap, 6 mi) continuous at goal MP, easy wu/cd. |

### Long runs

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `long_easy` | Long run (easy) | Steady aerobic long run for time on feet and durability (all four authors' staple). | distance = min(3 h time-on-feet at observed long pace, 18 mi, 30–25% of week); all easy. |
| `long_fartlek` | Long run w/ fartlek | Easy long run with brief ~1 min surges sprinkled in for light turnover that breaks up the run (Humphrey). | same easy long-run distance; ~one 1-min surge per 1.5 mi (stays an aerobic day). |
| `mp_blend` | Marathon long run | Daniels 2Q nonstop E/M/(T)/M/E blend that banks race-pace volume inside the long run (Table 14.3). | long-run distance; ~half at goal MP (≤ M cap) with a 1-mi T surge, rest easy. |
| `progression` | Progression long run | Thirds that build easy to steady to marathon pace for pacing discipline and a low-risk strong finish (Humphrey/Higdon 3/1). | long-run distance split in thirds, easy then steady (E↔MP midpoint) then goal MP. |
| `mp_blocks` | Marathon-pace blocks | Two MP blocks split by an easy float for race rhythm, fueling rehearsal and more banked MP (Runna 'Block'). | long-run distance; 2 × (≈25%, ≤ M cap/2) blocks at goal MP, 1-mi easy float, easy wu/cd. |
| `fast_finish` | Fast-finish long run | Mostly easy and closed at marathon pace for late-race grit, kept controlled (McMillan; Humphrey). | long-run distance; final block (≤ M cap, ≤40%) at goal MP, rest easy. |
| `race_practice` | Race-practice long run | A dress rehearsal with one sustained MP block (the build's longest) for goal pace, fueling and kit (Pfitzinger; Runna). | long-run distance; one continuous MP block = min(M cap, distance − 3 mi), easy wu/cd. |

## Rotation (Daniels generator)

The generator never repeats the same session week after week. The **phase** picks the menu; a
per-phase occurrence counter picks the position, so the rotation is deterministic.

- **Q1 — the long run** (Saturday). Always a `long`-role workout:
  - **Base / down weeks:** `long_easy` ↔ `long_fartlek` (aerobic; the fartlek adds variety, not load).
  - **Threshold phase:** `mp_blend` ↔ `progression` (introduce goal-pace volume).
  - **Race Prep:** `mp_blocks` → `fast_finish` → `mp_blend`, and the last non-down Race-Prep week is
    forced to `race_practice` — the dress rehearsal.
- **Q2 — the midweek quality** (Tuesday on the 4-day week, Wednesday at 5+ days — held clear of
  the Saturday long run; see `common.midweek_quality_day`):
  - **Base phase:** aerobic in the pure engine; only the **club Base ramp** (`base_quality_ramp`)
    puts a quality here, rotating `speed_reps` → `cruise_mile` → `tempo` (`BASE_Q2`) — a gentle Reps
    session first (low-fatigue speed/economy), a short threshold later, so the first quality is easy
    on a rebuilding aerobic base.
  - **Threshold phase:** `cruise_mile` → `tempo` → `broken_t` → `over_unders` → `tempo_ladder`.
  - **Race Prep:** `vo2_intervals` → `drop_set` → `vo2_pyramid` → `vo2_1200` → `descending_i` →
    `rolling_400s` → `speed_reps`. On a **mileage step-up week** VO2max is deferred and the session
    is held at threshold (don't raise volume and pile on intervals the same week — Daniels p.36).
  - **Taper:** `cruise_mile` (a short threshold touch two weeks out) → `mp_reps` (a low-fatigue
    goal-pace sharpener the final full week, mirroring the Runna taper).
- **Q3 — a second midweek quality** (Thursday on the 4-day week — see
  `common.second_midweek_quality_day`). A continuous goal-pace `mp_run` ("Race-pace run"). Opt-in via
  `weekday_quality_sessions = 2` (needs ≥ 4 days); pure Daniels is a single midweek quality, and the
  **z2tc club engine** (`engine/plan/club.py`) is what defaults this on. It is **skipped** on down
  weeks and on weeks the long run is itself a quality session (so a quality-long week stays at two
  hard sessions — long + Q2 — not three). In the **Base** phase it appears only under the club
  `base_quality_ramp`, **eased in** — only the back half of Base carries it, so the block opens at one
  effort and ramps to two before the Threshold phase. On a 4-day `quality_long_runs_race_prep_only`
  load this gives threshold weeks two real quality runs and seeds **race-practice** work into the
  threshold phase.

Down weeks keep the long run easy and drop Q2/Q3 entirely.

### Pure engine vs club engine

The generators here are **pure** — same `AthleteInputs` → same `TrainingPlan`, textbook by default
(single midweek quality, aerobic Base). The club's house modifications live in `engine/plan/club.py`:
`apply_club_policy()` resolves z2tc defaults (two quality efforts a week, `base_quality_ramp` on) onto
the inputs, and `build_club_plan()` builds through the pure `build_plan` with that policy applied.
Production (the CLI `build-plan` / `start-season`, `replan`) builds **club** plans; the pure engine
stays available for testing and book-faithful output.
