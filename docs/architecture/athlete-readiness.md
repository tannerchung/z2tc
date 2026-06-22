# Athlete readiness → plan: the decision model

How raw inputs (intake form + Strava + coach knowledge) become the numbers the engine
runs on. This exists so we **don't re-derive it per athlete** — when a number looks
wrong, trace it here instead of re-interrogating the data.

Canonical contracts: intake field matrix → [`docs/intake-and-engine.md`](../intake-and-engine.md);
plan math → [`docs/architecture/plan-engine.md`](plan-engine.md). This doc is the *reasoning layer* on top.

---

## 1. Input provenance map

Every `AthleteInputs` field (`engine/plan/models.py`) has exactly one source of truth.
"Strava" = derived by `engine/analyze.summarize` + `scripts/merge_report_nyrr_survey.py`;
"intake" = `store/intake_sheet.py` reading the club **`Intake`** tab; "coach" = manual
override on the merged `SurveyInputs` JSON.

| Field | Source | Notes |
|-------|--------|-------|
| `vdot` | Strava (races) | Best representative race; **freshness-gated** (§3). NYRR chip times override Strava GPS. |
| `goal_marathon_s` (+ `_b_s`, `_c_s`) | intake | A/B/C goal times, cols K/L/M. |
| `w_now` | Strava | Trailing ~4-wk run-mile avg. **Volume readiness, not fitness** (§4). |
| `p_history` | Strava | Max mpw in last marathon block → drives **tier/P** (§5). |
| `longest_run_mi` | Strava | Recent longest run. |
| `days_per_week` | intake | "How many days per week can you run?" (col X). |
| `race_name` | intake | "Which one is your primary?" (col J). |
| `race_date` | **calendar** | Official published date via `lib/marathon_calendar.py` (§6); form has no date column. |
| `block_weeks` | default **18** | No intake field → always 18 (§7). |
| `method` | auto / intake / coach | `assign_method` unless forced (§8). |
| `injury_prone` | intake | Derived from injury notes (col Y). |
| `*_pref`, `training_philosophy` | intake | Cols AA+; shape generator choices, not volume math. |
| `marathon_arrival/departure_date` | intake | Travel; also a **year hint** for the calendar. |

If a column is on the sheet but unmapped, `intake_sheet.unmapped_headers` **logs a
warning** — never silently drop a question.

---

## 2. Two clocks: fitness vs volume

The central idea. An athlete has **two independent states**, and conflating them is the
bug that produced Kelly's broken plan:

- **Fitness (VDOT → paces).** How fast she can race *now*. Degrades only with a true
  training **break** (Daniels Table 15.1, §3). "Backing off a little in mileage" is **not**
  fitness loss (Daniels p.155).
- **Volume readiness (where the mileage ramp starts).** How much she's *currently* running.
  Independent of fitness — a race-fit runner can still be at low volume.

`peak_mileage = max(p_history, w_now)` (the old code) collapsed both into one number and let
a low off-season `w_now` distort the plan. The model below keeps them separate.

---

## 3. Fitness: VDOT, freshness, and breaks

1. **Source VDOT from the best recent race** (half > 10K > 5K > marathon), NYRR chip
   times preferred.
2. **Freshness check** — decide whether to trust that VDOT, from two Strava signals:
   - **Race recency:** VDOT source race ≤ ~60 days old (Daniels p.219: a recent race with
     uninterrupted training sets VDOT directly).
   - **Mileage continuity:** no long multi-week zero-gaps in the lead-up.
   - Pass → trust the race VDOT. Fail → apply Table 15.1.
3. **Table 15.1 — VDOT adjustment for training breaks** (Daniels p.281–282), keyed on the
   length of a **break (days not running)**, *not* time-since-peak and *not* a volume dip:

   | Break | FVDOT-1 (no cross-train) | FVDOT-2 (cross-train) |
   |-------|--------------------------|------------------------|
   | ≤ 5 days | 1.000 | 1.000 |
   | 7 days | .994 | .997 |
   | 6 weeks (42 d) | .889 (≈11% loss) | .944 |
   | ~10 weeks | ≈.80 (floor, ~20% loss) | better |

   `adjusted_vdot = race_vdot × FVDOT`. Cross-training during the break selects **FVDOT-2**.

4. **Cross-training (FVDOT-1 vs FVDOT-2)** is read from Strava `sport_type` per workout
   (also `name`/`description` for qualitative tagging):
   - **Leg-associated aerobic → FVDOT-2:** `Ride`, `Swim`, elliptical, aqua-jog, `Hike`/`Walk`
     at volume.
   - **Strength/mobility → does NOT offset detraining:** `WeightTraining`, `Pilates`, `Yoga`,
     generic `Workout`.

   Pfitzinger has no quantified break table; he treats ~6 weeks as the point fitness starts to
   slip (p.375) and warns over-tapering loses fitness (p.221). Daniels' Table 15.1 is the model
   we use.

> **In code (`engine/readiness.py`):** `assess_freshness()` makes the trust decision;
> `break_adjustment_factor(days_off, cross_trained)` interpolates Table 15.1 (anchors .889 @ 6 wk,
> .944 with cross-train, ~.80 floor — Daniels p.282); `classify_cross_training(sport_types)`
> buckets Strava `sport_type`; `adjusted_vdot()` applies the discount. The break/cross-training
> signals reach the engine via `AthleteInputs.recent_break_days` /
> `cross_trained_during_break`, derived at merge time (`scripts/merge_report_nyrr_survey.py`).

---

## 4. Volume readiness: the re-entry start

The ramp starts at a **re-entry volume**, not raw `w_now` and not the demonstrated peak:

- `w_now` alone **undershoots** a race-fit athlete (a 1:45-half runner clears 20 mpw easily).
- `p_history` alone **overshoots** (volume not run in months → injury risk).
- **Re-entry start ≈ the recent *sustainable* volume the athlete has actually been running**
  (e.g. recent multi-week high), gated by current race-fitness, **then coach/athlete can override**.

A ~0-day break does **not** raise the start to peak — break length governs *fitness* (§3),
recent volume governs the *start*. The two are decoupled.

From the re-entry start, ramp per **Daniels p.219 (printed p.205)**: *"increasing weekly
mileage about every 4th week … by 1 mile for every running session you do each week … but
don't increase by more than 10 miles"* (and *"no need to go over 80 miles per week"*). So the
ramp **holds** the level for ~3 running weeks, then **steps up** by `min(days_per_week, 10)`
mpw — with a recovery week (~80%) every 4th week (Pfitzinger ch.3). Returning from a real
layoff follows the more conservative **Table 15.2** schedule (Daniels p.283: cat. II = ½ at
50% load then ½ at 75%; cat. III = thirds at 33→50→75%).

**Base-from-scratch vs already-based.** An athlete who starts near peak just holds at peak
(little ramping); a true base-builder climbs slowly and may **not** reach an aggressive `P`
inside 18 weeks — that's correct, and the generators **flag** it (`peak not reached: … raise
the re-entry start or lower P`) instead of sprinting up. Long runs stay ≤ ~⅓ of the week and
respect the tier ceiling.

> **In code:** `engine/plan/common.weekly_volumes(start, peak, …, hold_weeks=3,
> down_week_every=4)` implements the hold-then-step ramp (replacing the old every-week
> increment). `engine/readiness.recommended_reentry_volume()` recommends the **start**;
> `safe_weekly_step()` is the `min(sessions, 10)` increment. **`build_plan` now applies this
> automatically:** when `inputs.reentry_start_mpw` is unset it calls
> `recommended_reentry_volume()` and the generators ramp from there (`common.ramp_start`), not
> from a raw off-season `w_now`. A coach overrides by setting `reentry_start_mpw` (or
> `recent_sustained_mpw`) explicitly, or marks a true beginner `race_fit=False` to start at
> `w_now` and slow-build. Note this is only the ramp **start** — the hold-then-step **rate**
> still tops the build below an aggressive `P` (hence the `peak not reached` flag); a faster
> return-to-`P` ramp is a separate, not-yet-built change.

**Off-peak duration vs. demonstrated peak.** When `p_history` is months stale, treat it as a
*ceiling reference*, not current capacity: `engine/readiness.decayed_volume_capacity(p_history,
weeks_since_peak)` applies a house piecewise decay (same interpolation style as Daniels
Table 15.1 factors) for advisory tooling; coaches can also fold `WeeklyEvaluation.estimated_mpw`
events (see [event-sourcing](event-sourcing.md)).

---

## 5. Peak / P and tier selection

- **P (planned peak weekly mileage)** is the athlete's choice in Daniels' framing — "the most
  mileage you plan to run" (p.232, p.273) — not an engine output. The engine **recommends** a
  safe P from demonstrated capacity (`p_history`), run days, goal, and injury profile; the
  **coach/athlete confirm** it. Diminishing-return / accelerating-setback framing (Daniels
  Principle 6, p.36, fig 2.3) caps how aggressive a recommendation should be.

> **In code:** `engine/readiness.recommended_peak_mileage(p_history, days_per_week,
> injury_prone, goal_demanding)` anchors on `p_history`, allows **at most one safe step** above
> it for a demanding goal, holds at demonstrated capacity when injury-prone, and clamps to
> Daniels' **80-mpw** ceiling (p.219). `injury_volume_factor()` is the conservative
> injury haircut (Accelerating Setbacks, p.36).
- **Tier** is bucketed off P (≈ `p_history`): Daniels splits prescriptions at 40 mpw (T-pace
  Session A "up to 40" vs B "41–70", p.70); the 2Q program columns bucket into 41–55, 56–70, …
  The tier sets the long-run ceiling and session caps — and is set by **P, not the re-entry start**.

---

## 6. Race-date resolution (calendar)

The form captures the marathon **name** but not its date, and athletes mistype dates. Dates
are officially published, so `lib/marathon_calendar.py` resolves `race_name → ISO date`
(tolerating sponsor prefixes like "Bank of America Chicago Marathon"). The intake reader fills
`race_date` from the calendar when no date column is present, using the travel year as a hint.
Extend `MARATHON_DATES` per confirmed year. Unknown race → `race_date` falls back to coach/defaults.

---

## 7. Block length

`block_weeks` defaults to **18** and there is no intake question for it, so it is **always 18
unless explicitly added to intake**. `intake_training_start_date` is captured for context but
does **not** shorten/lengthen the block.

---

## 8. Method routing (Daniels vs Pfitzinger)

`assign_method`: a forced `method` wins; else `p_history ≥ 40 and days_per_week ≥ 5` →
Pfitzinger; else Daniels.

This is **book-grounded but the cutoff is our calibration**. Pfitzinger's *Advanced
Marathoning* targets post-debut, higher-mileage runners; its schedules are organized by peak
weekly mileage with the **lowest plan peaking at 55 mpw** (Ch.8), up to 100+ (Ch.11), assuming
5–7 days and often doubles (p.12–13, p.17, p.42). Daniels spans Novice → 101–120. So routing
advanced/high-mileage runners to Pfitzinger is legitimate; the exact `40 / 5` numbers are ours,
and an athlete near 55-peak is genuinely borderline.

---

## 9. Worked example — Kelly (the reference case)

Pulled real data (intake row 3, Strava `42251408`, NYRR chip):

| Signal | Value | Reading |
|--------|-------|---------|
| Intake | Kelly Hession, **Chicago Marathon**, A-goal **3:45** (B 3:48 / C 3:50), **5 days** | Real, after the intake-reader fix. |
| `race_date` | **2026-10-11** | Resolved from the calendar (form has no date). |
| Races (Strava) | Halves 1:52→1:49→**1:45** (Brooklyn, 2026-05-16) + 10K 2026-06-06 | Improving; **fitness current**. |
| `vdot` | **42.6** | Source race 31 days old → **freshness PASS** → no Table 15.1 adj. |
| Cross-training | Pilates/Swim/Ride/Weights (475 acts) | Mostly strength/mobility; she never broke anyway. |
| Weekly volume | ~5–21 mpw for ~7 months since NYC peak | **Volume low**, but `w_now=10.9` is an off-season backoff, not detraining. |
| `p_history` | **47.9** (NYC block) | Sets **tier 41–55** and the P recommendation. |

**Verdict:** race-fit (VDOT 42.6, untouched) but low-volume. So the plan keeps her paces, sets
P/tier off the 47.9 peak, and starts the ramp at a **re-entry ≈ 20 mpw** (recent high she's run,
which her half-fitness easily supports) — *not* raw 10.9 (the old 3.6-mi week-1 long run) and
*not* 48 (untrained volume). Method auto-routes to **Pfitzinger** (47.9 ≥ 40, 5 days), though
she sits on the Daniels-41–55 / Pfitzinger-entry boundary.

Running `assess_readiness` on Kelly confirms her **3:45 A-goal is `within_current`** — VDOT 42.6
already predicts a ~3:38 marathon (`race_equivalent_times`), so the goal is conservative, not a
reach. The coaching move is to protect that fitness through the volume re-entry, not chase a
faster VDOT.

---

## 10. Goal realism — arming the coach (the most-used output)

The coach, not the athlete, drives intake; the coach's job is to judge whether the athlete's
A/B/C goals are real and explain why. The model gives the numbers to do that:

1. **Required fitness.** `vdot_from_race(Marathon, goal_time)` → the VDOT the goal *demands*.
2. **Current fitness.** Race VDOT (freshness-gated, §3).
3. **Realistic fitness.** `projected_vdot(current, build_weeks)` — current **plus** a
   diminishing-return gain (`projected_vdot_gain`, house heuristic on Daniels Principle 6,
   p.36): a beginner can add a few VDOT points over a block, an advanced runner far less.
4. **Verdict** (`goal_feasibility` → `within_current` / `in_reach` / `stretch` / `unrealistic`)
   plus a **defensible alternative time** = `predict_race_time(projected_vdot, Marathon)`.
5. **Equivalent times** (`race_equivalent_times(vdot)`) translate one fitness number into 5K /
   10K / HM / marathon targets — useful for setting tune-up race goals and reality-checking a
   half result against a marathon dream.

This is the script the coach reads back to the runner: *"your half says VDOT X; that's a ~Y
marathon today; your goal needs VDOT Z, which is a realistic stretch / out of range for one
block — let's anchor at Y′."*

---

## 11. Balancing the volume ramp against VO2max (hitting the time goal *and* the mileage)

The tension: a low-volume re-entry needs mileage to climb, but the time goal needs VDOT to
climb — and stacking hard **VO2max (`I`)** intervals on a week you're also **raising mileage**
courts Accelerating Setbacks (Daniels p.36; Pfitzinger ch.3 hard/easy). Rule the engine now
encodes:

- VO2max work only appears in the **Race Prep** phase (after the endurance base is laid) in both
  generators — never during the early volume climb.
- **`engine/plan/common.volume_step_ups(vols)`** marks weeks whose target rises above all prior
  weeks. On a **step-up week**, the generators **swap the VO2max session for a threshold session**
  (and flag `VO2max deferred this week (mileage step-up)`). Because the ramp **holds** 3 weeks per
  level (§4), most Race-Prep weeks are *holds* — so VO2max lands on stable-mileage weeks, exactly
  where it belongs, and you still get the VDOT stimulus without colliding with a volume jump.

So the two demands are sequenced, not crammed: raise volume on step weeks (threshold-only
quality), develop VO2max on the hold weeks in between.

---

## 12. What is in code now (quick map)

| Concern | Function (`engine/readiness.py` unless noted) | Book anchor |
|---------|-----------------------------------------------|-------------|
| Predict race time from VDOT | `engine/vdot.predict_race_time`, `race_equivalent_times` | Daniels Table 5.1 |
| Realistic VDOT gain | `projected_vdot_gain`, `projected_vdot` | Principle 6, p.36 (fig 2.3) |
| Goal verdict + alternative | `goal_feasibility` → `GoalAssessment` | derived |
| Freshness / trust race VDOT | `assess_freshness` | Daniels p.219 |
| Break adjustment | `break_adjustment_factor`, `adjusted_vdot` | Table 15.1, p.282 |
| Cross-training bucket | `classify_cross_training` | Daniels p.284 |
| Re-entry start | `recommended_reentry_volume` | Table 15.2, p.283 |
| Safe weekly increment | `safe_weekly_step` | Daniels p.219 |
| Recommended peak P | `recommended_peak_mileage` | Daniels p.219/p.232 |
| Hold-then-step ramp | `engine/plan/common.weekly_volumes` | Daniels p.219 |
| VO2max-vs-ramp balance | `engine/plan/common.volume_step_ups` + generators | Daniels p.36 / Pfitz ch.3 |
| Top-level coach report | `assess_readiness` → `ReadinessAssessment` | — |
