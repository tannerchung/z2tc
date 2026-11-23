# PRD, User Profiles, Garmin/Strava HITL Pace Calibration & Engineering Tickets (`detourrunclub.com/training`)

## Goal
Build an end-to-end interactive prototype on `detourrunclub.com/training` (`detour-web/public/training.html`) backed by deterministic `detour-engine` modules (`engine/pace_calibration.py` and `engine/web_prototype.py`) that adapts to distinct runner archetypes (**Tanner's Metrics/Physiology Mode** vs. **Cindy's "Tell Me What To Do + A Little Why" Mode** vs. **First-Timer Applied Mode**), ingests recent Garmin/Strava history to compute `E / M / T / I / R` paces, teaches the applied feel of each zone, and captures Human-in-the-Loop (HITL) comfort feedback before generating the plan.

---

## Current Context & Assumptions
- **Existing Deterministic Engine (`detour-engine`):**
  - `engine/paces.py :: training_paces(vdot)` computes continuous Daniels & Gilbert (1979) paces (`easy`, `marathon`, `threshold`, `interval`, `rep` plus integer seconds `easy_low_s`, `easy_high_s`, `marathon_s`, `threshold_s`, `interval_s`, `rep_s`).
  - `engine/plan/models.py :: AthleteInputs` already supports `vdot`, `goal_marathon_s`, `w_now` (4-wk Strava avg), `p_history` (block peak mpw), `decayed_peak_mpw`, `observed_long_pace_s` (actual Strava long-run pace), and `easy_pace_override_s` (narrowed easy band override).
  - `render/workout_glossary.py :: explain_workout_label(label)` already translates cryptic engine labels into plain-English instructions.
  - `store/events.py` already defines `ManualOverridePayload`, `DifficultyPayload`, `SetGoalPayload`, `CoachNotePayload`, and `SetCoachingScopePayload` for append-only event sourcing.
- **The Missing Product & UX Layer:**
  1. **Information Density Mismatch:** Data-hungry runners (like Tanner) want VDOT curves, `%VO2max`, Table 15.1 decay, and 1 Hz stream metrics, whereas action-oriented runners (like Cindy) just want to know *what to run today* and *one sentence of why it helps*.
  2. **Cold Pace Prescription Without Applied Context or HITL Feedback:** Ingesting Garmin/Strava data (`merge_strava_report`) yields a mathematical VDOT and 5 pace zones (`E, M, T, I, R`), but runners often run their Strava easy runs too fast ("grey-zone running") or have an older race PR that feels intimidating today. Furthermore, many runners cannot answer *"Are you comfortable with these paces?"* because they do not know what `E`, `M`, `T`, `I`, and `R` are supposed to feel like in practice.

---

## Architecture & Proposed Approach
We introduce a pure Python calibration and persona-adaptation module (`engine/pace_calibration.py`) that (1) compares ingested Garmin/Strava habits (`w_now`, `p_history`, `observed_long_pace_s`, source race VDOT) against prescribed Daniels zones, (2) generates an **Applied `E / M / T / I / R` Field Guide** pairing every pace with its real-world Talk Test, breathing cue, duration ceiling, and dual-persona explanation (**Tanner Telemetry View** vs. **Cindy Action + Why View**), and (3) resolves 4 Human-in-the-Loop (HITL) comfort choices into deterministic `AthleteInputs` adjustments and `EventPayload` records. We then export this complete state via `engine/web_prototype.py` to `detour-web/public/data/engine-prototype-bundle.json` and render it interactively in `detour-web/public/training.html`.

---

## 1. Product Requirements Document (PRD): User Profiles, Stories & HITL Calibration

### 1.1 Core User Profiles (Cognitive & Data-Appetite Archetypes)

| Dimension | Profile 1: "The Telemetry Architect" (**Tanner Archetype**) | Profile 2: "The Guided Executor" (**Cindy Archetype**) | Profile 3: "The Pace-Curious Builder" (**Maya Archetype**) |
| :--- | :--- | :--- | :--- |
| **Persona Mode Slug** | `telemetry` (`METRICS & PHYSIOLOGY`) | `guided` (`TELL ME WHAT TO DO + A LITTLE WHY`) | `applied_translator` (`TEACH ME THE ZONES FIRST`) |
| **Psychographic & Running Background** | Experienced marathoner (`VDOT 48–55`, Garmin Forerunner/Fenix + Strava). Loves systems, reads Pfitz/Daniels, tracks HR drift and cadence. | Busy NYC professional (`VDOT 38–46`, Apple Watch / Garmin). Consistent and hardworking, but has zero desire to decode acronyms or physiology papers. | Joined DRC via Saturday runs (`Tier 0` $\rightarrow$ `Tier 1/2`). Syncs Strava, runs almost every run at the same `~8:50/mi` social pace, new to structured intervals. |
| **Core Job-To-Be-Done** | *"Show me the exact math from my Garmin/Strava history, why my VDOT is 48.2, how Table 15.1 scaled my volume, and which physiological limiter each workout targets."* | *"Just tell me what to run on Tuesday in plain English, give me one clear sentence on why it helps me hit my goal, and push it to my watch."* | *"Explain the difference between E, M, T, I, and R in terms of how my breathing and legs should feel so I can tell you if the Strava-calculated paces feel right."* |
| **What Causes Drop-Off (Anti-Persona Friction)** | Black-box "trust the AI" plans that hide how paces or weekly mileage were derived. | Wall-of-numbers tables (`%VO2max`, `MCT1/MCT4`, `172 ms GCT`) and cryptic shorthand (`1.5E + 4x1.0T w/ 1:00 jg + 1.5E`). | Being asked *"Confirm your Threshold (7:48/mi) and Interval (7:12/mi) paces"* without knowing how `T` differs from `I` or `M`. |
| **How `training.html` Adapts to This Profile** | Displays raw + decayed VDOT, `%VO2max`, `w_now` vs `p_history`, 1 Hz H1/H2 drift, lineage citations (`Daniels`, `Canova`), and exact formula provenance. | Collapses raw math into a clean **Daily Action Card** powered by `explain_workout_label()` + a 1-sentence **"Why Today Matters"** callout. | Opens the **Applied `E / M / T / I / R` Talk-Test & Effort Translator** side-by-side with their Strava habits and offers a `"2-Week Guided Test Drive"` option. |

---

### 1.2 User Stories & Acceptance Criteria

- **`US-01` (Tanner — Metrics & Provenance Transparency):**
  - *As a* Telemetry Architect runner (`telemetry` mode), *I want to* see the exact Garmin/Strava race and 12-week mileage history that set my VDOT, my Table 15.1 detraining factor, `%VO2max` per zone, and the physiological mechanism (`lactate_shuttle`, `form_stiffness`) on every workout, *so that* I can verify and trust the engine's math.
- **`US-02` (Cindy — Plain-English Action + "A Little Why"):**
  - *As a* Guided Executor runner (`guided` mode), *I want* every workout translated from shorthand (`Cruise intervals: 1.5 mi E + 4 x 1.0 mi @ 7:33/mi w/ 1:00 jog + 1.5 mi E`) into a plain-English checklist with a single sentence explaining *why* we are doing it, *so that* I never have to decode running acronyms before heading out the door.
- **`US-03` (Garmin/Strava Habit vs. VDOT Discrepancy Detection):**
  - *As a* runner connecting Strava or Garmin, *I want* the system to compare my **VDOT-calculated paces** against my **actual recent Strava easy/long run paces (`observed_long_pace_s`)**, *so that* it catches when I'm running my easy days too fast ("grey-zone running") or when an old PR is too aggressive for my current fitness.
- **`US-04` (Applied Understanding of `E / M / T / I / R` Before Asking for Feedback):**
  - *As a* runner who doesn't know the textbook difference between `E`, `M`, `T`, `I`, and `R`, *I want* an interactive, plain-English guide that explains **how each pace feels in my body (Talk Test + breathing + duration ceiling + real-world NYC effort)** right next to my personalized numbers, *so that* I actually understand what I'm confirming.
- **`US-05` (HITL Comfort Check with Safe "I Don't Know Yet" Path):**
  - *As a* runner reviewing my Strava-derived paces, *I want* to tell the engine how comfortable I feel with those targets—including an honest *"I'm not sure yet, give me a 2-week guided test drive"* option—*so that* my plan starts at a level I can execute with confidence.

---

## 2. Step-by-Step Engineering Tickets (TDD Cycle)

1. **Ticket `DRC-101` (`detour-engine`):** Create `/Users/tanner/Documents/Projects/detour-engine/tests/test_pace_calibration.py` and `/Users/tanner/Documents/Projects/detour-engine/engine/pace_calibration.py` implementing `USER_PROFILES`, `build_applied_emtir_guide`, `diagnose_strava_pace_alignment`, `apply_pace_comfort_feedback`, and `format_workout_for_persona`.
2. **Ticket `DRC-102` (`detour-engine`):** Create `/Users/tanner/Documents/Projects/detour-engine/tests/test_web_prototype.py`, `/Users/tanner/Documents/Projects/detour-engine/engine/web_prototype.py`, and `/Users/tanner/Documents/Projects/detour-engine/scripts/export_web_prototype_bundle.py` to export `/Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`.
3. **Ticket `DRC-103` (`detour-web`):** Build `/Users/tanner/Documents/Projects/detour-web/public/training.html` with the Persona View Switcher (`Tanner Mode` vs. `Cindy Mode` vs. `First-Timer Applied Mode`), Garmin/Strava Ingestion & HITL Comfort Calibration Studio, Tier 0–3 Switcher, 4-Stage Progressive Disclosure Scrubber, and 23-Workout Catalog.
4. **Ticket `DRC-104` (`detour-web` + QA):** Point `/coaching` $\rightarrow$ `/training` in `vercel.json`, update `/coaching-intake.html` (`?tier=`, `?persona=`, `?comfort=` pre-fill + `16px` mobile inputs + canonical `#121214` / `#B8BDC3` tokens), add `TRAINING ENGINE` nav links to `profile.html` and `connect.html`, and verify via `pytest` and headless browser.

(Full copy-pasteable code for every ticket is in `/Users/tanner/.hermes/plans/2026-11-13_213549-detour-user-profiles-hitl-paces-and-prd.md`.)
