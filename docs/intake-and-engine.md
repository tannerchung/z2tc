# Intake, merge policy, and plan engine

This document is the **source of truth** for how Zone 2 Track Club data flows from **Google Forms + Strava** into the deterministic **`engine/plan`** marathon builder, what is **required vs optional**, and how blanks are resolved.

For the *reasoning layer* on top of these fields — fitness vs volume, VDOT freshness/breaks, re-entry starting volume, P/tier selection, method routing, and a worked Kelly example — see [`docs/architecture/athlete-readiness.md`](architecture/athlete-readiness.md).

---

## 1. Two layers

| Layer | Role |
|-------|------|
| **Feeds / merge** | Strava scrape + **NYRR chip times** (optional) + Google Form row → one `AthleteInputs` instance. **Partial:** [`store/intake_sheet.py`](../../store/intake_sheet.py) + `main.py pull-intake` reads the `Intake` tab into `SurveyInputs` (overlay on a defaults JSON). Official NYRR times: [`lib/data_feeds/nyrr.py`](../../lib/data_feeds/nyrr.py) + `main.py nyrr-races`, merged with Strava report numerics via [`scripts/merge_report_nyrr_survey.py`](../../scripts/merge_report_nyrr_survey.py). Full Strava↔sheet merge for every field is still coach-driven where not scripted. |
| **Engine** | `build_plan(AthleteInputs) -> TrainingPlan`. Pure math from the Training Plan Formula Reference (Daniels / Pfitzinger). **No LLM** in the numeric path. |

Canonical code:

- Model: [`engine/plan/models.py`](../engine/plan/models.py) — `AthleteInputs`, `MarathonRace`, `TrainingPlan`.
- Default resolution for **optional** intake blanks: [`engine/plan/intake.py`](../engine/plan/intake.py) — `resolve_intake_defaults()`.
- Entry: [`engine/plan/__init__.py`](../engine/plan/__init__.py) — `build_plan()` always runs `resolve_intake_defaults()` first.
- Volume / caps / long-run math: [`engine/plan/common.py`](../engine/plan/common.py).
- Generators: [`engine/plan/daniels.py`](../engine/plan/daniels.py), [`engine/plan/pfitzinger.py`](../engine/plan/pfitzinger.py).

---

## 2. Google Form (live) — required vs optional

Form: **Zone 2 Track Club Marathon 2026 Intake**  
`https://docs.google.com/forms/d/12Vft9B-yZwsL-x-11Y01fUaOZuYW-1I-yod-bdkxx5s/edit`

### Required on the form (athlete must answer)

| Form section | Question | Maps to `AthleteInputs` | Notes |
|--------------|----------|---------------------------|--------|
| Profile | First name, last name | `name` (concatenated) | |
| Profile | Birthday | `birthday` | ISO string |
| Profile | Instagram | `instagram_handle` | |
| Profile | Strava link | `strava_profile_url` | Merge also stores Strava athlete id elsewhere |
| Marathon | Which marathons (checkboxes) | `marathons_selected`, `secondary_races`, `race_name` / `race_date` | **Merge** must pick exactly **one** primary; form uses checkboxes for primary — validate in merge |
| Marathon | Primary (checkbox) | primary `race_name` / `race_date` | Same validation |
| Marathon | A goal (HH:MM) | `goal_marathon_s` | Parsed to seconds |
| Training | Days / week | `days_per_week` | int |
| Training | Injury / issues | `intake_injury_notes` + **`injury_prone`** | Form is required text; merge sets `injury_prone` from coach rules or keywords **or** leaves `False` if text is clearly “none” |

### Optional on the form (blank = policy below)

| Question | `AthleteInputs` field(s) | If blank / omitted |
|----------|---------------------------|---------------------|
| Email | `email` | Leave `None`; notifications optional |
| B / C goal | `goal_marathon_b_s`, `goal_marathon_c_s` | `None` — coach/Sheet uses A only unless manually set |
| Latest half + time | `latest_half_race_text`, `latest_half_time_s` | Use **Strava** best half / races for VDOT; form overrides if athlete types a more representative race |
| Latest marathon + time | `latest_marathon_race_text`, `latest_marathon_time_s` | Same: Strava first, form overrides |
| When starting training | `intake_training_start_date` | Use **club season start** or first week of linked Sheet; merge computes `block_weeks` = weeks from start → primary |
| How do you want to train | `training_philosophy` | **`steady`** (`resolve_intake_defaults`) |
| Hard runs / week | `hard_quality_sessions_pref` | **`auto`** → resolved to **`two`** (Pfitz) or **`one_or_two`** (Daniels) from auto method |
| Hard difficulty | `hard_session_intensity_pref` | **`normal`** |
| Long run frequency | `long_run_frequency_pref` | **`weekly`** |
| Long run difficulty | `long_run_difficulty_pref` | **`club`** (follow club Saturday prescription) |
| Arrive / depart / stay | `marathon_arrival_date`, … | `None` — **no plan change**; social coordination only |
| Carb / shakeout | `social_carb_load`, `social_shakeout` | **`unknown`** — no plan change |
| **Closing —** Do you have any races or vacations planned? | `intake_races_vacations_notes` | `None` — merge/coach may still suggest deload or travel-week tweaks from **judgment + Strava** if the athlete wrote nothing but the profile implies heavy travel or racing |
| **Closing —** Other than a training plan, are you looking for nutrition guidance, a music playlist, shoe recommendation, or other tips? | `intake_coaching_extras_notes` | `None` — **no default product list**; coach decides whether to offer standard club guidance. If the form uses checkboxes, merge can join labels into one string (e.g. `nutrition; shoes`) |
| **Closing —** Add information about your secondary marathon here if you’d like. | `secondary_marathon_notes` | `None` — complements structured `secondary_races` (name/date). Use for pacing intent, “treat as B race,” crew, or taper questions |
| **Closing —** Anything other notes? | `free_notes` | `None` |

**Policy (your words, encoded):** for any **optional** field, if we cannot infer something significant from **Strava history**, we apply the **default** in the third column (or **`None`** where the default is “no automated fill” — e.g. races/vacations, extras, secondary notes, free notes). If we *can* infer (e.g. consistent 2 quality days in Strava), the **merge layer** should set the field explicitly before calling `build_plan` — the engine does not re-scrape Strava.

The four **closing** questions are **coach / ops / renderer** inputs: `build_plan()` does not read them. Optional blanks still mean “use coaching judgment + Strava when helpful”; there is no numeric default for nutrition or playlists.

---

## 3. Canonical intake slugs (Form → merge → `AthleteInputs`)

The merge step should normalize Google Form answer text to these slugs so the engine and Sheet stay aligned.

### `training_philosophy`

| Form label | Slug |
|------------|------|
| This is completely for funsies | `funsies` |
| Good progress/steady training | `steady` |
| All out | `all_out` |

### `hard_quality_sessions_pref`

| Form label | Slug |
|------------|------|
| 1 per week | `one` |
| 1 or 2 per week | `one_or_two` |
| 2 per week | `two` |
| you tell me | `auto` → resolved in `resolve_intake_defaults` |

### `hard_session_intensity_pref`

| Form label | Slug |
|------------|------|
| Take it easy on me | `easy` |
| Normal | `normal` |
| Crying is part of the process | `hard` |

### `long_run_frequency_pref`

| Form label | Slug |
|------------|------|
| Just enough, I don't have time | `minimal` |
| Once a week | `weekly` |
| I want to see all of New York City | `extra_aerobic` |

### `long_run_difficulty_pref`

| Form label | Slug |
|------------|------|
| I'd like to keep them easy | `easy` |
| Whatever the club does | `club` |
| You'll see me tomorrow | `aggressive` |

### Social (non-training)

| Form | Slug |
|------|------|
| Yes / Maybe | `yes` / `maybe` |
| (blank) | `unknown` after defaults |

---

## 4. How intake **adjusts** the plan (today vs next)

### Implemented today

- **`resolve_intake_defaults`**: every `build_plan()` call gets concrete slugs for philosophy, hard days, LR prefs, social unknowns — so downstream code never sees `None` for those keys.
- **Generators** currently still use **formula book** structure (2Q / mesocycles); they do **not** yet branch on `training_philosophy` or LR difficulty. Those fields are **encoded for the next iteration** (or for the Sheet renderer / coach UI).
- **`intake_races_vacations_notes`**, **`intake_coaching_extras_notes`**, **`secondary_marathon_notes`**, **`free_notes`**: stored on `AthleteInputs` for merge/Sheet/coach only; **ignored by pace/week math**.

### Next engine hooks (documented intent)

| Field | Intended effect on weeks |
|-------|---------------------------|
| `training_philosophy` | `funsies` → softer caps, slower ramp; `all_out` → allow upper cap of quality **if** `p_history` supports it; else flag |
| `hard_quality_sessions_pref` | `one` → at most one structured quality / week; `two` → current 2Q / Pfitz style |
| `hard_session_intensity_pref` | Scale T/I volume inside caps (`easy` → −15% reps, `hard` → use full caps) |
| `long_run_frequency_pref` | `minimal` → not every week at max LR; `extra_aerobic` → optional second aerobic touch within weekly miles |
| `long_run_difficulty_pref` | `easy` → fewer MP blocks in LR; `club` → match group plan; `aggressive` → progression / fast finish when volume allows |
| `goal_marathon_b_s` / `c` | Sheet + coach targets; optional replan if A is unrealistic vs VDOT |
| `intake_training_start_date` | Recompute `block_weeks`; align “Week 1” to club calendar row for that date |
| `intake_injury_notes` + `injury_prone` | Lower peak, longer holds, fewer quality sessions |
| `returning_marathoner` | When true (or Strava finds a prior marathon), merge anchors `p_history` / `last_marathon_*` on the latest Strava block, applies volume-capacity decay (`decayed_peak_mpw`), detrains VDOT (Table 15.1), sets `race_fit` when peak ≫ `w_now`. See [`store/merge_survey.py`](../store/merge_survey.py). |
| `intake_races_vacations_notes` | Future: parsed dates → optional deload / travel-week adjustments (today: coach edits plan manually) |
| `secondary_marathon_notes` + `secondary_races` | Coach narrative (B-race pacing, crew); engine still keys off primary `race_date` unless product adds multi-peak logic |

### Coach overrides (no Form question, persisted on the baseline)

These `SurveyInputs` fields have no athlete-facing Form question — the coach tunes them and
they are stored on the **season baseline** so a `replan` reproduces the plan faithfully (the
alternative is one `ManualOverride` event each). All map 1:1 to `AthleteInputs`.

| Field | Effect |
|-------|--------|
| `weekday_quality_sessions` | Midweek quality count in a build week (pure 1 = Daniels 2Q; 2 adds a midweek race-pace run). The club engine (`engine/plan/club.py`) defaults this to 2 |
| `base_quality_ramp` | Club policy: ease the second quality into the Base phase (1 → 2). Pure Daniels keeps Base aerobic |
| `aggressive_volume_ramp` | +1 mi/running-day every week to peak (vs Daniels' 3-week hold) |
| `long_run_cap_mi` / `long_run_peak_weeks` | Let the long run build past the 3 h / share caps (monitored), and weeks held there |
| `quality_long_runs_race_prep_only` | Keep threshold long runs easy; quality longs only in race-prep |
| `strides_per_phase` | Cap on stride weeks per phase |
| `recent_sustained_mpw` / `reentry_start_mpw` / `observed_long_pace_s` | Re-entry + measured-pace signals (often Strava-derived; coach-editable) |

`scripts/backfill_db.py` layers these onto an imported baseline and rebuilds the artifact.

---

## 5. Strava vs form — who wins?

| Datum | Primary source | Override |
|-------|----------------|----------|
| `w_now`, `p_history`, `longest_run_mi` | Strava (last block + trailing weeks) | Coach manual |
| `vdot` | Strava races + Table 5.1 (+ **detrain** when `returning_marathoner`) | Form latest half/marathon if athlete says it’s more representative; coach `RaceEstimate` events |
| `last_marathon_date`, `last_marathon_time_s`, `decayed_peak_mpw` | Strava latest marathon block (+ optional chip override) | Coach manual |
| Chip times (NYRR + future feeds) | [`lib/data_feeds/chip_lookup.py`](../lib/data_feeds/chip_lookup.py) via merge `--chip-search` | Strava GPS when no chip |
| `race_date`, `race_name`, primary | Form (required) | Must match merge validation |
| `goal_marathon_s` (A) | Form (required) | — |
| B / C goals | Form if present | Else absent |
| Philosophy / hard / LR prefs | Form if present | Else `resolve_intake_defaults` |

---

## 6. Club calendar vs athlete start date

- **Club Sheet** uses a fixed **Saturday long run** calendar (season week index + date).
- **Engine** uses `race_date` + `block_weeks` (default 18) and **Saturday** as long-run day in the generated week.
- **`intake_training_start_date`**: merge should set `block_weeks = min(18, weeks_from_start_to_race)` (or keep 18 and prepend “already running” mileage). UI should show **both** `ClubWeek` and `AthleteWeek` + **weeks to primary**.

---

## 7. Related docs

- [overview.md](architecture/overview.md) — Repo layers, data flow, implemented vs planned.
- [intake-google-form.md](intake-google-form.md) — Form API scripts, linking responses to Sheets.
- [README.md](../README.md) — CLI and project overview.
