# Detour Ecosystem: Comprehensive 9-Persona Architecture Audit & Full Business Staffing Blueprint

**Date:** Saturday, October 31, 2026  
**Scope:** Empirical codebase audit (`detour-web`, `detour-marathon-hub`, `detour-engine` v7) + Architectural stress-test of `detour-crm-schema.md` (`SCHEMA_VERSION = 8`) + Full Commercial & Non-Profit Organizational Design  
**Epistemic Tagging:** `[Measured]` = Verified directly in repository source files; `[Inferred]` = Derived from architectural/legal constraints.

---

## Part 1: Comprehensive 9-Persona Audit (Live Codebase + v8 CRM Spec)

Each of the nine personas inspected the live repositories and the proposed v8 schema (`docs/architecture/detour-crm-schema.md`) to surface concrete vulnerabilities, data-loss vectors, and design gaps.

---

### 1. Systems Designer Audit
**Focus:** Canonical identity resolution, state machine integrity, and multi-silo drift.

#### Findings
- **`[Measured]` P0 — Four Disconnected Intake Schemas (Not Three):**
  - Beyond the `detour-web` 31-column Founding Survey (`17Kk8...`), the 10-tab Race CMS (`1MlxS...`), and `output/detour.db`, `detour-engine/store/intake_sheet.py` reads a **fourth** schema: the legacy `z2tc` Google Form (`Intake` tab).
  - In `store/intake_sheet.py` (lines 79–90), `_IGNORED_HEADER_NEEDLES` explicitly ignores `"birthday"`, `"instagram"`, `"safety waiver"`, and `"photo waiver"`, while `_parse_method` (lines 240–250) only recognizes `"daniels"` and `"pfitzinger"`—silently dropping `"hansons"`, `"higdon"`, or `"3-day"` selections to `None`.
- **`[Measured]` P1 — Brittle Naive Substring Injury Classifier:**
  - In `store/intake_sheet.py` (lines 266–272), `_injury_prone_from_notes()` marks an athlete `injury_prone = True` if `len(raw) > 3` and the string does not match the exact substrings `("none", "n/a", "no injury", "healthy", "no issues")`. If a runner writes *"No current injuries, feeling strong!"*, `"no injury"` fails to match `"no current injuries"` and the engine permanently flags them as injury-prone, capping their volume ramp.
- **`[Measured]` P1 — Missing Multi-Key Identity Merge Table in v8 Spec:**
  - In `detour-crm-schema.md`, `core.people` assumes a single known `email` and `strava_athlete_id` at creation time. In reality, an athlete often signs up on `/survey` with `personal@gmail.com`, submits a coaching form with `work@company.com`, and gets scraped from Strava before either email is linked.
- **Remediation:**
  1. Add `core.person_aliases` (`alias_type`: `'email' | 'phone' | 'strava_id' | 'name_slug'`, `alias_value` PK, `person_id` FK) so multiple emails or pre-linked Strava IDs resolve deterministically to one `core.people.id`.
  2. Replace `_injury_prone_from_notes()` substring guessing with an explicit structured radio field (`injury_status: 'healthy' | 'managing_niggle' | 'recovering_from_injury'`) on the intake form.

---

### 2. Backend Developer Audit
**Focus:** Concurrency, serverless ephemerality, idempotency, and database migration safety.

#### Findings
- **`[Measured]` P0 — Ephemeral `/tmp` Backup Illusion on Vercel Serverless:**
  - In `detour-web/api/survey-response.js` (lines 109–159), `appendBackupFiles()` writes `survey-responses.csv` and `survey-responses.json` to `process.cwd()` (read-only in Vercel production) and falls back to `/tmp/survey-responses.csv`. On Vercel Lambda, `/tmp` is wiped on every cold start and is not shared across concurrent container instances. If the Google Sheets API token expires or rate-limits (`429`), the fallback `/tmp` write is permanently lost as soon as the lambda freezes.
- **`[Measured]` P1 — Race Condition on In-Place Sheet Updates:**
  - In `detour-web/api/survey-response.js` (lines 359–390), `payload.is_update` fetches column `F:F`, finds the row index `i + 1` in memory, and issues a `PUT` to `A{rowNum}:AE{rowNum}`. Because Google Sheets has no row-level locking, concurrent submissions or manual row sorting by an officer between the `GET` and `PUT` will overwrite the wrong member's row.
- **`[Measured]` P1 — SQLite Foreign Key Pragma Disabled by Default:**
  - In `detour-engine/store/db.py` (lines 59–65), `sqlite3.connect()` is initialized without `PRAGMA foreign_keys = ON;` and without `PRAGMA journal_mode = WAL;`. SQLite parses `REFERENCES` clauses in `CREATE TABLE` but **does not enforce them** unless `PRAGMA foreign_keys = ON` is executed on every connection open, and default journaling blocks concurrent readers during CLI + MCP writes.
- **Remediation:**
  1. In `store/db.py`, immediately add `self._conn.execute("PRAGMA foreign_keys = ON")` and `self._conn.execute("PRAGMA journal_mode = WAL")` inside `Store.__init__()`.
  2. Replace the `/tmp` fallback in `api/survey-response.js` with a direct transactional `INSERT ... ON CONFLICT (email) DO UPDATE` into managed Postgres (Supabase) or Turso before attempting the Google Sheets mirror.

---

### 3. Frontend Developer Audit
**Focus:** Static build pipelines, cache invalidation, and zero-runtime-dependency race hubs.

#### Findings
- **`[Measured]` P1 — Hardcoded Dual-Maintenance Between `race-cms.json` and `nyc-hub.js`:**
  - While `detour-marathon-hub/scripts/sync_cms_sheet.py` generates `data/race-cms.json` from the 10-tab Google Sheet, `nyc.html`, `nyc-spectator.html`, and `nyc-hub.js` still rely on hardcoded HTML tables, `<span class="badge-wave">`, and static JavaScript `RUNNERS` arrays. Updating the Sheet and running `sync_cms_sheet.py` does not automatically update the DOM or JS arrays without manual edits across 4 files.
- **`[Measured]` P2 — Manual Cache-Busting Query Strings (`?v=YYYYMMDDvN`):**
  - Asset synchronization (`detour-web/scripts/sync_assets.sh`) requires manually bumping `?v=...` query strings in HTML files; missing one reference causes returning mobile Safari users to run stale `nyc-hub.js` against updated HTML DOM IDs.
- **Remediation:**
  1. Build a deterministic static compiler (`scripts/compile_race_hub.py`) that consumes `data/race-cms.json` (exported from `club.race_entries`), injects rendered HTML fragments between `<!-- BEGIN_AUTO_ROSTER -->` / `<!-- END_AUTO_ROSTER -->` markers, writes the `RUNNERS` JS constant, and auto-stamps SHA-256 content hashes (`?v=a1b2c3d4`) on all local CSS/JS links.

---

### 4. UI/UX Team Audit
**Focus:** Member onboarding cognitive load, progressive disclosure, and officer ergonomics.

#### Findings
- **`[Measured]` P1 — 31-Column Monolithic Survey Fatigue:**
  - Asking a brand-new runner showing up for a casual Saturday 5-mile social run to fill out 31 fields (including NYRR volunteer history, singlet chassis cut, emergency contacts, and marathon targets) in one sitting creates drop-off.
- **`[Measured]` P1 — Officer Spreadsheet Fragility:**
  - In the 31-column Founding Cohort Sheet and 10-tab Race CMS Sheet, volunteer officers (Kelly, Cindy) see raw technical columns alongside operational columns, with no data-validation dropdowns protecting foreign keys (`person_id`, `race_slug`).
- **Remediation:**
  1. **Two-Stage Progressive Onboarding UX:**
     - *Stage 1 (60-Second Fast Pass — Required for Run #1):* Name, Email, Phone, Emergency Contact, and Clickwrap Waiver (`core.people` + `club.waiver_acceptances` + `club.emergency_contacts`).
     - *Stage 2 (Member Profile & Kit Locker — Async Link in Welcome Email):* Pace bracket, Strava link, NYRR ID, Bakline singlet sizing, and fueling profile (`club.memberships` + `club.kit_orders`).
  2. Lock structural ID columns in the Officer Google Sheet using Google Sheets `ProtectedRanges` API so officers can edit bibs, waves, and kit handoff status without breaking primary keys.

---

### 5. Privacy, Security & CISO Architect Audit
**Focus:** Credential exposure, PII access controls, filesystem permissions, and NY SHIELD Act compliance.

#### Findings
- **`[Measured]` P0 — Admin Secret Accepted via URL Query Parameter:**
  - In `detour-web/api/survey-response.js` (line 201):
    `const providedKey = authHeader.replace(/^Bearer\s+/i, '') || req.query.key || req.query.secret || '';`
  - Allowing `DRC_ADMIN_SECRET` in `req.query.key` exposes the master secret in plaintext across Vercel edge logs, browser history, proxy logs, and HTTP `Referer` headers—granting full unmasked CSV export of all member names, birthdays, home addresses, and phone numbers.
- **`[Measured]` P0 — Unsanitized Path Traversal & Default Permissions in Garmin Token Store:**
  - In `detour-engine/feeds/garmin/session.py` (lines 29–31 & 82):
    `GARMIN_AUTH_DIR / athlete_id` and `store.mkdir(parents=True, exist_ok=True)` do not validate `athlete_id` against `^[a-z0-9-]+$` and do not set `mode=0o700` on the directory or `0o600` on OAuth token files.
- **`[Measured]` P1 — Unmasked Session Replay Risk on Survey PII:**
  - `detour-telemetry.js` uses `session_recording: { maskAllInputs: false, maskInputOptions: { password: true } }` as a submission recovery failsafe. This means home addresses, birthdays, and emergency contact phone numbers typed into `/survey` are transmitted in cleartext to PostHog session replay storage.
- **Remediation:**
  1. **Immediate Fix (Post-Marathon):** Remove `req.query.key` and `req.query.secret` from `api/survey-response.js`; enforce `Authorization: Bearer <DRC_ADMIN_SECRET>` header exclusively.
  2. Enforce `re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", athlete_id)` and `os.chmod(store, 0o700)` in `feeds/garmin/session.py`.
  3. Add `data-ph-mask-input` (or `class="ph-no-capture"`) specifically to the `address`, `birthday`, and `emergency_phone` input fields on `/survey` so PostHog masks sensitive PII while keeping gear/pace selections visible.

---

### 6. Non-Profit & Tax Counsel / CPA Audit
**Focus:** IRS 501(c)(3) compliance, NY General Obligations Law § 5-326, and clickwrap enforceability.

#### Findings
- **`[Measured]` P0 — Deficient Clickwrap Evidentiary Record:**
  - `detour-web/api/survey-response.js` (lines 299–308) validates `payload.safety_waiver === 'Agreed'` and writes the 6-character word `'Agreed'` into Google Sheets. Under New York contract law, defending a negligence waiver requires proving **which exact text** the user saw and **when/how** they manifested assent (`waiver_text_sha256`, `accepted_at_utc`, `client_ip_hash`, `user_agent`).
- **`[Inferred]` P0 — NY GOL § 5-326 Commercially Paid Coaching Trap:**
  - Under New York General Obligations Law § 5-326, liability waivers for negligence are **void as against public policy** when a user pays a fee to a commercial recreational operator, unless the contract is strictly structured as instructional/coaching services with explicit assumption-of-risk disclosures and backed by commercial Coach Professional Liability & E&O insurance.
  - Furthermore, if a runner pays **Detour Athletics LLC** for 1:1 coaching and gets injured during a **Detour Run Club Inc.** (501c3) free group run, plaintiff counsel will attempt to pierce the entity veil unless the two waivers (`rrca_club_waiver` vs. `llc_coaching_agreement`) are executed as separate, entity-specific legal instruments.
- **Remediation:**
  1. In `club.waiver_acceptances`, require `legal_entity` (`'Detour Run Club Inc.'` vs. `'Detour Athletics LLC'`), `waiver_text_sha256`, `accepted_at_utc`, `ip_hash` (salted SHA-256 of `x-forwarded-for`), and `user_agent`.
  2. Never bundle the 501(c)(3) group run waiver and the LLC paid coaching agreement into a single checkbox.

---

### 7. Run Club COO & Supply-Chain Director Audit
**Focus:** Bakline MOQ economics, inventory reconciliation, NYRR club standing, and race-day aid station execution.

#### Findings
- **`[Measured]` P1 — Unstructured Secondary Gear & No Exchange/Size-Swap Tracking:**
  - In `api/survey-response.js` (lines 288–289), secondary items are concatenated into a single comma-separated string (`secStr`), and there is no distinction between a **non-binding survey ballot** (`"I want a Men's M Singlet"`) and a **paid, committed order**. Ordering Bakline wholesale units off unverified survey ballots risks leaving the club treasury holding unpaid inventory.
- **`[Measured]` P1 — Missing NYRR Club Code Verification Loop:**
  - NYRR requires at least 15 active NYRR members listing the club on their NYRR profile to maintain official club recognition and team scoring eligibility. Currently, `nyrr_affiliation` is self-reported once at signup and never re-verified before NYRR team-points races.
- **Remediation:**
  1. Split `club.kit_orders` into normalized line items (`club.kit_order_items`) with explicit state transitions: `ballot_interest -> payment_received -> wholesale_ordered -> delivered_to_hq -> handed_to_runner`.
  2. Add `nyrr_verified_at` and `nyrr_roster_match` boolean to `club.memberships` so the COO can run a pre-race audit before NYRR club points races (Brooklyn Half, Team Champs, NYC Marathon).

---

### 8. Exercise Physiologist & Sports Data Scientist Audit
**Focus:** Bioenergetic model integrity, longitudinal load monitoring (ACWR), and clinical safety gates.

#### Findings
- **`[Measured]` P1 — Missing Clinical Red-Flag & Scope-of-Practice Triage in `engine.events`:**
  - `detour-engine` models VDOT, grade-adjusted power, and mileage caps mathematically, but `engine.events` currently lacks a clinical severity taxonomy distinguishing a **normal training adaptation** (mild DOMS / fatigue -> `replan` down-week) from a **Clinical Red Flag** (bone stress injury symptoms, sharp localized pain that worsens with running, chest pain, or RED-S / caloric deficiency indicators) that must **halt automated replanning** and route the athlete to a licensed Sports PT / Physician.
- **`[Measured]` P2 — Environmental & Course-Grade Context Missing from `RaceResult` and `weekly_actuals`:**
  - `store/models.py` stores `RaceResult(distance_m, time_s, race_date)` and `weekly_actuals(run_miles)` without temperature/dewpoint (`wbgt_c`) or elevation gain (`elevation_gain_m`). Comparing a 72°F humid Brooklyn Half against a 45°F flat marathon block skews `current_vdot` and `endurance_gap` calculations in `dossier_snapshots`.
- **Remediation:**
  1. Add `clinical_triage_level` (`'green_normal' | 'yellow_modify_load' | 'red_medical_referral_hold'`) to `engine.events`. When `'red_medical_referral_hold'` is triggered, `detour-engine` freezes quality workout generation until cleared.
  2. Add `elevation_gain_m`, `avg_hr_bpm`, `decoupling_pct` (`Pa:Hr`), and `temp_c` to `engine.weekly_actuals` and `RaceResult`.

---

### 9. AI & Agentic Context Architect Audit
**Focus:** MCP server completeness, prompt injection defense, and multi-channel context isolation.

#### Findings
- **`[Measured]` P0 — Headless MCP Server Is Currently an Unimplemented Stub:**
  - In `detour-engine/mcp/server.py` (lines 16–22), `detour_build_plan()` and `detour_replan()` raise `NotImplementedError("MCP server integration is scheduled for Phase 4.")`, and the file does not yet wire the `FastMCP` / `mcp.server` transport over `store/db.py`.
- **`[Inferred]` P1 — Indirect Prompt Injection via Free-Text Survey Notes:**
  - Fields like `free_notes`, `intake_injury_notes`, and WhatsApp messages flow into `narrative_renders` and Coach Kip's context window. Without strict structural delimiters and schema validation at the LLM boundary, untrusted text in a public survey submission could attempt to manipulate Coach Kip's tool calls.
- **Remediation:**
  1. Wire `detour-engine/mcp/server.py` directly to `Store` (`output/detour.db`) with explicit read/write tool schemas and mandatory `athlete_id` scope binding.
  2. Wrap all athlete-supplied free text in `<untrusted_athlete_note>` XML tags before passing to LLM narrative renderers, and restrict LLM outputs strictly to Pydantic-validated `EventProposal` schemas (never raw SQL).

---

## Part 2: Full Business Organizational & Hiring Blueprint

As Detour scales across **Detour Run Club Inc.** (501(c)(3) community club) and **Detour Athletics LLC** (1:1 coaching, multi-discipline training across Road/Track/Trail/Ultra, adaptive `detour-engine` SaaS/MCP, and technical apparel), you should **not** hire bloated full-time overhead early.

Instead, structure the organization across **Four Staffing Tiers** tied to concrete revenue and membership milestones:

```
                   ┌────────────────────────────────────────────────────┐
                   │        FOUNDER, HEAD COACH & CHIEF ARCHITECT       │
                   │                    Tanner Chung                    │
                   └─────────────────────────┬──────────────────────────┘
                                             │
     ┌───────────────────────────┬───────────┴───────────────┬───────────────────────────┐
     ▼                           ▼                           ▼                           ▼
[ TIER 1: FRACTIONAL ]    [ TIER 2: CLUB BOARD ]     [ TIER 3: PART-TIME ]       [ TIER 4: FULL-TIME ]
(Retainer / Milestone)    (501c3 Volunteer Officers) (Revenue-Share / Seasonal)  (Scale Stage >150k ARR)
• Sports Liability Counsel• VP & Medical: Kelly H.   • Specialist Sub-Coaches    • #1 GM Community & Brand
• 501c3 + LLC Tax CPA     • Events & NYRR: Cindy K.    (Trail/Ultra, Track, BQ)  • #2 Founding Full-Stack
• Partner Sports PT Clinic• Pace Group Captains      • Race-Day Documentary        & Wearables Engineer
• Sports Dietitian (CSSD)   (8:00, 9:00, 10:00+ mi)    Photographer / Video      • #3 Director of Coaching
• Apparel Tech-Pack Spec                             • Drop Fulfillment Assist     & Athlete Success
```

---

### Tier 1: External Consultants & Clinical Partners (Engage Now / Per-Milestone)
*Zero fixed payroll; protects your legal entity firewall, clinical scope of practice, and tax efficiency.*

1. **Sports & Non-Profit Corporate Attorney (Milestone Fee: 1,500–2,500 USD once)**
   - **Role:** Drafts the 1-page **Revocable Brand & Tech License Agreement** between Tanner/Detour Athletics LLC and Detour Run Club Inc. (501c3); audits the NY GOL § 5-326 language separating the free group-run clickwrap waiver from the paid LLC coaching contract; reviews RRCA vs. private Coach E&O insurance exclusions.
2. **Dual-Entity CPA & Tax Strategist (Annual Retainer — Paired with Pangolin.ai CPA)**
   - **Role:** Oversees the 501(c)(3) Form 990-N / NY ST-119.1 Sales Tax Exemption, documents the 0% Founder Working Capital Promissory Note, ensures Bakline gear rebates remain 100% exempt from UBIT, and optimizes IRC § 162 deductions (gear, race travel, software) on Detour Athletics LLC.
3. **Partner Sports Physical Therapy Clinic — DPT (Zero-Dollar Mutual Referral Partnership)**
   - **Role:** Partner with a premier Brooklyn/Manhattan running PT clinic (e.g., Custom Performance, Finish Line PT, or a Park Slope running DPT).
   - **Why It's Essential:** RRCA coaching certification strictly prohibits diagnosing or treating musculoskeletal injuries. When `detour-engine` flags a `red_medical_referral_hold`, you offer the athlete priority 48-hour triage with your Partner DPT. In return, the DPT feeds structured return-to-run volume/pace constraints back into `detour-engine` and refers their discharged patients to Detour for post-PT marathon coaching.
4. **Registered Sports Dietitian — CSSD / RDN (Quarterly Clinical Audit / Per-Consult Referral)**
   - **Role:** Reviews and co-signs the deterministic fueling equations in `engine/plan/nutrition.py` (60–90g/hr carb ramps, sodium replacement, GI sensitivity tiers) and takes 1:1 clinical referrals for athletes with complex GI disorders or suspected RED-S (Relative Energy Deficiency in Sport).
5. **Technical Apparel Pattern Maker & Sourcing Specialist (Per-Collection Project Fee)**
   - **Role:** When Detour graduates beyond Bakline stock wholesale blanks into custom cut-and-sew silhouettes (`detour-kit`), translates your vector CAD tokens into factory-ready tech packs, graded POM (Point of Measure) tables, and lab-dip color standards.

---

### Tier 2: 501(c)(3) Volunteer Board Officers & Run Leaders (0 USD Payroll — Perk & Gear Comp)
*Protects Tanner from burning out on Saturday morning logistics and satisfies IRS/RRCA governance.*

1. **VP & Medical / Aid Station Director (Kelly Hession):** Co-signs RRCA compliance, anchors Mile 18.2 / long-run hydration stations, and holds `vp_medical` access to `club.emergency_contacts`.
2. **Secretary / Community & NYRR Coordinator (Cindy Kim):** Manages NYRR volunteer quotas, official club roster verification (`nyrr_club_affiliation`), and post-race celebration venues.
3. **Treasurer (Core Founding Crew Member):** Reconciles the dedicated 501(c)(3) bank account, Bakline rebate deposits, and founder loan repayments (4-hour/quarter commitment).
4. **Pace Group Captains (4–6 Rotating Runners across 8:00, 9:00, 10:00, and 11:00+/mi):**
   - **Why It's Essential:** If the founder has to lead every pace group on Saturday morning, the club caps out at one pace pocket and interferes with your own marathon training block. Compensate Pace Captains with comped seasonal Bakline kits (`payment_status = 'comped'`).

---

### Tier 3: Part-Time Contractors & Revenue-Share Specialists (Variable Cost — Scales with Revenue)
*Trigger when 1:1 coaching passes 12–15 active athletes (~3,000 USD/mo) or seasonal gear drops pass 75 units.*

1. **Associate Specialty Running Coaches (1099 Revenue-Share Contractors: 65% Coach / 35% Detour Platform Split)**
   - **Who to Hire:**
     - **Trail & Ultra Specialist Coach (`Detour Trail / Ultra`):** Coaches 50K–100M athletes using `detour-engine`'s Minetti grade-energetics kernel.
     - **Women's Performance & Postpartum / First-Timer Coach:** Expands coaching roster diversity and psychological safety for first-time marathoners.
     - **Track / Sub-3:00 BQ Specialist Coach (`Detour Track Club`):** Leads Tuesday night track intervals at Red Hook / McCarren / Prospect Park.
   - **Economics:** At 225 USD/mo per athlete, Detour Athletics LLC retains ~78 USD/mo per athlete in pure platform/IP margin while `detour-engine` + Coach Kip automates 80% of the plan generation and Strava/Garmin monitoring.
2. **Freelance Run-Culture Documentary Photographer / Reels Editor (250–400 USD per Major Race / Drop Shoot)**
   - **Why It's Essential:** High-taste visual storytelling (`detour-brand`) drives top-of-funnel organic growth. Having a dedicated shooter at Mile 6.7, Mile 18.2, and track nights frees you to be fully present as Coach and Founder.
3. **Seasonal Kit Fulfillment & Expo Assistant (25–30 USD/hr for ~10 hours, 3x/year)**
   - **Role:** Receives bulk Bakline shipments, tags/bags orders against `club.kit_orders`, and staffs pre-race shakeout gear pickup tables.

---

### Tier 4: Full-Time Employees (Scale Stage: >150,000–250,000 USD Annual Run-Rate)
*Only hire full-time when commercial SaaS, coaching roster (50+ athletes), and B2B brand activations justify dedicated headcount.*

1. **Full-Time Hire #1: Head of Community, Events & Brand Partnerships (GM of Run Club & Experiential)**
   - **Why First:** Your highest-leverage moat is the physiological engine (`detour-engine`), product vision, and AI architecture. A full-time Community & Partnerships GM owns weekly run operations across all boroughs, negotiates 5,000–25,000 USD brand activations (shoe demo days, fuel sponsors, pop-up hubs), and turns free community runs into a predictable conversion funnel for paid coaching and SaaS.
2. **Full-Time Hire #2: Founding Full-Stack & Wearable Systems Engineer**
   - **Why Second:** Owns the production Next.js/mobile athlete portal (`Detour UI`), official Garmin/Coros/Apple Watch/Strava real-time webhook ingestion, database infrastructure, and multi-tenant coach dashboard—freeing you to focus on R&D and enterprise strategy.
3. **Full-Time Hire #3: Director of Coaching & Athlete Success (Head Coach)**
   - **Why Third:** Recruits, trains, and QA-audits the roster of part-time Associate Coaches, runs the 15-minute intake strategy screens, and owns athlete retention and race-day VIP hospitality.

---

### Tier 5: New Digital Specialist Personas Added to the Hermes Board for Detour

To give you these capabilities **today at zero payroll cost**, we should instantiate four additional digital lenses whenever we work on Detour:

1. **🩺 Sports PT & Return-to-Run Triage Specialist:** Audits `engine.events` injury flags, enforces bone-stress vs. soft-tissue red-flag gates, and generates structured PT referral briefs.
2. **🧪 Certified Sports Dietitian (CSSD) & Thermoregulation Specialist:** Governs `engine/plan/nutrition.py`, calculates race-week carb-load schedules (`8–10g/kg`), and adjusts marathon fluid/sodium targets based on race-day temperature/dewpoint.
3. **🤝 Brand Partnerships & Experiential Creative Director:** Designs high-taste brand colabs (Bakline, Maurten, Brooks, local Brooklyn cafes) that fund club perks without diluting DRC's underground aesthetic.
4. **📊 Growth, Funnel & Retention Analyst:** Tracks conversion from Saturday group runs -> `/survey` -> `/engine` VDOT calculator -> 1:1 paid coaching (`coaching.subscriptions`).
