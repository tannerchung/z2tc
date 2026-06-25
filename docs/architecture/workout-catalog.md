# Workout catalog (the repo's workout dictionary)

The catalog is the single, deterministic dictionary of every quality session the plan engine can
prescribe. It lives in [`engine/plan/workouts.py`](../../engine/plan/workouts.py) as
`CATALOG_WORKOUTS` — that tuple is **canonical**; this doc is the human-readable view of it. Each
entry carries a `purpose` (what it's for) and a `generation` note (how the engine sizes and paces
it), so a coach can read the dictionary without reading the builders.

See also: [plan-engine.md](plan-engine.md) (generators), [formula-reference.md](formula-reference.md)
(book-cited constants). On-sheet labels are decoded for coaches by
[`render/workout_glossary.py`](../../render/workout_glossary.py).

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
| `cruise_mile` | Cruise intervals | Mile threshold repeats with short 60 s jogs — bank T volume above a 20-min tempo (Daniels p.67). | reps = (10%-week T cap) ÷ 1 mi, at VDOT threshold pace, 60 s jog between. |
| `tempo` | Tempo run | One continuous comfortably-hard effort at threshold — confidence + lactate clearance (Daniels). | single block capped at ~20 min (T cap if shorter), at VDOT threshold pace. |
| `broken_t` | Cruise intervals (broken-T) | Half-mile threshold repeats — more reps, same T stimulus, sharper feel (Daniels). | reps = T cap ÷ 0.5 mi, at VDOT threshold pace, 60 s jog. |
| `over_unders` | Over/unders | Alternate threshold (over) and marathon pace (under), nonstop — rhythm changes at race paces (Runna). | ≈ T-cap reps of 0.5 mi @ T / 0.5 mi @ goal MP, nonstop. |
| `tempo_ladder` | Threshold ladder | Descending threshold blocks (long → short) with 60 s jogs — same T effort, varied shape (Runna 2-1-1). | T cap split 50/25/25 into 3 blocks at VDOT threshold pace, 60 s jog. |

### Interval (I / VO2max)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `vo2_intervals` | VO2max intervals | 1000 m reps at ~5K effort, equal-time jog — VO2max / aerobic power (Daniels I). | reps = (8%-week I cap) ÷ 1000 m, at VDOT interval pace, equal-time jog. |
| `vo2_1200` | VO2max intervals (1200s) | 1200 m reps at I pace — Daniels' preferred VO2max rep for slower runners (3–5 min work). | reps = I cap ÷ 1200 m, at VDOT interval pace, equal-time jog. |
| `vo2_pyramid` | VO2max pyramid | 400-800-1200-800-400 m pyramid at I pace — same VO2max stimulus, varied rep length. | fixed pyramid (~3.6 km work) at VDOT interval pace, equal-time jog; wu/cd absorbs cap. |
| `descending_i` | Descending intervals | 1200-1000-800-600-400 m at I pace — shortening reps keep pace honest as fatigue builds. | fixed descending set at VDOT interval pace, equal-time jog. |
| `drop_set` | Drop set | 1000-800-600-400-200 m descending ladder at I pace — short, sharp, fast finish (Runna). | fixed drop ladder at VDOT interval pace, equal-time jog. |

### Repetition (R)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `speed_reps` | Speed reps | Short fast 400 m reps at Rep pace, full recovery — speed + running economy (Daniels R). | reps = (5%-week R cap) ÷ 400 m, at VDOT rep pace, full 400 m jog. |
| `short_reps` | Speed reps (200s) | 200 m reps at Rep pace — pure turnover / neuromuscular work (Daniels p.135). | reps = R cap ÷ 200 m (≥8), at VDOT rep pace, full 200 m jog. |
| `rolling_400s` | Rolling 400s | 400 m reps at Rep pace with only a 200 m jog float — continuous rhythm/turnover (Runna). | reps = R cap ÷ 400 m, at VDOT rep pace, short 200 m jog (no full recovery). |

### Marathon pace (M)

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `mp_reps` | Race-pace reps | Short half-mile reps at goal marathon pace, 60 s jog — low-fatigue race-rhythm rehearsal for the taper (Runna). | reps = (trimmed M cap, ≤3 mi) ÷ 0.5 mi, at goal MP, 60 s jog. |

### Long runs

| Key | Name | What it is | How the engine builds it |
|---|---|---|---|
| `long_easy` | Long run (easy) | Steady aerobic long run — time on feet, durability (all four authors' staple). | distance = min(3 h time-on-feet at observed long pace, 18 mi, 30–25% of week); all easy. |
| `long_fartlek` | Long run w/ fartlek | Easy long run with brief ~1 min surges sprinkled in — light turnover, breaks up the run (Humphrey). | same easy long-run distance; ~one 1-min surge per 1.5 mi (stays an aerobic day). |
| `mp_blend` | Marathon long run | Daniels 2Q nonstop E/M/(T)/M/E blend — race-pace volume inside the long run (Table 14.3). | long-run distance; ~half at goal MP (≤ M cap) with a 1-mi T surge, rest easy. |
| `progression` | Progression long run | Thirds: easy → steady → marathon pace — pacing discipline, low-risk strong finish (Humphrey/Higdon 3/1). | long-run distance split in thirds: easy, steady (E↔MP midpoint), goal MP. |
| `mp_blocks` | Marathon-pace blocks | Two MP blocks split by an easy float — race rhythm + fueling rehearsal, more banked MP (Runna 'Block'). | long-run distance; 2 × (≈25%, ≤ M cap/2) blocks at goal MP, 1-mi easy float, easy wu/cd. |
| `fast_finish` | Fast-finish long run | Mostly easy, closed at marathon pace — late-race grit, kept controlled (McMillan; Humphrey). | long-run distance; final block (≤ M cap, ≤40%) at goal MP, rest easy. |
| `race_practice` | Race-practice long run | Dress rehearsal: one sustained MP block (the build's longest) — goal pace, fueling + kit (Pfitzinger; Runna). | long-run distance; one continuous MP block = min(M cap, distance − 3 mi), easy wu/cd. |

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
  - **Threshold phase:** `cruise_mile` → `tempo` → `broken_t` → `over_unders` → `tempo_ladder`.
  - **Race Prep:** `vo2_intervals` → `drop_set` → `vo2_pyramid` → `vo2_1200` → `descending_i` →
    `rolling_400s` → `speed_reps`. On a **mileage step-up week** VO2max is deferred and the session
    is held at threshold (don't raise volume and pile on intervals the same week — Daniels p.36).
  - **Taper:** `cruise_mile` (a short threshold touch two weeks out) → `mp_reps` (a low-fatigue
    goal-pace sharpener the final full week, mirroring the Runna taper).

Down weeks keep the long run easy and drop Q2 entirely.
