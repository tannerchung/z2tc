# Stage 0–3 Specification & TDD Plan: Window 2 Run-Feedback & Readjustment Notification UX + Common Race Distance Estimator & No-Race Benchmarking (`detour-engine` + `detour-web`)

## Goal
Extend the Stage 0 MVP and closed-loop coaching pipeline with **(1)** an explicit **Window 2 Post-Run Feedback & Readjustment Notification UX** (showing the athlete feedback on their completed run, the exact `Before -> After` readjustment to tomorrow's workout, and a 3-button confirmation/override bar) and **(2)** an **Estimated Race Times Table across 7 common distances (`1 Mile`, `5K`, `4 Miles`, `10K`, `10 Miles`, `Half Marathon`, `Marathon`)** paired with a **4-Mode Athlete Benchmark Selector** (especially for athletes without an upcoming race on the calendar).

---

## Summary of Additions to Stage 0 MVP

1. **Window 2 Evening Run-Feedback & Tomorrow Readjustment Notification UX (`window2_notification`):**
   - When `compute_narrative_sha256(activity)` detects an athlete's Strava note or watch upload (or at the `8:00 PM` evening review), the athlete receives a structured **Evening Readjustment Card** with three parts:
     - **Part A — Feedback on Today's Completed Run:** Quotes her Strava note (*"Pushed over Queensboro Bridge, calves a little tight"*) + watch telemetry (`9:35/mi` pace vs. `10:21–11:18/mi` Easy band, `164 spm` cadence) and delivers coaching feedback in her active UI lens (`SIMPLE & CLEAR` by default).
     - **Part B — Transparent `Before -> After` Tomorrow Readjustment Diff:** Shows the exact change (`Thu 3 x 1.0 mi @ 8:55/mi` $\rightarrow$ `3 x 1.0 mi @ 9:05/mi + 2-Min Calf Warm-Up`) and explains *why* it was adjusted so she is never surprised the next morning.
     - **Part C — 3-Button Athlete Confirmation / Override Bar:**
       1. **`[✓ Keep Adjusted Plan (9:05/mi)]`** (Default if untouched by morning)
       2. **`[↩ Restore Original Target (8:55/mi) — My Legs Feel Fine]`** (Lets her override if her Strava note was just casual banter)
       3. **`[💬 Text Coach Tanner to Customize Tomorrow]`** (Flags Coach Tanner directly)
2. **Estimated Race Times Across 7 Common Distances (`build_estimated_race_times_table`):**
   - Computes **Current Equivalent**, **+8-Week Build Projection**, and **+16-Week Peak Projection** (plus side-by-side comparison to any Official NYRR PR) across:
     `1 Mile` (`1609m`) · `5K` (`5000m`) · `4 Miles (NYRR Central Park Loop)` (`6437m`) · `10K` (`10000m`) · `10 Miles (Bronx 10M)` (`16093m`) · `Half Marathon` (`21097.5m`) · `Marathon` (`42195m`).
3. **"How Do You Want to Benchmark Progress?" Selector (`BENCHMARK_MODES` — Built for Both Racing & Non-Racing Athletes):**
   - **`1. submax_workout_check` ("Benchmark Me From My Regular Workouts — Zero Race Stress"):** Repeats a controlled Threshold/Progression session every 4 weeks; when HR/RPE drops at the same pace, VDOT levels up `+0.5` automatically with zero time-trial stress.
   - **`2. club_loop_check` ("Monthly 5K or Central Park 4-Mile Loop Check-In"):** Uses a low-key 4M/5K effort at Week 6 & Week 12.
   - **`3. upcoming_race_ladder` ("I Have a Target Race on the Calendar"):** Uses `tune_up_ladder()` (`5K -> 10K -> 10K` checkpoints).
   - **`4. consistency_habit_first` ("Skip Time Benchmarks for Now — Track My Weekly Consistency"):** Focuses on hitting `4/4` weekly runs and keeping Easy days conversational.

(Full wireframes, data schemas, and TDD tasks `Tasks 0.1–0.3` are in `/Users/tanner/.hermes/plans/2026-11-13_234224-detour-window2-readjustment-ux-and-race-benchmark-estimator.md`.)
