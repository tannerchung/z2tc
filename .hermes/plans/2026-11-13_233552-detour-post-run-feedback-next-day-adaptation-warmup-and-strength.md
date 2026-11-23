# Closed-Loop Coaching Specification & Stage 0–3 Plan: Strava Notes + Garmin Next-Day Adaptation, Post-Run Feedback, Warm-Ups & Metric-Driven Strength (`detour-engine` + `detour-web`)

## Goal
Define and implement the closed-loop daily coaching pipeline that **(1)** ingests completed Strava notes and Garmin telemetry across three daily windows to trigger automatic **Next-Day Workout Adjustments**, **(2)** delivers structured **Post-Run Execution Feedback** in the athlete's chosen UI lens (`SIMPLE & CLEAR`, `LEARN BY FEEL`, `DEEP DATA & SCIENCE`), and **(3)** attaches deterministic **Workout-Specific Warm-Ups** and **Metric-Driven Strength/Prehab Prescriptions** drawn directly from the athlete's race curve, watch biomechanics, and Strava notes.

---

## Summary of the 3 New Closed-Loop Capabilities

1. **When Strava Notes & Garmin Metrics Trigger Next-Day Adjustments (3 Daily Windows):**
   - **Window 1 (`T + 5 mins` Immediate Watch Sync):** Pulls splits, HR, cadence, GCT, L/R balance, and shoe mileage; generates instant post-run feedback; triggers `needs_post_run_narrative_nudge()` if a key workout has blank notes.
   - **Window 2 (`T + 2h to 8:00 PM` Delayed Strava Note Harvest & Next-Day Triage):** Uses `compute_narrative_sha256(activity)` (`engine/narrative_capture.py`) to catch Strava notes/RPE added later in the day and locks tomorrow's workout before bedtime:
     - **`GREEN` (Keep Tomorrow As Planned):** Controlled execution.
     - **`YELLOW` (Auto-Modulate Tomorrow):** If an Easy run was run in the grey zone (`>25s/mi` too fast) or notes mention `"heavy legs"` / `"tight calves"`, softens tomorrow's Quality reps by `+10s/mi` (or trimsEasy volume).
     - **`RED` (Protect & Alert Coach Tanner):** If Strava note flags sharp/focal pain (`"achilles"`, `"shin"`, `"sharp"`) or L/R GCT asymmetry `>= 52/48%`, converts tomorrow to Rest/Cross-Train and alerts Coach Tanner.
   - **Window 3 (`6:00 AM` Next-Morning Garmin Readiness Gate):** Optional overnight HRV (`rMSSD` vs. 7d baseline) + sleep check (`< 5.5h`) offering a 1-tap workout swap on Quality mornings.
2. **Workout-Specific Dynamic Warm-Ups (`build_workout_warmup_protocol`):**
   - `Easy/Recovery` (`3 min` out-the-door ankle/hip mobility + slow Mile 1 rule), `Threshold/MP` (`6 min` activation + `1.5 mi` jog + `3x15s` pickups), `Interval/Rep` (`8 min` drills + pogos + `4x20s` strides), `Saturday Long Run` (`4 min` glute medius + single-leg calf wake-up).
3. **Metric-to-Conclusion-to-Strength Engine (`derive_strength_and_form_prescriptions`):**
   - Draws explicit deterministic conclusions from the athlete's race curve, Garmin cadence/GCT, and Strava notes (`calf_tendon_spring_and_turnover`, `eccentric_quad_and_late_race_durability`, `pelvic_glute_medius_stability`) and prescribes **3 high-leverage exercises (`8–10 mins, 2x/week`)** with a clear *"What We Saw in Your Data $\rightarrow$ Why These 3 Moves Fix It"* explanation.

(Full architecture, wireframes, and TDD tasks `Tasks 0.1–0.3` are in `/Users/tanner/.hermes/plans/2026-11-13_233552-detour-post-run-feedback-next-day-adaptation-warmup-and-strength.md`.)
