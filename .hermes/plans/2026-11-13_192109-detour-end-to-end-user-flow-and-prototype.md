# Detour End-to-End Tiered User Flow & Interactive Prototype Plan (`detourrunclub.com/training`)

## Goal
Define the concrete end-to-end user journey from Free Club Member (`Tier 0`) through Paid Coaching Tiers (`Tier 1`, `Tier 2`, `Tier 3`) and prototype an interactive Training Engine & Tier Simulator directly inside `detourrunclub.com` (`detour-web/public/training.html`) backed by deterministic `detour-engine` JSON artifacts—without spinning up a separate `detourathletics.com` codebase.

---

## Strategic Decision: `detourrunclub.com` First vs. Separate `detourathletics.com` Site

**Recommendation: Build and prototype directly on `detourrunclub.com` (`detour-web`) under `/training` and `/coaching-intake` first. Do NOT stand up a separate `detourathletics.com` website right now.**

### Why `detourrunclub.com` First Wins
1. **Single Identity, Passport & Wearable Graph (`core.people`):**
   - Runners already authenticate via `detour-member-auth.js`, store their PRs and Pace Pocket on `/profile`, RSVP to races on `/races`, and link Garmin/Strava OAuth on `/connect`.
   - A separate `detourathletics.com` site would force a second login, duplicate Strava/Garmin OAuth callbacks, and split the runner's passport across two domains.
2. **Clean Legal & Tax Firewall Without Two Websites:**
   - IRS 501(c)(3) and NY General Obligations Law § 5-326 require **legal, contractual, and financial separation**—not separate HTML repositories.
   - **Visual & Legal Seam (Already established in `public/coaching-intake.html`):**
     - **Detour Run Club Inc. (501(c)(3)) pages (`/join`, `/races`, `/drops`):** Use **Detour Orange (`#F4581C`)**, `$0.00` dues, and the non-profit RRCA waiver (`drc-rrca-v2026.1`).
     - **Detour Athletics LLC pages (`/training`, `/coaching-intake`):** Display the **Cyan (`#38BDF8`) Commercial Entity Banner** (*"Provided by Detour Athletics LLC, an independent coaching practice separate from Detour Run Club Inc. 501(c)(3)"*), require the PAR-Q+ & LLC Commercial Coaching Agreement (`drc-llc-coaching-v2026.1`), and route paid upgrades exclusively to Detour Athletics LLC's commercial Stripe checkout.
   - **Bonus Host-Rewrite Option:** Just like `cms.detourrunclub.com` already rewrites `/` to `/admin.html` in `detour-web/vercel.json` (lines 5–14), if you ever want `detourathletics.com` as a standalone domain later, you can point its DNS to the exact same `detour-web` Vercel deployment and rewrite `/` $\rightarrow$ `/training.html` with zero duplicate code.
3. **Natural Upgrade Funnel:**
   - Every runner enters the top of the funnel as a Free 501(c)(3) Club Member on `/join` $\rightarrow$ lands on `/profile` $\rightarrow$ sees their free VDOT Pace Card & Saturday Group Long-Run Pocket $\rightarrow$ upgrades in one click on `/training` when they want a full 16-week adaptive plan, watch workouts, and Coach Kip / Head Coach Tanner support.

---

## Concrete End-to-End User Flow: Tier 0 $\rightarrow$ Tier 1 $\rightarrow$ Tier 2 $\rightarrow$ Tier 3

This table maps what the runner actually sees, signs, pays, and unlocks at every step of the journey:

| Dimension | Tier 0 · Free Club Member (`Detour Run Club Inc. 501(c)(3)`) | Tier 1 · Detour Engine Self-Serve (`Detour Athletics LLC`) | Tier 2 · Adaptive Engine + Coach Kip Check-Ins (`Detour Athletics LLC`) | Tier 3 · 1:1 Head Coach Tanner + Full Forensics (`Detour Athletics LLC`) |
| :--- | :--- | :--- | :--- | :--- |
| **Price & Entity** | **`$0.00 / forever`** (501(c)(3) Non-Profit) | **`$29 / mo`** (or `$99 / race block` · LLC) | **`$69 / mo`** (LLC Guided Adaptive) | **`$150 / mo`** Founding Cohort (LLC 1:1) |
| **Entry Route on `detourrunclub.com`** | `/join` $\rightarrow$ `/profile` | `/training` $\rightarrow$ `/coaching-intake?tier=tier1_engine` | `/training` $\rightarrow$ `/coaching-intake?tier=tier2_guided` | `/training` $\rightarrow$ `/coaching-intake?tier=tier3_1on1` |
| **Legal Gate** | RRCA Club Waiver (`drc-rrca-v2026.1`) | 7-Q PAR-Q+ + LLC Agreement (`drc-llc-coaching-v2026.1`) | 7-Q PAR-Q+ + LLC Agreement (`drc-llc-coaching-v2026.1`) | 7-Q PAR-Q+ + LLC Agreement + 1:1 Consult |
| **Day 1 Onboarding Inputs** | Name, Email, Borough, Self-Selected Pace Pocket (`Front` / `Middle` / `Social`), Optional PR | Goal Race + Date, Recent Race/PR (or Estimated Pace), Current/Peak Weekly Miles, Days/Week (`3–7`), Long Run Day | Same as Tier 1 + Strava/Garmin OAuth link (`/connect`) + WhatsApp/Web Check-In channel | Same as Tier 2 + Orthopedic/Injury History, Shoe Quiver, 1:1 Kickoff Call with Tanner |
| **What They Get on Day 1 (Week 1 UI)** | • Digital Runner Passport (`/profile`)<br>• Assigned Group Pace Pocket<br>• VDOT Equivalent Training Paces (`E, M, T, I, R`)<br>• Weekly Club Run RSVP (`/races`) | • Full 12–18 Wk Deterministic Plan (`build_club_plan`)<br>• Interactive 23-Workout Dictionary (`/training`)<br>• 1-Click `.ICS` Calendar + Google Sheet Export<br>• **Zero nutrition/sensor clutter on Day 1** | • Everything in Tier 1<br>• **Auto Push-to-Watch** (`.FIT` / Garmin Connect)<br>• **Progressive Coaching Unlocks** (1 prompt at a time via `onboarding_milestones.py`)<br>• Weekly Replan (`replan.py`) when life/travel happens | • Everything in Tier 2<br>• **1 Hz Stream Forensics** (H1/H2 Decoupling, GCT/Stride Stiffness, Limiter Routing)<br>• Custom Workout Swaps (`Canova`, `Hudson Hills`, `Mona`)<br>• Race-Day Course & Gut Blueprint + Bi-Weekly 1:1 Review |
| **Engine Scope Flags Active (`AthleteInputs`)** | None (Static VDOT lookup + group pocket) | All 4 secondary scope flags `False` by default (pure paces & mileage progression) | Progressively unlocked at milestones:<br>• **1st Run $\ge 12\text{ mi}$:** `enable_fueling_guidance=True`<br>• **Peak/Warm ($\le 8\text{ wtg}$ or $\ge 65^\circ\text{F}$):** `enable_hydration_weather=True` | Full telemetry unlocked as needed:<br>• `enable_fueling_guidance=True`<br>• `enable_hydration_weather=True`<br>• `enable_biomechanics_forensics=True`<br>• `enable_readiness_gates=True` |

---

## How Progressive Disclosure Works Across the Training Timeline (What the Runner Experiences)

Instead of dumping every feature of `detour-engine` onto the screen on Day 1, the prototype demonstrates the **4-Stage Progressive Timeline**:

1. **Stage A — Week 1 (Day 1 Onboarding · Cognitive Load = Minimal):**
   - **Runner sees:** Their 5 VDOT training zones (`Easy`, `Marathon`, `Threshold`, `Interval`, `Repetition`), their Week 1 schedule (`Tue Quality`, `Thu Quality`, `Sat Group Long Run`), and 1-click Watch/Calendar sync.
   - **Hidden (`False`):** No gel calculators, no sweat-sodium prompts, no HRV/GCT charts.
2. **Stage B — Week 4 (Milestone 1: First Long Run $\ge 12.0\text{ mi}$ / $\ge 90\text{ min}$):**
   - **Engine Trigger:** `next_onboarding_prompt()` detects `long_run_miles >= 12.0` with `enable_fueling_guidance=False`.
   - **Runner sees a 1-question card:** *"Saturday is your first 12-miler (~1h45m). What gel, chew, or drink mix do you like carrying?"* (`[Maurten 100]` `[Huma Chia]` `[Precision PF30]` `[Recommend one]`).
   - **Result:** Emits `SetCoachingScopePayload(enable_fueling_guidance=True)` $\rightarrow$ Week 4+ Long Run cards now display a clean 1-line `FUELING TIP` pill (`~40–60g carbs/hr · 1 gel every 30–35 min + water`), while keeping watch workout step labels 100% clean.
3. **Stage C — Week 10 (Milestone 2: Entering Peak Build $\le 8\text{ wtg}$ or Warm Weather $\ge 65^\circ\text{F}$):**
   - **Engine Trigger:** `next_onboarding_prompt()` detects `wtg <= 8` or `ambient_temp_f >= 65.0` with `enable_hydration_weather=False`.
   - **Runner sees a 1-question card:** *"Do you get white salt stains on your hat/singlet or calf tightness on warm runs?"* (`[Salty Sweater]` `[Moderate]` `[Low]`).
   - **Result:** Emits `SetCoachingScopePayload(enable_hydration_weather=True, sweat_sodium_tier="salty")` $\rightarrow$ Long run card adds dynamic fluid (`650–900 mL/hr`) & sodium (`800–1200 mg/hr`) targets.
4. **Stage D — Week 12–15 (Milestone 3: Tier 3 Limiter Routing + Dress Rehearsal Carb Load):**
   - **Engine Trigger (Tier 3):** 1 Hz Garmin/Strava stream detects late-run cadence/GCT drift (`form_stiffness`) or marathon-pace lactate accumulation (`lactate_shuttle`).
   - **Runner/Coach sees:** Deterministic workout swap recommendation from the 23-workout catalog (`workouts_for_limiter("form_stiffness")` $\rightarrow$ swaps standard intervals for `hill_repeats` or `rolling_400s`; `lactate_shuttle` $\rightarrow$ `canova_alternations` or `over_unders`), plus the 48-hour Dress Rehearsal Carb-Load card (`8–10g/kg/day`) at `wtg == 4`.

---

## Architecture / Proposed Approach

We will build a deterministic, zero-dependency prototype bridge between `detour-engine` and `detour-web` (`detourrunclub.com`):
1. **Deterministic Fixture Generator in `detour-engine` (`scripts/export_web_prototype_bundle.py`):** Runs `build_club_plan()`, `next_onboarding_prompt()`, `nutrition_for_long_run()`, `workouts_by_category()`, and `workouts_for_limiter()` across realistic athlete states (Week 1 Day 1, Week 4 First 12-Miler, Week 10 Peak Build + Salty Sweater, Week 13 Dress Rehearsal + Tier 3 Limiter Swap) and exports a canonical JSON bundle to `/Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`.
2. **Interactive Prototype Hub on `detourrunclub.com` (`/Users/tanner/Documents/Projects/detour-web/public/training.html`):** A flagship interactive page on `detourrunclub.com` (`/training`) where you (and prospective athletes) can:
   - Toggle between **Tier 0 (Free Club)**, **Tier 1 (Engine Self-Serve)**, **Tier 2 (Guided + Progressive Milestones)**, and **Tier 3 (1:1 Coaching + 1 Hz Limiter Forensics)**.
   - Scrub along the **Training Timeline (`Week 1` $\rightarrow$ `Week 4` $\rightarrow$ `Week 10` $\rightarrow$ `Week 13`)** to see the exact progressive disclosure prompts appear and unlock engine flags in real time.
   - Explore the **23-Workout Categorized Catalog** filterable by the 7 physiological buckets and athlete limiters (`form_stiffness`, `lactate_shuttle`, `aerobic_ceiling`, `hill_strength`).
   - Click straight into `/join` (Tier 0), `/connect` (Watch Sync), or `/coaching-intake?tier=...` (Paid LLC Upgrade).
3. **Wire Navigation & Routing (`vercel.json`, `public/profile.html`, `public/coaching-intake.html`):** Update `/coaching` redirect in `vercel.json` to point to `/training`, add a `TRAINING ENGINE` pill to `/profile` and `/connect`, and pre-select the chosen tier query parameter (`?tier=...`) on `/coaching-intake`.

---

## Step-by-Step Implementation Tasks

### Task 1: Create the Deterministic Web Prototype Exporter in `detour-engine`
- **Files:**
  - Create `/Users/tanner/Documents/Projects/detour-engine/engine/web_prototype.py`
  - Create `/Users/tanner/Documents/Projects/detour-engine/scripts/export_web_prototype_bundle.py`
  - Create `/Users/tanner/Documents/Projects/detour-engine/tests/test_web_prototype.py`
- **Verification Command:**
  `cd /Users/tanner/Documents/Projects/detour-engine && python3 -m pytest -q tests/test_web_prototype.py`
  Expected output: `2 passed`.

### Task 2: Export `/Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`
- **Files:**
  - Generate `/Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`
- **Verification Command:**
  `cd /Users/tanner/Documents/Projects/detour-engine && python3 scripts/export_web_prototype_bundle.py && ls -lh /Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`

### Task 3: Build the Interactive Prototype Page (`/Users/tanner/Documents/Projects/detour-web/public/training.html`)
- **Files:**
  - Create `/Users/tanner/Documents/Projects/detour-web/public/training.html`
- **Features:**
  1. **Interactive Tier Switcher (`Tier 0` $\rightarrow$ `Tier 1` $\rightarrow$ `Tier 2` $\rightarrow$ `Tier 3`)** showing exact legal entity, price, Day-1 onboarding inputs, and unlocked engine features.
  2. **Live VDOT & Pace Pocket Calculator** (`E, M, T, I, R` paces + DRC Front/Middle/Social Pocket mapping).
  3. **4-Stage Progressive Disclosure Timeline Simulator (`Week 1` $\rightarrow$ `Week 4` $\rightarrow$ `Week 10` $\rightarrow$ `Week 13`)** rendering real `detour-engine` output, showing which `SetCoachingScope` flags are locked vs. unlocked, the exact Coach Kip 1-question milestone card, and how `Workout.label` stays clean while `PlannedWeek.flags` displays the informal `fueling_tip`.
  4. **Interactive 23-Workout Categorized Catalog & Limiter Filter** across the 7 physiological categories and 8 coaching lineages (`Daniels`, `Canova`, `Hudson`, `Runna`, `Pfitzinger`, `Hansons`, `Higdon`, `Moneghetti`).

### Task 4: Wire `/training` into `vercel.json`, `coaching-intake.html`, `profile.html`, and `connect.html`
- **Files:**
  - Modify `/Users/tanner/Documents/Projects/detour-web/vercel.json`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/coaching-intake.html`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/profile.html`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/connect.html`
- **Verification Command:**
  Run `pytest` in `detour-engine` and verify `training.html` renders all 4 tiers, 4 progressive timeline stages, and 23 catalog workouts cleanly.
