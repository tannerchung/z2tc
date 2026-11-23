# Detour Master Technology, CMS/CRM & Account Provisioning Specification

**Status:** Canonical Architecture Blueprint (`v2026.11`)  
**Owner:** Tanner Chung (Founder, President & Head Coach)  
**Legal Entities Covered:**  
1. **Commercial & IP Track:** Tanner Chung (Sole Proprietor) -> **Detour Athletics LLC** (Owns all software, domains, trademarks, database spine, and 1:1 coaching)  
2. **Community Non-Profit Track:** **Detour Run Club Inc.** (501(c)(3) under RRCA Group Exemption #2702 — Licenses public community web surfaces royalty-free from Licensor)

---

## 1. Executive Summary & Architectural Philosophy

Detour operates as a high-taste NYC endurance community (`Detour Run Club Inc.`) paired with a deterministic physiological training engine and commercial coaching lab (`Detour Athletics LLC` / `detour-engine`).

To prevent **Split-State data silos** (where member contacts, race bibs, waivers, and training plans drift out of sync across separate cloud databases) and eliminate **intimidating 13-tab spreadsheets for non-technical club officers**, Detour uses a **Unified State + Managed Cloud Free-Tier Architecture**:

1. **Single Canonical Database Spine (`Supabase Cloud Postgres` <-> Local `detour.db` SQLite):** Every person, waiver, Bakline singlet order, marathon bib, cheer station, workout card, and Garmin/Strava activity lives in one relational database partitioned across four strict schemas (`core`, `club`, `engine`, `coaching`) enforced by Postgres **Row-Level Security (RLS)**.
2. **Guided Officer Portal & Web CMS (`Payload CMS 3.0` Embedded in `detour-web`):** Runs serverless inside our existing Next.js app on Vercel for **$0/month**, reading and writing directly to our Supabase Postgres database. Replaces the raw 13-tab Google Sheet with clean, role-restricted forms, dropdowns, and checklists for club officers (Kelly, Cindy, Treasurer).
3. **Subway-Proof Static Edge Delivery:** Whenever an officer updates a runner's bib, wave, or cheer station in `/admin`, a build hook runs `compile_cms_semantic.py` (enforcing our 10-point Anti-Drift & PII Sanitization Gate) and bakes static `data/race-cms.json` and `public/data/drc-cms-views.js` files. Public race pages (`/nyc`, `/nyc-spectator`) never query a live database from the browser on race morning.
4. **Best-in-Class $0/Month Ecosystem Extensions:**
   - **Authentication:** **Supabase Auth** (50,000 MAU free — Magic Links, Google/Apple, Strava OAuth).
   - **Email (Transactional + Marketing):** **Resend** (API + Broadcasts + React Email) + **Cloudflare Email Routing**.
   - **Sponsor & Coaching Pipeline CRM:** **Attio Free** (3 seats, auto-syncs Gmail/Calendar threads for brand sponsors & coaching leads).
   - **Scheduling:** **Cal.com Free** (15-minute coaching strategy screens).
   - **Video & Photo Vault:** **Cloudflare R2** (10GB free, **$0.00 egress bandwidth** for PT/strength exercise videos, race photography, and `.FIT` files).
   - **Analytics & Lifecycle Triggers:** **PostHog Cloud Free** (1M events/mo free, session replay with PII masking, behavioral webhooks).
   - **Banking & Payments:** **Mercury** (separate $0/mo checking accounts for 501c3 and LLC) + **Stripe** (coaching billing).

---

## 2. Account Creation & Root Email Ownership Playbook (Zero Google Workspace Needed)

### 2.1 Why You Should NOT Use `detourrunclub@gmail.com` (or Google OAuth) as the Root Tech Owner

1. **Future Officer Access Risk:** `detourrunclub@gmail.com` is the shared operational inbox for the 501(c)(3) club. If you ever grant a future Club Secretary, VP, or Treasurer access to `detourrunclub@gmail.com`, and that Gmail account is the "Sign in with Google" owner of Cloudflare, Supabase, Vercel, or Stripe, that volunteer officer instantly gains root control over your domains, commercial LLC database, and private coaching revenue.
2. **Corporate Veil & IP Ownership:** Under the signed **Revocable IP, Brand & Technology License Agreement**, **you (Tanner Chung / Detour Athletics LLC)** own 100% of the domains, codebase, and technology stack. Registering core infrastructure under a generic `detourrunclub@gmail.com` Google OAuth token blurs the line between 501(c)(3) property and LLC property.
3. **You Already Have Custom `@detourrunclub.com` Emails for $0/Month via Cloudflare:** You do **not** need paid Google Workspace ($7.20/mo) or a separate LLC domain today to create custom-domain accounts. Because **Cloudflare Email Routing** is active on `detourrunclub.com`, you can route specific `@detourrunclub.com` aliases to two separate Gmail destinations right now for $0.

### 2.2 The Two-Destination Cloudflare Email Routing Split (Set Up Before Creating Accounts)

In **Cloudflare Dashboard -> `detourrunclub.com` -> Email -> Email Routing**, configure your aliases across **two separate destination inboxes**:

```
                     [ CLOUDFLARE EMAIL ROUTING (detourrunclub.com) ]
                                            │
            ┌───────────────────────────────┴───────────────────────────────┐
            ▼                                                               ▼
┌───────────────────────────────────────┐       ┌───────────────────────────────────────┐
│ DESTINATION 1: PRIVATE FOUNDER INBOX  │       │ DESTINATION 2: 501(c)(3) CLUB INBOX   │
│      (tanner.chung@gmail.com)         │       │      (detourrunclub@gmail.com)        │
│  Strictly Private — Never Shared      │       │  Club Operations & Officer Accessible │
├───────────────────────────────────────┤       ├───────────────────────────────────────┤
│ • tanner@detourrunclub.com            │       │ • hello@detourrunclub.com             │
│ • infra@detourrunclub.com             │       │ • ops@detourrunclub.com               │
│ • coaching@detourrunclub.com          │       │ • treasury@detourrunclub.com          │
│ • security@detourrunclub.com          │       │ • gear@detourrunclub.com              │
│ • privacy@detourrunclub.com           │       │ • kelly@ / cindy@ (or direct fwd)     │
└───────────────────────────────────────┘       └───────────────────────────────────────┘
```

- **How to Sign Up for Accounts:** Always choose **"Continue with Email + Password"** (saved in your 1Password vault with 2FA/Passkey enabled) rather than clicking *"Sign in with Google"*.
- **Seamless Future LLC Domain Migration:** Because accounts are registered with `infra@detourrunclub.com` or `tanner@detourrunclub.com` via email/password (not hard-locked to a Gmail OAuth ID), the day you buy `detourathletic.com` (or `detourathletics.run`), you can swap the account email to `tanner@detourathletic.com` in 30 seconds.

### 2.3 Master Account Provisioning Matrix (Step-by-Step Checklist)

Use this exact table as you create each account today:

| # | Service / Tool | Role in Stack | Exact Owner Email to Register With | Auth Method (In 1Password) | Legal Entity Owner | Free Tier Allowance |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Cloudflare** (DNS, Email Routing, **R2 Storage**) | Domains, zero-cost email routing, R2 video/photo CDN (`$0` egress) | **`infra@detourrunclub.com`** *(routed to `tanner.chung@gmail`)* | Email + Password + 2FA | Tanner / Detour Athletics LLC | Free DNS/Email + 10GB R2 storage (`$0` egress) |
| **2** | **Supabase** (Postgres DB, Auth, Storage, Vault) | Single canonical database (`core`, `club`, `engine`, `coaching`) + Member Auth + MCP | **`infra@detourrunclub.com`** | Email + Password (or Personal GitHub) | Tanner / Detour Athletics LLC | 500MB Postgres DB, 50,000 MAU Auth, 1GB Storage |
| **3** | **Vercel** | Hosting `detour-web`, Embedded **Payload CMS 3.0 (`/admin`)**, `@vercel/og` graphics | **`infra@detourrunclub.com`** | Personal GitHub + Email (`infra@`) | Tanner / Detour Athletics LLC | 100GB bandwidth, serverless functions, preview deploys |
| **4** | **Resend** | Transactional emails (waivers, magic links, receipts) + Club Broadcasts + Gmail SMTP | **`infra@detourrunclub.com`** | Email + Password + 2FA | Tanner / Detour Athletics LLC | 3,000 emails/mo (100/day), 1,000 Broadcast contacts |
| **5** | **PostHog Cloud (US)** | Product & funnel analytics (`window.drcTrack`), session replay, lifecycle webhooks | **`infra@detourrunclub.com`** | Email + Password | Tanner / Detour Athletics LLC | 1,000,000 events/mo, 5,000 session replays/mo |
| **6** | **Attio** | Pipeline CRM for Brand Partnerships (Bakline, Maurten) & 1:1 Coaching Leads | **`tanner@detourrunclub.com`** *(workspace domain: `detourrunclub.com`)* | Email Magic Link / Password *(Sync Gmail inside Settings)* | Tanner / Detour Athletics LLC | Free Forever for up to 3 seats (`Tanner`, `Kelly`, `Cindy`) |
| **7** | **Cal.com** | 15-Minute Coaching Strategy Screen booking widget (`/coaching`) | **`tanner@detourrunclub.com`** *(connect Google Calendar inside Settings)* | Email + Password | Tanner / Detour Athletics LLC | Free Forever for individuals (unlimited event types) |
| **8** | **Stripe (Account A — LLC)** | Paid 1:1 Coaching Subscriptions (`$175–$250/mo`) & future Engine SaaS | **`coaching@detourrunclub.com`** *(swap to `@detourathletic.com` later)* | Email + Password + Passkey | **Detour Athletics LLC** *(Links to LLC Mercury Bank)* | `$0/mo` fixed (2.9% + 30c per transaction) |
| **9** | **Stripe (Account B — 501c3)** *(Optional)* | Secondary Bakline float kit claims & non-profit event ticketing | **`treasury@detourrunclub.com`** | Email + Password + Passkey | **Detour Run Club Inc. (501c3)** *(Links to 501c3 Mercury Bank)* | `$0/mo` fixed (Non-profit discounted processing rate available) |
| **10** | **Mercury Bank (2 Separate Logins)** | Zero-fee business checking, virtual cards, officer approval rules | **LLC:** `tanner@detourrunclub.com`<br>**501c3:** `treasury@detourrunclub.com` | Email + Password + Passkey | Separate EINs (`Detour Athletics LLC` vs. `Detour Run Club Inc.`) | `$0/mo`, `$0` minimum balance, free wires/ACH |
| **11** | **RRCA / NYRR / Bakline** | 501(c)(3) group exemption, club roster charter, singlet wholesale portals | **`ops@detourrunclub.com`** (or `tanner@detourrunclub.com`) | Email + Password | **Detour Run Club Inc. (501c3)** | N/A (Club operational portals) |

---

## 3. Complete System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        USER & OFFICER INTERACTION SURFACES                              │
├────────────────────┬────────────────────┬────────────────────┬──────────────────────────┤
│ 1. PUBLIC WEB      │ 2. MEMBER PORTAL   │ 3. RUNNER APP      │ 4. OFFICER / COACH ADMIN │
│ detourrunclub.com  │ /account           │ detourathletic.com │ detourrunclub.com/admin  │
│ • /nyc & /chicago  │ • Signed Waivers   │ • Season Calendar  │ • Payload CMS 3.0 UI     │
│   (Static Edge)    │ • Kit Order Status │ • Workout Cards    │ • Kelly/Cindy: `club.*`  │
│ • /survey & /kit   │ • NYRR Affiliation │ • Carb/Sodium Plan │ • Tanner: `coaching.*`   │
│ • /engine VDOT Calc│ • Squad Directory  │ • R2 PT Videos     │   + Fleet Readiness      │
│ • Social OG Cards  │ • Race Bib & Wave  │ • .FIT & .ICS Sync │ • Attio: Sponsor/Deals   │
└─────────┬──────────┴─────────┬──────────┴─────────┬──────────┴────────────┬─────────────┘
          │                    │                    │                       │
          └────────────────────┴──────────┬─────────┴───────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                UNIFIED STATE SPINE: SUPABASE CLOUD POSTGRES + AUTH                      │
│                  (Mirrored Locally to `detour-engine/output/detour.db`)                 │
├────────────────────┬────────────────────┬────────────────────┬──────────────────────────┤
│   `core.*` Schema  │   `club.*` Schema  │  `engine.*` Schema │   `coaching.*` Schema    │
│ • people (PK slug) │ • memberships      │ • seasons          │ • intakes (PAR-Q+)       │
│ • person_aliases   │ • waiver_accepts   │ • survey_baselines │ • subscriptions (Stripe) │
│ • auth.users link  │ • emergency_cntcts │ • plan_artifacts   │ • oauth_connections      │
│   (Magic Link,     │ • kit_drops/orders │ • events (typed)   │   (Garmin/Strava Vault)  │
│    Google, Strava) │ • races & entries  │ • training_blocks  │ • equipment_shoes        │
│                    │ • cheer_stations   │ • weekly_actuals   │ • exercises_library (R2) │
│                    │ • governance_docs  │ • dossier_snapshots│ • session_notes          │
└─────────┬──────────┴─────────┬──────────┴─────────┬──────────┴────────────┬─────────────┘
          │                    │                    │                       │
          ▼                    ▼                    ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│             DETERMINISTIC ENGINE, AI BOUNDARY & EXTERNAL INTEGRATIONS                   │
├─────────────────────────────┬────────────────────────────┬──────────────────────────────┤
│ • `detour-engine` (Python)  │ • Coach Kip / Hermes Agent │ • Resend (Receipts/Broadcast)│
│   Daniels VDOT, Minetti     │   `llm/boundary.py` parses │ • PostHog (Funnel Webhooks)  │
│   Power, Nutrition, Replan  │   Strava/WhatsApp -> Events│ • Cloudflare R2 (Video/Photo)│
│ • `detour-mcp-server`       │ • Strava & Garmin Webhooks │ • Cal.com + Stripe Webhooks  │
└─────────────────────────────┴────────────────────────────┴──────────────────────────────┘
```

---

## 4. How Every Entity Type & Business Function Operates

### 4.1 Replacing the 13-Tab Google Sheet: Payload CMS 3.0 Officer Portal (`/admin`)
Payload CMS 3.0 installs directly inside `detour-web` (`/app/(payload)/admin`) on Vercel and connects to Supabase Postgres via `@payloadcms/db-postgres`.
- **Zero Technical Intimidation:** Instead of 35 columns and raw JSON strings (`supplies_json`), officers see clean forms, dropdown selects (`Wave 1..5`, `Corral A..F`), toggle switches, and visual progress bars.
- **Role-Based Access Control (RBAC) — Strict Entity Firewall:**
  - **`club_officer` (Kelly, Cindy):** Can only view and edit **501(c)(3) Community Operations** (`Members`, `Waivers`, `Emergency Contacts`, `Races & Cheer Stations`, `Kit Drops & Orders`, `Governance Filings`).
  - **`club_treasurer` (Gaurav):** Can only view and edit **501(c)(3) Non-Profit Treasury Collections** (`club.treasury_ledger`, `club.kit_drops`, `club.kit_orders`, `club.founder_loan_tranches`, `club.governance_documents`) and the **DRC Non-Profit Treasury Dashboard (`/treasury-projections`)**. Has **zero visibility** into Detour Athletics LLC coaching revenue, Stripe subscriptions, LLC expenses, or personal tax data (`coaching.*` is blocked at the Postgres RLS layer).
  - **`coach_admin` (Tanner Only):** Exclusive access to **Detour Athletics LLC Commercial & Financial Collections** (`coaching.subscriptions`, `coaching.llc_ledger`, `coaching.intakes`, `engine.*`) and the private **Detour Athletics LLC P&L & Tax Shield Dashboard (`/da-projections`)**.

### 4.2 Legal Waivers, Media Releases & Corporate Paperwork
1. **Dual-Instrument NY GOL § 5-326 Clickwrap Engine:**
   - **Club Waiver (`drc-rrca-v2026.1`) & Media Release (`photo-release-v2026.1`):** Signed on `detourrunclub.com/survey` for free ($0) community activities.
   - **LLC Coaching Agreement & PAR-Q+ (`llc-coaching-parq-v2026.1`):** Signed on `detourathletic.com/coaching/onboarding` as an independent instructional/consulting contract before Stripe checkout.
   - **Cryptographic Proof:** Every submission writes an append-only row to `club.waiver_acceptances` recording `waiver_version`, `waiver_text_sha256`, `accepted_at_utc`, `ip_hash`, and `user_agent`, and emails a PDF/HTML copy via Resend.
2. **Board Governance Vault (`club.governance_documents`):**
   - Stores the signed NY Certificate of Incorporation, IRS 501(c)(3) GEN #2702 determination letter, RRCA insurance policies, signed **Revocable IP & Tech License Agreement**, signed **0% Founder Promissory Note**, and IRS Form 990-N e-Postcard receipts in a private Supabase Storage bucket accessible to Board Officers.

### 4.3 Command Center & Spectator Portals (`/nyc`, `/nyc-spectator`, `/chicago`)
- **Build-Time Static Compilation:** When an officer updates a runner's bib or cheer station supply list in Payload `/admin` and clicks **"Publish Race Hub"**, Payload triggers `compile_cms_semantic.py`.
- **10-Point Anti-Drift & PII Sanitization Gate:** Automatically strips all private emails, phone numbers, home addresses, birthdays, and emergency contacts before emitting static `data/race-cms.json` and `public/data/drc-cms-views.js`.
- **Subway-Proof Performance:** Race-day pages load in <50ms with zero runtime database calls, surviving 3G subway tunnels and 200 simultaneous spectators at Mile 6.7.

### 4.4 Member Portal (`detourrunclub.com/account`) & Runner Dashboard (`detourathletic.com/app`)
Authenticated via **Supabase Auth** (Magic Link via Resend, Google/Apple Sign-In, or 1-Click Strava OAuth):
1. **DRC Member Portal (`/account` — Free for All Club Members):**
   - View & update personal profile, emergency contact, fueling preferences, and NYRR Member ID.
   - View signed waiver status, Bakline kit order sizes/pickup status, and active race bib/corral/cheer assignments.
   - Opt-in Squad Directory & pace-group finder.
2. **Coached Runner Dashboard (`/app` — Detour Athletics LLC Clients):**
   - **Interactive Season Calendar & Daily Workout Cards:** Displays prescribed mileage, continuous Daniels VDOT pace zones, and Minetti grade-adjusted power targets.
   - **Nutrition & Carb-Load Module (`engine/plan/nutrition.py`):** 72-hour pre-race carb-load calculator (`8–10g/kg`), workout hydrogel schedules (`60–90g/hr`), and WBGT weather-adjusted sodium/fluid targets.
   - **Video & Exercise Library (Cloudflare R2):** Embedded high-frame-rate video demos for prescribed strength, mobility, running drills, and PT prehab (`Single-Leg Hop Test`, `Eccentric Calf Drops`) streamed from Cloudflare R2 at $0 bandwidth cost.
   - **1-Click Wearable & Calendar Sync:** Direct download/push of binary Garmin `.FIT` structured workouts and `.ICS` calendar feeds.
   - **26.2 Readiness Equivalence Telemetry:** Visual charts showing 36-hour cumulative volume, aerobic decoupling (`Pa:Hr` cardiac drift < 5.0%), and shoe mileage bars (`coaching.equipment_shoes`).

### 4.5 Coaching & Telemetry Dashboard (`/admin/coaching`)
- **Fleet Readiness Matrix:** Displays all coached athletes in a single high-density view with traffic-light indicators for **Weekly Compliance %**, **ACWR (`0.8–1.3`)**, **Cardiac Drift (`Pa:Hr`)**, **Clinical PT Triage Status** (`green_adaptable` | `yellow_load_modify` | `red_medical_referral_hold`), and **Shoe Retirement Alerts (>325 mi)**.
- **1-Click AI Event Approval Queue:** Review structured `EventProposal` rows extracted by Coach Kip from athlete WhatsApp check-ins and Strava notes; clicking **[Approve & Replan]** runs `replan.py`, generates a new immutable `PlanArtifact`, and notifies the runner.

### 4.6 Automated Social Graphics, Email Marketing & Sponsor Pipelines
1. **Social Post & Pace Card Compiler (`@vercel/og` / Satori + `resvg`):**
   - One-click generation inside `/admin` turns route data and race rosters into `1080x1350` Instagram carousels (Friday Route Dispatches, Wave Start Cards) and `1170x2532` iPhone Lock-Screen Pace Cards using embedded `Bebas Neue` and `JetBrains Mono` fonts.
2. **3-Tier Email Engine (Resend + PostHog + Supabase):**
   - **Tier 1 (Transactional):** Instant survey/waiver receipts, kit confirmations, and magic links via Resend API.
   - **Tier 2 (Broadcasts & Announcements):** Segmented newsletters sent via Resend Broadcasts directly from Supabase SQL views (`All Active Members`, `NYC 2026 Squad`, `Unverified NYRR Roster`).
   - **Tier 3 (Behavioral Drip Sequences):** PostHog tracks high-intent actions (`engine_vdot_calculated`, `coaching_page_viewed`) and fires webhooks to send automated coaching follow-ups.
3. **Sponsor & Coaching Pipeline CRM (Attio Free + Cal.com Free):**
   - **Attio** connects to `tanner@detourrunclub.com` Gmail & Calendar to automatically log email threads with brand partners (Bakline, Maurten, Brooks, local cafes) and prospective coaching clients across visual Kanban stages.
   - **Cal.com** embeds on `/coaching` for booking 15-minute athlete strategy screens.

---

## 5. How the Coaching Engine + AI + Wearable Telemetry Loop Works

Detour enforces **The Inviolable Deterministic Seam**: AI never calculates paces or mileage; AI translates messy human and environmental context into typed events that parameterize the deterministic Python kernel (`detour-engine`).

1. **Stage 1 — Structured Ingestion (`feeds/strava/`, Garmin API, `club.race_entries`):**
   - Automatically pulls completed runs (distance, pace, HR stream, elevation, `Pa:Hr` drift, shoe ID), official race splits, and weather (`WBGT`) into `engine.training_blocks` and `engine.weekly_actuals`.
2. **Stage 2 — Deterministic Dossier & Anomaly Detection (`engine/analyze.py`):**
   - Computes `CapacityProfile` and `DossierSnapshot` (`recommended_vdot`, Table 15.1 detraining decay, `w_now`, `p_history`, `endurance_gap`, `ACWR`) and flags `EasyPaceDrift`, `LongRunIncomplete`, or `MissedQuality`.
3. **Stage 3 — AI Boundary Distillation (`llm/boundary.py` -> `engine.events`):**
   - Coach Kip (Hermes / Gemini) reads unstructured Strava captions and WhatsApp DMs (*"Ran the half in 1:38 with a head cold"* or *"Right calf tightened at Mile 12"*) and writes strictly validated Pydantic `EventProposal` rows (`EffortQuality`, `RaceEstimate`, `Injury`, `Unavailable`, `Difficulty`) with `status = 'proposed'`.
4. **Stage 4 — Coach Approval & Deterministic Replan (`engine/plan/replan.py`):**
   - Once approved in `/admin/coaching`, `fold_events_to_inputs()` folds the events into `AthleteInputs`, runs `build_plan()` + `nutrition.py`, saves an immutable `PlanArtifact` (`inputs_hash`), updates `.FIT`/`.ICS` feeds, and dispatches Coach Kip's empathetic explanation to the runner.

---

## 6. Legal & Tax Cost-Allocation Rules (When Free Tiers Scale to Paid)

When growth eventually pushes any tool into a paid tier (e.g., Vercel Pro `$20/mo`, Supabase Pro `$25/mo`, Resend Pro `$20/mo`):

1. **Detour Athletics LLC Pays 100% of Shared Tech Infrastructure:**
   - Charge all cloud infrastructure, domain renewals, and AI/API bills to **Detour Athletics LLC's Mercury debit/credit card**.
   - **Tax Advantage (IRC § 162):** The 501(c)(3) pays 0% income tax, so deductions inside the non-profit save `$0`. Inside Detour Athletics LLC (Schedule C pass-through), every `$1.00` of tech spend is a **100% tax-deductible business expense** offsetting taxable coaching revenue at your ~40%+ marginal tax rate.
   - **IP Protection:** Paying the hosting bills from the LLC reinforces that the domains, codebase, and database are **100% LLC property** licensed royalty-free to the 501(c)(3) under the *Revocable IP, Brand & Technology License Agreement*.
2. **What the 501(c)(3) Bank Account Pays For:**
   - **Detour Run Club Inc.** pays strictly for direct non-profit community expenses: RRCA membership & liability insurance (`$395/yr`), NY DOS incorporation (`$75`), Bakline wholesale kit invoices, and marathon cheer/aid station supplies (exempt from `8.875%` NY sales tax via Form ST-119.1).
   - **Optional Exact-Cost Reimbursement:** If the 501(c)(3) treasury ever holds surplus cash, it may reimburse the LLC for its documented, proportional share of actual 3rd-party email/database costs at **exact cost (`0%` markup)**, or repay principal on your **0% Founder Promissory Note** (`02_FOUNDER_ZERO_PERCENT_PROMISSORY_NOTE_501C3.md`) 100% tax-free.
