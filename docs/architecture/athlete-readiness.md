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
> `cross_trained_during_break`, derived at merge time (`store/merge_survey.py`:
> break measured since the chosen fitness race, compared against the marathon anchor;
> `resolve_merge_vdot()` applies `assess_freshness()` before storing plan VDOT).

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

### 10a. Tune-up race ladder — the forward feedback loop

`goal_feasibility` is a *day-one* verdict. `tune_up_ladder()` turns it into a **mid-block, measurable
loop** so an aggressive goal is tested rather than assumed — exactly what's needed when goal MP sits
at/past current Threshold (the goal-realism caution on the plan sheet). Given current VDOT, the goal,
the build length, and (optionally) the race date, it lays out checkpoint races — default **5K (≈30%
in) → 10K (≈55%) → 10K (≈80%)** (short/sharp; **no half marathon close to the goal** — a half that
late costs the recovery a peak long-run block needs, cf. Pfitzinger ch.8 / Higdon) — and for each
gives two target times at that distance:

- **on-track-for-goal** = `predict_race_time(v, dist)` where `v` walks a straight line from current
  toward the goal's `required_vdot` (the A-goal trajectory).
- **realistic** = `predict_race_time(projected_vdot(current, weeks_elapsed), dist)` (the
  diminishing-return projection).

Decision rule: a result at/under **on-track** keeps the A-goal alive; between the two is a B-goal;
slower than **realistic** is the signal to re-anchor. Returns `TuneUpLadder` (with `TuneUpCheckpoint`
rows); surfaced read-only via `python main.py tune-up-plan <athlete>`. It mutates nothing — the
existing `TuneUpResult` / `FitnessAnchor` events are how an actual result folds back into `vdot`.

This is the coach/readiness *report* layer. **Scheduling** these tune-ups into the plan is club
policy: `ClubPolicy.schedule_tune_ups` (`engine/plan/club.py`) turns the ladder's checkpoints into
declarative `TuneUpRace` specs on `AthleteInputs.tune_up_races`, and `place_tune_up_races` seats each
one on its week's long-run slot (a `RACE` on a mini-cutback week) as a **method-agnostic** post-process
— every club plan gets the feedback races. **Daniels plans get the ladder by default** (the club's
stance is that an empirical mid-block 5K/10K is the best way to refine VDOT and paces, on-track goal
or not); other methods get the club ladder only when the goal needs a VDOT the athlete hasn't shown.
When a method already races mid-block (Pfitzinger/Higdon),
the club doesn't double-schedule: it keeps the book's native races and **annotates** each with the same
goal-linked target times the ladder computes (`_annotate_native_tune_ups`), so those athletes also know
what to aim for. The ladder logic stays here; the policy/placement seam stays in the club engine — see
[`docs/architecture/plan-engine.md`](plan-engine.md).

**Closing the loop (`record-tune-up`).** After an athlete races a tune-up, `python main.py
record-tune-up <athlete> --distance 10k --time 41:30` computes the VDOT the effort showed
(`vdot_from_race`), logs a `TuneUpResult` event (folded into the athlete's `vdot` on the next
`replan`), and reports the re-anchor verdict: it projects the measured fitness over the weeks left
(`goal_feasibility`) and says whether the marathon goal is on track or should move toward the
projected-fitness equivalent. This assumes a genuine race effort — that's what makes the VDOT real.

**The flywheel is closed (dossier anchor freshens).** `--race-date` (default today) stamps when the
tune-up was run. `main._load_dossier` reads applied `TuneUpResult` events, converts each to a
`RacePerformance` (`engine.athlete_profile.race_from_tune_up`) and merges it into the dossier's race
timeline, recomputing the fitness anchor's `source_date` as the max of the report's source race and
the latest tune-up. So a freshly-raced tune-up automatically clears `anchor.stale` and the
"confirm a stale anchor with a tune-up" recommendation — the dossier no longer reports a stale anchor
the athlete has already addressed. `build_dossier` stays pure; the merge happens in the `main.py`
store adapter, which passes the corrected races + `source_date` in.

**Showing the verdict on the sheet.** Once results have landed, `publish-sheet` paints them onto the
plan. It reads the athlete's `TuneUpResult` events (chronological), pairs them to the plan's tune-up
weeks in order, and for each match calls `readiness.tune_up_outcome(measured_vdot, goal, weeks_remaining)`
— the same projection as `record-tune-up`, anchored to the **measured** VDOT so the verdict is stable
across later replans. The mapping is `within_current`/`in_reach` → on-track (green ✅), `stretch` →
B-goal watch (amber 🟠), `unrealistic` → behind (red 🔴). The race cell is tinted by status and the
week's "Why" column leads with the verdict line (`render/plan_layout._tune_up_outcomes`, tinted in
`render/plan_sheet_format`). Weeks without a result render unchanged.

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

## 12. Proposed: adherence-driven readiness delta (future work — algorithm TBD)

> **Status: PROPOSED, not implemented.** This section captures the design intent so we can build it
> deliberately. The *algorithm itself* (the calibration constants and the exact penalty curves) is
> intentionally left open — we'll define it together. Nothing here ships until those are settled.

### The gap this closes

`projected_vdot(current, weeks_elapsed)` gives the fitness ramp we expect **if the athlete executes
the plan**. `engine/monitor.py` already detects when they *don't* (`AdherenceFlag` on volume, `MissedQuality`,
plus `LongRunIncomplete` / `FatigueFlag` / `EasyPaceDrift` / `OverreachFlag`). What's missing is the
bridge: a deterministic read of *"given what they actually did, where does that leave their fitness and
endurance, and how does that contrast with where the plan assumed they'd be?"* Today that delta is
applied by hand via `WeeklyEvaluation.calibrated_vdot`. The proposal is to **compute** the contrast
(advisory) so the coach walks into the athlete conversation with the math already done, then confirms
the delta deliberately.

### Two separate tracks (they degrade differently)

Fitness isn't one number for this purpose — a missed long run and a missed interval session hurt
*different* capacities, so we track them apart:

1. **VDOT track (speed / aerobic power).** Driven by `MissedQuality` and pace-drift signals. Missing
   the *quality* sessions stalls the VDOT ramp rather than reversing it. Sketch:
   `expected_vdot_now ≈ current + Σ(weekly_gain × quality_executed_fraction)` over the elapsed weeks —
   i.e. you only bank the gain you did the work for.
2. **Endurance track (durability / volume).** Driven by the `AdherenceFlag` volume ratio and
   `LongRunIncomplete`. This barely moves VDOT but erodes marathon-specific durability. Model it as an
   **endurance-readiness factor (0–1)** that widens the VDOT→*marathon* conversion (a 10K-VDOT with
   under-built volume doesn't convert to the same marathon time). It should leave the 5K/10K
   predictions essentially untouched.

### Output: a versioned `ReadinessDelta` (advisory, coach-confirmed)

A pure function (proposed `engine/readiness.adherence_adjustment(...)`) consumes the folded adherence
signals over a rolling window and returns (proposed shape):

```
ReadinessDelta {
    algo_version: int            # REQUIRED — see "Versioning" below
    window_weeks: int            # how many weeks of signals were considered
    vdot_delta: float            # adherence-adjusted minus expected-if-on-plan
    endurance_factor: float      # 0..1, scales the marathon conversion only
    suggested_calibrated_vdot: float
    drivers: list[str]           # the specific signals that moved it (provenance)
    inputs_digest: str           # hash of the signal set the delta was computed from
}
```

It is **advisory only**: the coach reviews it and, after the conversation, writes the
`WeeklyEvaluation` event (with `calibrated_vdot`) that actually folds into the plan. The
coach-in-the-loop boundary from §10 is preserved — the engine recommends, the coach decides.

### Versioning & auditability (hard requirement)

**Every delta must be versioned and persisted so we can analyze the data later and trace any number
back to how it was produced.** This rides on the existing append-only event log (§ event-sourcing):

- **Algorithm version on every delta.** `ReadinessDelta.algo_version` (mirroring `ClubPolicy.version`)
  is stamped on every computed delta. When we change the penalty curves, we bump the version — so a
  delta computed under v1 is never silently re-interpreted under v2. Later analysis can bucket deltas
  by `algo_version`.
- **Persist as an event, not a mutation.** A proposed `ReadinessDelta` event (or a versioned extension
  of `WeeklyEvaluation`) records `algo_version`, the `vdot_delta` / `endurance_factor`, the `drivers`,
  the `inputs_digest`, **and** both the *suggested* and the coach-*applied* values. Because events are
  append-only, the full history of "what the algorithm proposed vs. what the coach applied, under which
  algorithm version" is preserved for every week — replayable and auditable.
- **Reproducibility.** `algo_version` + `inputs_digest` together let us re-derive (or explain) any past
  delta. If a plan looks wrong months later, we can see exactly which signals and which algorithm
  version produced the adjustment.

### Surfacing

Extend the `tune-up-plan` / `review` report to show three columns per checkpoint:
**expected-if-on-plan** · **adherence-adjusted** · **goal-required** — making the on-track / re-anchor
contrast explicit at a glance.

### Open questions to define together (the algorithm)

1. How much VDOT does a fully-missed quality week cost (start conservative — perhaps half the week's
   expected gain)? Linear in missed fraction, or threshold-based?
2. The volume-ratio → `endurance_factor` curve (and how `LongRunIncomplete` weighs vs. total volume).
3. Rolling-window length, and whether recent weeks weigh more than older ones.
4. Floor/clamp behavior (a delta should never swing fitness more than is physiologically plausible
   in the window).

---

## 13. What is in code now (quick map)

| Concern | Function (`engine/readiness.py` unless noted) | Book anchor |
|---------|-----------------------------------------------|-------------|
| Predict race time from VDOT | `engine/vdot.predict_race_time`, `race_equivalent_times` | Daniels Table 5.1 |
| Realistic VDOT gain | `projected_vdot_gain`, `projected_vdot` | Principle 6, p.36 (fig 2.3) |
| Goal verdict + alternative | `goal_feasibility` → `GoalAssessment` | derived |
| Tune-up race ladder | `tune_up_ladder` → `TuneUpLadder`/`TuneUpCheckpoint` (CLI `tune-up-plan`) | derived |
| Tune-up result → VDOT + re-anchor | `engine/vdot.vdot_from_race` + `goal_feasibility` (CLI `record-tune-up`, `TuneUpResult` event) | derived |
| Freshness / trust race VDOT | `assess_freshness` | Daniels p.219 |
| Break adjustment | `break_adjustment_factor`, `adjusted_vdot` | Table 15.1, p.282 |
| Cross-training bucket | `classify_cross_training` | Daniels p.284 |
| Re-entry start | `recommended_reentry_volume` | Table 15.2, p.283 |
| Safe weekly increment | `safe_weekly_step` | Daniels p.219 |
| Recommended peak P | `recommended_peak_mileage` | Daniels p.219/p.232 |
| Hold-then-step ramp | `engine/plan/common.weekly_volumes` | Daniels p.219 |
| VO2max-vs-ramp balance | `engine/plan/common.volume_step_ups` + generators | Daniels p.36 / Pfitz ch.3 |
| Top-level coach report | `assess_readiness` → `ReadinessAssessment` | — |
| Athlete dossier (volume + VDOT-over-time + responder + goal realism) | `engine/athlete_profile.build_dossier` → `AthleteDossier` (CLI `athlete-report`) | derived |

## 14. Athlete dossier — operationalizing the manual study (read-only)

Before building a block a coach studies the athlete's past by hand: where did the last block actually
open, what mileage can they hold, has fitness moved and does it respond to volume, is the goal real,
how stale is the anchor. `engine/athlete_profile.py` is the **deterministic, repeatable** version of
that pass (CLI `athlete-report`). It is **pure** — given the same parsed history it always yields the
same `AthleteDossier` — and **mutates nothing**: every output is either a measured fact, an advisory
recommendation *string*, or a structured `ProposedInput` (a defensible `AthleteInputs` change). Turning
any of those into an actual change is a separate, coach-confirmed step — a proposed event, exactly as in
§12 (see "Feeding the dossier into plan creation" below).

What it computes:

- **`VolumeProfile`** — from the last block's capacity profile (`compute_capacity_profile` weeks):
  the *demonstrated opener* (median of the first up-to-3 active weeks — what the athlete actually
  started at, not a table default), the sustainable band (p25–p75 of active weeks), peak, average, and
  long-run dominance. This is the empirical counterweight to the `recommended_reentry_volume` table
  read: when an injury-prone athlete's demonstrated opener sits well above the off-season cap, the
  dossier surfaces the gap so the coach can lift `reentry_start_mpw` deliberately.
- **`FitnessTimeline`** — each race's VDOT over time paired with its **trailing 4-wk volume**, the
  Pearson **volume↔VDOT correlation**, the short-vs-marathon **endurance gap**, and an advisory
  **responder** label: `volume-sensitive` (VDOT rises with mileage — a real ramp is justified),
  `speed-dominant` (short-race VDOT well above the marathon; mileage should buy durability, not a
  higher ceiling), `stable` (VDOT flat across the observed range), or `insufficient-data` (<3 rated
  races). The label is explicitly advisory — tune-up results remain the source of truth.
- **`GoalRealism`** for A/B/C via `goal_feasibility`, and **`AnchorConfidence`** (staleness vs the
  `FRESH_ANCHOR_DAYS` ≈ 60 d threshold).

The CLI is the only impure part: it loads the baseline + latest plan (for the folded VDOT and current
opener) from the store and the race history + weekly feed from the `output/marathon/` artifacts, then
calls the pure `build_dossier`. Cross-athlete, the responder split is the signal worth accumulating —
e.g. a strongly volume-sensitive athlete vs. a speed-dominant one get different ramp and goal advice
from the same engine.

**Persisting the substrate (`dossier_snapshots`).** Every `athlete-report` and `publish-sheet` writes
an append-only `DossierSnapshot` (full dossier JSON + flattened query columns: responder, opener/peak/
sustainable-band mpw, volume↔VDOT correlation, endurance gap, current VDOT, anchor age/staleness,
injury-prone), stamped with `DOSSIER_VERSION` and the inputs fingerprint. This is what turns the
per-athlete read into a **fleet substrate**: `dossier-log` reads it to show the responder distribution,
anchor-staleness spread, opener gaps, and goal-realism spread across the roster (and one athlete's
trend across seasons), and `plan-log` joins `plan_artifacts` (now stamped with both `engine_version`
and `club_policy_version`) to `weekly_actuals` adherence. Engine/policy changes stay deferred until a
pattern is visible here — the "earn the change with data" surface. Bump `DOSSIER_VERSION` when the
responder thresholds, `FRESH_ANCHOR_DAYS`, or volume math change so snapshots stay comparable.

The dossier also feeds the **plan-sheet narrative** (summary, "personalized to you", notes), alongside
the accumulating execution summary (`engine/execution.py`) that drives the per-week "Why" feedback —
see [interpretation-layer.md §6a](interpretation-layer.md). That narrative is deterministic and
number-safe; `publish-sheet --llm-narrative` only smooths wording. When `publish-sheet --training`
points at the current-block feed, the execution summary scores every elapsed week so on-plan weeks earn
positive reinforcement and shortfalls become the stated reason for any conservative choices.

### Feeding the dossier into plan creation — proposed events, never silent mutations

`engine.athlete_profile.proposed_inputs` distills the dossier's defensible signals into concrete
`ProposedInput`s (field + value + rationale + the current value for the diff). It is conservative on
purpose: today it proposes the **re-entry opener** — anchoring `reentry_start_mpw` on the volume the
athlete has actually opened a block at, when the current plan opens meaningfully lower. Goal
re-anchoring stays a coach conversation (we never auto-propose changing someone's goal), and responder
framing stays advisory prose. `python main.py athlete-report --propose` writes each `ProposedInput` as a
`proposed` `ManualOverride` event plus one applied `CoachNote` for provenance; `review` approves and
`replan` folds — so the dossier shapes the plan only with explicit coach sign-off. Extend
`proposed_inputs` as more signals earn a clean, defensible field mapping.
