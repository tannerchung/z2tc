# Product Requirements Document (PRD), Technical Specification & Engineering Tickets: Detour Training Engine & Tiered Onboarding Prototype (`detourrunclub.com/training`)

## Goal
Ship a production-grade interactive prototype at `detourrunclub.com/training` (`detour-web/public/training.html`) backed by deterministic `detour-engine` JSON artifacts (`public/data/engine-prototype-bundle.json`) that lets runners experience the complete `Tier 0` (Free Club) $\rightarrow$ `Tier 1` (Engine Self-Serve) $\rightarrow$ `Tier 2` (Guided Adaptive + Coach Kip) $\rightarrow$ `Tier 3` (1:1 Forensics) journey before hitting the legal/medical intake wall on `/coaching-intake`.

---

## 1. Product Requirements Document (PRD)

### 1.1 Executive Summary & Problem Statement
Right now, `detour-engine` contains a complete deterministic physiological engine (357 passing tests across VDOT math, Table 15.1 volume decay, 23 categorized workouts across 8 coaching lineages, 4-stage progressive disclosure milestones, and 1 Hz biomechanics/limiter routing), while `detour-web` contains disconnected onboarding endpoints (`/join`, `/profile`, `/connect`, `/coaching-intake`).

**The Core Product Failure Today:**
1. **No "Aha Moment" Before the Legal Wall:** Visiting `detourrunclub.com/coaching` currently redirects straight to `/coaching-intake.html`, which greets the runner with an `admin_only` gate, a 7-question PAR-Q+ medical questionnaire, and a 2,000-word LLC liability waiver *before* they have seen a single training week, VDOT pace zone, Garmin watch step, or progressive milestone.
2. **Invisible Tier Differentiation:** Runners (and stakeholders) cannot see what changes when moving from a **Tier 0 Free Club Member (`$0`)** to **Tier 1 Engine Self-Serve (`$29/mo`)**, **Tier 2 Guided Adaptive (`$69/mo`)**, or **Tier 3 1:1 Head Coach Tanner (`$150/mo`)**.
3. **Domain Confusion (`detourrunclub.com` vs. `detourathletics.com`):** Splitting the prototype onto a second website (`detourathletics.com`) would fracture authentication (`detour-member-auth.js`), duplicate Strava/Garmin OAuth (`api/strava-oauth.js`, `api/garmin-oauth.js`), and break the single-click upgrade funnel from `/profile` to `/training`.

### 1.2 Strategic Architecture Decision: Why `detourrunclub.com/training` Wins
- **Unified Athlete Passport (`core.people`):** One login, one PR ledger, one Strava/Garmin OAuth connection across free Saturday bridge runs and paid marathon blocks.
- **Contractual & Visual Entity Firewall (501(c)(3) vs. LLC):**
  - **Detour Run Club Inc. (501(c)(3) Non-Profit):** Routes `/join`, `/races`, `/drops`. Styled with **Detour Orange (`#F4581C`)**, **`$0.00` dues**, and the RRCA waiver (`drc-rrca-v2026.1`).
  - **Detour Athletics LLC (Commercial Practice):** Routes `/training` and `/coaching-intake`. Displays the **Cyan (`#38BDF8`) Commercial Disclosure Banner**, requires the PAR-Q+ & LLC Coaching Agreement (`drc-llc-coaching-v2026.1`), and routes payments exclusively to Detour Athletics LLC's Stripe account.
  - **Future Domain Optionality:** Just as `cms.detourrunclub.com` rewrites `/` $\rightarrow$ `/admin.html` in `detour-web/vercel.json`, `detourathletics.com` can later point to the same Vercel deployment and rewrite `/` $\rightarrow$ `/training.html` with zero code duplication.

### 1.3 Cult Brand Positioning & Copy Architecture (`/cult-brand-and-copywriting` + `/humanizer` + `/creative-ideation`)
Using **Stefan Georgi's RMBC Framework**, **Zach Heffner's 5 Cult Brand Pillars**, **Ashley Rutstein's Strategic Insight Law**, and **Oren John's Spec Totem Rule** (with zero AI-isms, zero em-dash spam, and zero structural emojis):
- **Strategic Insight (The Tension):** Every ambitious NYC runner secretly wants a real physiology-backed plan for their next marathon or half, but they hate two things: rigid PDF spreadsheets that break the week they travel for work, and chatty AI apps that hallucinate paces and nag them to log every gram of oatmeal on Day 1.
- **The Clear Enemy:**
  1. Static 16-week PDF plans that turn a missed Tuesday into a ruined block.
  2. Generic AI wrapper apps that guess training paces with an LLM and clutter watch workout titles with nutrition paragraphs.
- **The Solution Mechanism (Oren John Spec Totems):**
  - `VDOT O2-COST SOLVER` (Daniels & Gilbert deterministic curves, never LLM-guessed paces)
  - `TABLE 15.1 MILEAGE DECAY` (automatic safe volume scaling after sickness or work travel)
  - `CLEAN WATCH STEP CONTRACT` (`Workout.label` stays 100% pure for Garmin/COROS/Apple Watch; informal fueling tips attach only to `PlannedWeek.flags`)
  - `PROGRESSIVE SCOPE GATES` (Day 1 asks only for your race, PR, and weekly miles; fueling, sodium, and biomechanics unlock one question at a time at the exact week your mileage demands them)

### 1.4 End-to-End User Journey & Tier Matrix (Jobs-To-Be-Done)

| Attribute | Tier 0 · Free Club Member | Tier 1 · Engine Self-Serve | Tier 2 · Guided Adaptive + Coach Kip | Tier 3 · 1:1 Head Coach Tanner |
| :--- | :--- | :--- | :--- | :--- |
| **Legal Entity & Price** | **Detour Run Club Inc.** (`501(c)(3)`) · **`$0.00`** | **Detour Athletics LLC** · **`$29/mo`** (`$99/block`) | **Detour Athletics LLC** · **`$69/mo`** | **Detour Athletics LLC** · **`$150/mo`** (Founding) |
| **Core Job-To-Be-Done** | *"Put me in the right Saturday pace pocket and show my training zones."* | *"Build me a real 12–18 week race block around my schedule without coaching fluff."* | *"Push workouts to my watch, adjust my week when work/life hits, and dial in long-run fueling as mileage builds."* | *"Diagnose why I fade after Mile 18 using my 1 Hz watch streams and prescribe targeted workouts with Tanner."* |
| **Entry & Upgrade Path** | `/join` $\rightarrow$ `/profile` $\rightarrow$ `/training?tier=tier0_free` | `/training?tier=tier1_engine` $\rightarrow$ `/coaching-intake?tier=tier1_engine` | `/training?tier=tier2_guided` $\rightarrow$ `/coaching-intake?tier=tier2_guided` | `/training?tier=tier3_1on1` $\rightarrow$ `/coaching-intake?tier=tier3_1on1` |
| **Day-1 Inputs Required** | Name, Email, Borough, Self-Selected Pace Pocket, Optional PR | Goal Race + Date, Recent PR, 4-Wk Avg Miles, 12-Mo Peak Miles, Days/Wk (`3–7`), Long Run Day | Tier 1 Inputs + Garmin/Strava OAuth (`/connect`) + Check-In Channel | Tier 2 Inputs + Injury/PT Triage, Shoe Rotation Quiver, 1:1 Kickoff Call |
| **Active `SetCoachingScope` Flags** | All `False` | All `False` on Day 1 (manual toggle available) | Unlocked at milestones:<br>• Wk 4 (`LR >= 12mi`): `enable_fueling_guidance=True`<br>• Wk 10 (`wtg <= 8` or `>=65°F`): `enable_hydration_weather=True` | Full telemetry:<br>• `enable_fueling_guidance=True`<br>• `enable_hydration_weather=True`<br>• `enable_biomechanics_forensics=True`<br>• `enable_readiness_gates=True` |
| **Primary Deliverables** | • Digital Runner Passport<br>• Assigned Group Pocket (`Front` / `Middle` / `Social`)<br>• 5 VDOT Pace Zones (`E, M, T, I, R`) | • Full 12–18 Wk Plan (`build_club_plan`)<br>• `.ICS` Calendar + CSV Export<br>• Interactive 23-Workout Catalog | • Auto Push-to-Watch (`.FIT`)<br>• Weekly Adaptive Replan (`replan.py`)<br>• 1-Question Milestone Prompts + 48h Carb-Load Rehearsal | • 1 Hz H1/H2 Decoupling & GCT Stiffness Forensics<br>• Limiter-Targeted Workout Swaps (`Canova`, `Hudson`, `Mona`)<br>• Custom Race-Day Course & Gut Blueprint |

### 1.5 Adversarial UX Pre-Mortem & Pragmatism Filter (`/adversarial-ux-test`)
Before writing a single line of HTML, we run the **Adversarial Persona Test** against our current flow and filter findings through the Mandatory Pragmatism Filter:
- **Adversarial Persona:** *"Marcus (39), VP at a Manhattan fintech, 3:28 marathoner chasing a 3:12 Boston Qualifier. Checks his phone on the 4 train between Fulton and Grand Central. Zero patience for forms, popups, or vague marketing."*
- **Pragmatism-Filtered Findings Addressed in This Spec:**
  1. **[RED — Real UX Bug] Cold Legal Wall on `/coaching`:** Clicking `/coaching` drops Marcus straight onto a 7-question medical PAR-Q+ form before he sees what a Detour training block looks like. **Fix:** Point `/coaching` $\rightarrow$ `/training` so runners explore the live interactive prototype first, then click `START TIER [X] INTAKE` which deep-links to `/coaching-intake?tier=...`.
  2. **[RED — Real UX Bug] iOS Safari Auto-Zoom & Token Drift on `/coaching-intake.html`:** `coaching-intake.html` uses `font-size: 14px` on form controls (causing jarring iOS viewport zoom on tap), lacks `data-theme="dark"`, and uses non-canonical `:root` hex codes (`#9da2a8` instead of WCAG AA `#B8BDC3`). **Fix:** Upgrade `coaching-intake.html` to `16px` mobile inputs, `48px` tap targets, canonical `detour-brand-system.css` tokens, and automatic `?tier=` pre-selection.
  3. **[RED — Real UX Bug] Day-1 Feature Overwhelm:** Showing sweat-sodium math, carb-loading grams, and ground-contact-time charts on Week 1 scares off normal runners. **Fix:** The Interactive Timeline Scrubber (`Week 1` $\rightarrow$ `Week 4` $\rightarrow$ `Week 10` $\rightarrow$ `Week 13`) visually locks secondary scope flags in Week 1 and reveals the exact 1-question Coach Kip card that unlocks each flag at the right milestone.
  4. **[GREEN — High-Value Onboarding Feature] Live VDOT + Pocket Calculator Above the Fold:** Let any visitor type or slide a recent race result (e.g., `1:38:00 Half` or `44:00 10K`) and immediately see their 5 VDOT paces (`Easy`, `Marathon`, `Threshold`, `Interval`, `Repetition`) and their assigned DRC Saturday Pace Pocket (`Front`, `Middle`, or `Social`).

---

## 2. Technical Specifications

### 2.1 System Architecture & Data Flow (`/diagram-design` + `/archify`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: DETERMINISTIC PYTHON ENGINE (/Users/tanner/Documents/Projects/detour-engine)│
│                                                                                      │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────┐ │
│  │ engine/plan/club.py     │  │ onboarding_milestones.py │  │ engine/plan/         │ │
│  │ build_club_plan()       │  │ next_onboarding_prompt() │  │ workouts.py          │ │
│  │ • VDOT O2-Cost Paces    │  │ • Wk 1: All flags False  │  │ • 23 Catalog Entries │ │
│  │ • Table 15.1 Decay      │  │ • Wk 4: 1st LR >= 12mi   │  │ • 7 Physio Categories│ │
│  │ • Clean Workout.label   │  │ • Wk 10: Peak / >=65°F   │  │ • 8 Coach Lineages   │ │
│  │ • PlannedWeek.flags     │  │ • Wk 13: Carb Rehearsal  │  │ • Limiter Routing    │ │
│  └───────────┬─────────────┘  └─────────────┬────────────┘  └──────────┬───────────┘ │
│              └──────────────────────────────┼──────────────────────────┘             │
│                                             ▼                                        │
│                     engine/web_prototype.py :: build_prototype_bundle()              │
│                     scripts/export_web_prototype_bundle.py                           │
└─────────────────────────────────────────────┬────────────────────────────────────────┘
                                              │ Exports deterministic JSON artifact
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: WEB APPLICATION (/Users/tanner/Documents/Projects/detour-web)               │
│                                                                                      │
│  public/data/engine-prototype-bundle.json (Canonical Read-Only Fixture)              │
│       │                                                                              │
│       ▼                                                                              │
│  public/training.html (Interactive Training Hub & Tier Simulator · window.DRC)       │
│  ├── Module A: Entity Firewall Banner (501(c)(3) Orange vs. LLC Cyan #38BDF8)        │
│  ├── Module B: Interactive Tier Matrix Switcher (Tier 0 / Tier 1 / Tier 2 / Tier 3)  │
│  ├── Module C: Live VDOT Pace & Saturday Pocket Calculator                           │
│  ├── Module D: 4-Stage Progressive Disclosure Scrubber (Wk 1 → Wk 4 → Wk 10 → Wk 13)│
│  ├── Module E: Interactive SVG Architecture & Seam Diagram (Clickable Nodes)         │
│  └── Module F: 23-Workout Categorized Catalog + Limiter Router                       │
│       │                                                                              │
│       ├──► Tier 0 CTA ──► /join (RRCA Waiver drc-rrca-v2026.1 · $0.00)               │
│       ├──► Watch Sync ──► /connect (Garmin + Strava OAuth)                           │
│       └──► Tier 1/2/3 ──► /coaching-intake?tier=tier1_engine|tier2_guided|tier3_1on1 │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Contract: `public/data/engine-prototype-bundle.json`
Generated deterministically by `detour-engine/engine/web_prototype.py`, this JSON file contains:
1. `schema_version`: `"2026.11.1"`
2. `entity_firewall`: Metadata for `Detour Run Club Inc. (501(c)(3))` (`#F4581C`, `$0.00`, `drc-rrca-v2026.1`) vs. `Detour Athletics LLC` (`#38BDF8`, commercial coaching tiers, `drc-llc-coaching-v2026.1`).
3. `tiers`: Array of the 4 tiers (`tier0_free`, `tier1_engine`, `tier2_guided`, `tier3_1on1`) with exact price, legal entity, required Day-1 inputs, active scope flags, deliverables, and intake URL (`/join` vs. `/coaching-intake?tier=...`).
4. `athlete_profile`: Baseline reference runner (`vdot: 48.0`, Half Marathon PR `1:36:40`, Goal Marathon `3:22:00`, `body_weight_kg: 70.0`, `five_x_per_week`).
5. `pace_zones`: Exact deterministic paces (`sec_per_mile` + formatted `MM:SS/mi`) for `easy`, `marathon`, `threshold`, `interval`, and `repetition`, plus DRC Saturday Pace Pocket boundaries (`Front Pocket 7:45–8:15/mi`, `Middle Pocket 8:45–9:15/mi`, `Social Pocket 9:45–10:30+/mi`).
6. `timeline_stages`: 4 deterministic snapshots produced by `build_club_plan()` and `next_onboarding_prompt()`:
   - `stage_wk1_day1` (**Week 1 · Day 1 Onboarding**): All 4 secondary scope flags `False`. Zero nutrition clutter. Shows clean `Workout.label` and empty `PlannedWeek.flags` for fueling.
   - `stage_wk4_first_12miler` (**Week 4 · First 12-Miler Milestone**): Long run reaches `12.0 mi`. Shows the triggered `MilestonePrompt` (`milestone_key="first_90min_long_run"`) and the resulting state after `SetCoachingScopePayload(enable_fueling_guidance=True)` where `PlannedWeek.flags` gains `fueling_tip: ...` while `Workout.label` remains untouched.
   - `stage_wk10_peak_heat` (**Week 10 · Peak Build & Warm Weather Milestone**): `wtg=7`, `long_run_miles=16.0`, `ambient_temp_f=72.0`. Shows the triggered `salty_sweater_check` prompt and resulting hydration/sodium guidance (`enable_hydration_weather=True`, `sweat_sodium_tier="salty"`).
   - `stage_wk13_dress_rehearsal_tier3` (**Week 13 · Dress Rehearsal + Tier 3 1 Hz Limiter Swap**): `wtg=4`, `long_run_miles=18.0`. Shows the `carb_load_dress_rehearsal` prompt (`8–10g/kg/day`) plus a Tier 3 `BiomechanicsBlock` (`form_stiffness` / `lactate_shuttle`) routing to deterministic workout replacements via `workouts_for_limiter()`.
7. `workout_catalog`: All 23 entries from `WORKOUT_DICTIONARY`, serialized with `key`, `title`, `category`, `category_title`, `source_lineage`, `physiological_target`, `when_to_prescribe`, `limiter_tags`, `default_zone`, and a sample rendered `Workout.label` at `vdot=48.0`.
8. `categories`: Ordered list of the 7 `WORKOUT_CATEGORIES` (`key`, `title`, `description`, `count`).

### 2.3 Frontend Design, Typography & Accessibility Contract (`/impeccable` + `/design-taste-frontend` + `/ui-ux-pro-max` + `/apple-design`)
1. **Canonical Elevation Stack (`detour-brand-system.css`):**
   - Document root: `<html lang="en" data-theme="dark">`
   - Web Canvas (`body`): `--asphalt-950` (`#121214`). Never `#1A1A1C`.
   - Card Surface (`.card`): `--night-asphalt` (`#1A1A1C`) with `1px solid var(--border-subtle, #38383D)`.
   - Elevated Controls / Callouts: `--surface-elevated` (`#242428`).
   - Recessed Inputs: `--surface-deep` (`#141416`).
2. **70 / 20 / 10 Color Law & Dual-Entity Accents:**
   - 70% `#121214` / `#1A1A1C` dark asphalt canvas.
   - 20% `#F2EFE6` Lane Cream primary typography + `#B8BDC3` Surveyor Gray (WCAG AA 7.2:1 contrast on dark backgrounds).
   - 10% High-Signal Accent: **Detour Orange (`#F4581C`)** when inspecting `Tier 0` (501(c)(3) Club) and **Commercial Cyan (`#38BDF8`)** when inspecting `Tier 1–3` (Detour Athletics LLC).
3. **Typography & Tap Target Laws:**
   - Headlines: `Bebas Neue` uppercase (`0.04em` tracking).
   - Body: `Inter` (`15px–16px`, line-height `1.55`).
   - Telemetry / Badges: `JetBrains Mono` (`11px–12.5px` minimum floor; zero `<11px` text).
   - Mobile Inputs: `font-size: 16px` and `min-height: 48px` on all `<input>`, `<select>`, and interactive buttons/tabs (`48x48px` minimum tap target).
4. **Action Economy & Anti-Bloat (`impeccable` + `DESIGN_SYSTEM_RULES.md`):**
   - **Rule of One:** Exactly ONE solid primary CTA button per active stage panel.
   - **Zero Structural Emojis:** All icons use inline SVG paths or `<use href="#token-...">` from the page's SVG `<defs>` sprite.
   - **Spring Motion & Reduced Motion:** Interactive tab/scrubber transitions use `cubic-bezier(0.22, 1, 0.36, 1)` (`220ms`) and respect `@media (prefers-reduced-motion: reduce)`.
   - **Sandboxed Storage Safety:** All state persistence under `window.DRC` uses `safeGetStorage` / `safeSetStorage` `try/catch` wrappers so preview iframes never throw `SecurityError`.

---

## 3. Engineering Ticket Breakdown (Step-by-Step Implementation Tasks)

Every ticket is scoped to 2–5 minutes of focused work, follows strict TDD (`write failing test -> verify failure -> implement -> verify pass`), and names exact file paths and verification commands.

---

### Ticket DRC-101: Build Deterministic Web Prototype Bundle Builder (`detour-engine`)
- **Objective:** Create `engine/web_prototype.py` and `scripts/export_web_prototype_bundle.py` to compile deterministic `detour-engine` outputs (4 tiers, VDOT pace table, 4 progressive timeline stages, and 23 categorized workouts) into a JSON-serializable dictionary.
- **Files:**
  - Create `/Users/tanner/Documents/Projects/detour-engine/tests/test_web_prototype.py`
  - Create `/Users/tanner/Documents/Projects/detour-engine/engine/web_prototype.py`
  - Create `/Users/tanner/Documents/Projects/detour-engine/scripts/export_web_prototype_bundle.py`
- **Verification Command:**
  ```bash
  cd /Users/tanner/Documents/Projects/detour-engine && python3 -m pytest -q tests/test_web_prototype.py && python3 scripts/export_web_prototype_bundle.py
  ```
  Expected output: `2 passed` and `Exported 23 workouts and 4 stages to /Users/tanner/Documents/Projects/detour-web/public/data/engine-prototype-bundle.json`.

---

### Ticket DRC-102: Build Interactive Prototype Hub (`/Users/tanner/Documents/Projects/detour-web/public/training.html`)
- **Objective:** Create `/Users/tanner/Documents/Projects/detour-web/public/training.html` implementing all 6 interactive modules (Dual-Entity Banner, Tier 0–3 Switcher, Live VDOT + Pace Pocket Calculator, 4-Stage Progressive Disclosure Timeline Simulator, Clickable SVG System Architecture Map, and 23-Workout Categorized Catalog + Limiter Filter).
- **Files:**
  - Create `/Users/tanner/Documents/Projects/detour-web/public/training.html`
- **Verification Command:**
  ```bash
  python3 -c '
  from pathlib import Path
  html = Path("/Users/tanner/Documents/Projects/detour-web/public/training.html").read_text()
  assert "data-theme=\"dark\"" in html
  assert "Detour Run Club Inc. (501(c)(3))" in html
  assert "Detour Athletics LLC" in html
  assert "/coaching-intake?tier=" in html
  assert "stage_wk1_day1" in html
  assert "canova_alternations" in html
  print("training.html structural assertions passed")
  '
  ```

---

### Ticket DRC-103: Harden `/coaching-intake.html` & Wire Funnel Navigation (`vercel.json`, `profile.html`, `connect.html`)
- **Objective:** Update `/coaching` redirect in `vercel.json` to `/training`, upgrade `coaching-intake.html` to canonical design tokens + `16px` mobile inputs + automatic `?tier=` query parameter selection, and add `TRAINING ENGINE` navigation pills to `profile.html` and `connect.html`.
- **Files:**
  - Modify `/Users/tanner/Documents/Projects/detour-web/vercel.json`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/coaching-intake.html`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/profile.html`
  - Modify `/Users/tanner/Documents/Projects/detour-web/public/connect.html`
- **Verification Command:**
  ```bash
  python3 -c '
  import json
  from pathlib import Path
  root = Path("/Users/tanner/Documents/Projects/detour-web")
  v = json.loads((root / "vercel.json").read_text())
  redirects = {r["source"]: r["destination"] for r in v.get("redirects", [])}
  assert redirects.get("/coaching") == "/training", redirects
  intake = (root / "public/coaching-intake.html").read_text()
  assert "URLSearchParams" in intake
  assert "tier1_engine" in intake and "tier2_guided" in intake and "tier3_1on1" in intake
  print("Funnel & coaching-intake verification passed")
  '
  ```

---

### Ticket DRC-104: End-to-End Empirical Browser & Test Suite Verification (`/empirical-execution` + `/web-workflow` + `/adversarial-ux-test`)
- **Objective:** Run the full `detour-engine` pytest suite (`359 passed, 1 skipped`) and verify `detour-web/public/training.html` and `coaching-intake.html` in a real headless browser with zero console errors, testing interactive tier switching, timeline scrubbing, and workout catalog filtering.
- **Verification Command:**
  ```bash
  cd /Users/tanner/Documents/Projects/detour-engine && python3 -m pytest -q
  ```
