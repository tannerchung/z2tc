# Multi-Stage PRD, Athlete Personas, Infrastructure, User Flows, Wireframes & TDD Implementation Plan (`detourrunclub.com/training`)

## Goal
Deliver the Detour Adaptive Training & Pace-Calibration experience across **4 iterative, independently testable stages (`Stage 0 MVP` $\rightarrow$ `Stage 1` $\rightarrow$ `Stage 2` $\rightarrow$ `Stage 3`)**, built around **3 universal Athlete Personas (`Analytical`, `Directive`, `Foundational`)**—never named after individuals—with complete PRD specifications, infrastructure contracts, user flows, wireframes, design system tokens, user stories, and copy-pasteable TDD tasks for each stage.

---

## Universal Athlete Personas (Replacing Personal Names Across Code, Schema & UI)

| Persona ID | UI Tab Label | Target Runner Profile | How Workouts, Paces & Diagnostics Render |
| :--- | :--- | :--- | :--- |
| **`analytical`** | **`METRICS & PHYSIOLOGY`** | Data-fluent performance runners who want VDOT provenance, `%VO2max`, Table 15.1 decay factors, and physiological limiters (`MCT1/MCT4`, `GCT`). | Shows `.FIT` watch string + `%VO2max` + physiological mechanism + Strava-vs-Chip math. |
| **`directive`** | **`ACTION + THE WHY`** | Action-oriented runners who want high-conviction direction in plain English plus one clear sentence on why today's session matters. | Translates shorthand via `explain_workout_label()` into a step-by-step run brief + 1-line `Why Today Matters`. |
| **`foundational`** | **`APPLIED ZONE GUIDE`** | Runners newer to structured zones (`E, M, T, I, R`) stepping up from group runs who need Talk-Test cues and breathing rhythms. | Anchors every pace and workout in **Talk-Test & Perceived Effort cues** (`"3–4 words max, 7/10 effort"`) and highlights the `2-Week Guided Test Drive`. |

---

## Stage-by-Stage Summary

1. **Stage 0 MVP (PR #1 · 0 Existing Files Modified):**
   - **Features:** 3 Archetype Runner Feeds (`archetype_fade`, `archetype_greyzone`, `archetype_debut`), 3 Athlete Persona Lenses (`analytical`, `directive`, `foundational`), Strava Habit vs. VDOT Easy Diagnostic Banner, 5-Zone Applied `E/M/T/I/R` Field Guide, 4-Option HITL Pace Comfort Gate (`lock_prescribed`, `match_strava_easy`, `step_down_gentler`, `unsure_2wk_trial`), and Live 7-Day Adaptive Week Schedule.
   - **Infrastructure:** `engine/pace_calibration.py` + `tests/test_pace_calibration.py` + `scripts/export_web_prototype_bundle.py` $\rightarrow$ `public/data/engine-prototype-bundle.json` + standalone `public/training.html`.
2. **Stage 1 (PR #2 · Official Multi-Distance Race Curve & 23-Workout Catalog):**
   - **Features:** `analyze_official_race_curve()` (`5K` $\rightarrow$ `10K` $\rightarrow$ `Half` $\rightarrow$ `Marathon` VDOT fade + GPS-vs-Official-Chip delta) and the interactive 23-Workout Catalog (`CATALOG_WORKOUTS`) filterable by physiological category and limiter.
3. **Stage 2 (PR #3 · Continuous Post-Onboarding Coaching Feedback Loop & 4-Week Progressive Disclosure):**
   - **Features:** Schema persistence (`communication_profile`, `coaching_voice`, `pace_comfort_choice`, `nyrr_member_id`) on `AthleteInputs`, `SurveyInputs`, and `SetCoachingScopePayload`; Post-Onboarding Coaching Voice Switcher (`direct_concise`, `warm_supportive`, `high_accountability`); and the Week 1 $\rightarrow$ Week 4 $\rightarrow$ Week 10 $\rightarrow$ Week 13 Progressive Disclosure Scrubber.
4. **Stage 3 (PR #4 · Production Funnel & Entity Firewall Integration):**
   - **Features:** `Tier 0` (501(c)(3) `#F4581C`) vs. `Tiers 1–3` (`Detour Athletics LLC` `#38BDF8`) switcher, `vercel.json` (`/coaching -> /training`), nav pills on `profile.html` & `connect.html`, and URL query pre-fill (`?tier=&persona=&voice=&comfort=`) on `/coaching-intake.html`.

(Full PRD, user stories `US-S0-01..04` through `US-S3`, desktop `1440px` & mobile `375px` ASCII wireframes, design tokens, and complete copy-pasteable TDD code are in `/Users/tanner/.hermes/plans/2026-11-13_231055-detour-staged-prd-personas-wireframes-and-spec.md`.)
