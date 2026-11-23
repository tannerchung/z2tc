# High-Touch Coach-Gated Co-Pilot Specification & Stage 0–3 TDD Plan: Weekly Rolling Plans, 23-Workout Menu, Chicago-Style Biomechanical Exercise Prescriptions, and Manual Coach Un-Gating (`detour-engine` + `detour-web`)

## Goal
Design and implement a **High-Touch Coach-in-the-Loop Coaching Experience** where **(1)** the athlete sees a **Macro Full-Block Roadmap** while detailed workouts are unlocked **weekly**, **(2)** the engine draws from the full **23-Workout Catalog (`engine/plan/workouts.py`)** and **Chicago Marathon 1 Hz Biomechanical Forensics (`GCT > 260 ms`, `Stride Length < 120 cm`, `Vertical Ratio > 8.0%`)** to recommend relatable, muscle-specific exercises, and **(3)** post-run feedback and workout modifications are **never robotically auto-applied**—instead, the engine **alerts Coach Tanner**, who analyzes the data with the engine, adds his personal note, and **manually ungates** the feedback and next-day modification to the athlete.

---

## Summary of the 4 High-Touch Upgrades

1. **Macro Full-Block Roadmap + Weekly Rolling Workout Assignment (`build_macro_roadmap_and_weekly_release`):**
   - The athlete sees the **entire 12–16 week Phase & Mileage Arc** (`Phase I: Foundation` $\rightarrow$ `Phase II: Threshold` $\rightarrow$ `Phase III: Race Prep` $\rightarrow$ `Phase IV: Taper`) plus her **7-Distance Estimated Race Times**, while exact daily workouts are **unlocked one week at a time each Sunday** after Coach Tanner reviews her week.
2. **The Full 23-Workout Menu (`engine/plan/workouts.py :: CATALOG_WORKOUTS`):**
   - Exposes all 5 workout families (`Broken-T Half-Miles`, `Cruise Miles`, `Descending T Ladder`, `Over/Unders`, `Canova 1K/1K Alternations`, `20-Min Park Mona Fartlek`, `VO2 Pyramid / Drop Set`, `60s Uphill Repeats`, `Rolling 400s`, `Progression Long Run`, `Long Run w/ Fartlek`, `Marathon-Pace Blocks`, `Fast-Finish Long Run`) so Coach Tanner can swap in the exact right stimulus.
3. **Chicago-Grade Relatable Biomechanics $\rightarrow$ Exercise Prescriptions (`derive_strength_and_form_prescriptions`):**
   - Connects real watch/race breakdowns directly to relatable stories and specific 8-minute routines:
     - **Feet Sticking / Tight Calves (`GCT > 260 ms` in Chicago Miles 22–25 or on NYC Bridges):** *Stiff-Ankle Pogo Hops (`3x25`)* + *Heavy Slow Bent-Knee Soleus Raises (`3x12/side`)* to keep `GCT < 240 ms`.
     - **Late-Race Shuffle (`Stride Length < 120 cm` after Mile 20):** *Straight-Leg Bounds (`3x30m`)* + *Single-Leg RDLs (`3x8/side`)* + *Side Plank w/ Leg Lift* to keep hip extension `130+ cm` when fatigued.
     - **Wasted Vertical Bounce & Bridge Quad Trash (`Vertical Ratio > 8.0%`):** *A-Skips & B-Skips (`3x30m`)* + *Slow Eccentric Box Step-Downs (`3x10/side`)* + *8-Sec Steep Hill Strides* (zero eccentric pounding).
4. **High-Touch Coach Tanner Un-Gating (`build_coach_copilot_review_packet` + `apply_coach_ungate_decision`):**
   - Instead of instant robotic feedback, a completed run enters `PENDING_COACH_REVIEW` (`"Run Synced · In Coach Tanner's Review Queue"`).
   - The engine alerts Coach Tanner with the side-by-side analysis, 4 modification options from the 23-workout catalog, and a pre-drafted personal note; once Tanner edits/approves and clicks **`[🔓 Ungate & Send to Athlete]`**, the feedback and modified workout unlock on the athlete's view.

(Full wireframes, schemas, and TDD steps `Tasks 0.1–0.3` are in `/Users/tanner/.hermes/plans/2026-11-13_235123-detour-coach-gated-copilot-workout-variety-and-chicago-biomech.md`.)
