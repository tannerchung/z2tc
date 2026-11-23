# Detour Unified CRM & Database Architecture (`SCHEMA_VERSION = 8`)

**Status:** Draft Specification (Pre-Implementation Lock for Post-NYC Marathon 2026)  
**Canonical Repository:** `/Users/tanner/Documents/Projects/detour-engine`  
**Connected Repositories:** `detour-web`, `detour-marathon-hub`, `detour-survey`  
**Architectural Pattern:** Domain-First Canonical Relational Spine + Composable Officer Views + Static Edge Portals  
**Legal & Privacy Boundary:** Strict Dual-Track Separation (`Detour Run Club Inc.` 501(c)(3) vs. `Detour Athletics LLC`)

---

## 1. Executive Summary & Problem Statement

Detour currently operates across **three production data silos** that evolved organically to serve immediate operational needs:

1. **Silo 1 — Member Intake & Kit (`detour-web/api/survey-response.js`):** Writes 31-column Founding Cohort rows to Google Sheet `17Kk8NAKtyF_pAv28rKeCPEeZoY5rQn8KZvGANhlf-N8` (plus backup CSV/JSON). Captures identity, waivers, emergency contacts, NYRR IDs, Bakline singlet sizing, and fueling preferences.
2. **Silo 2 — Race Command Center CMS (`detour-marathon-hub` / `drc-cms-management`):** Pulls a 10-tab Google Sheet (`1MlxS_HbXe_Gu4drkHJFb19wlx1f7pxKHebxa1EZV3-w`, 213 rows) via `scripts/sync_cms_sheet.py` into `data/race-cms.json` for bibs, waves, corrals, gun times, and cheer stations.
3. **Silo 3 — Physiological Kernel (`detour-engine/store/db.py`):** SQLite database (`output/detour.db`, `SCHEMA_VERSION = 7`) containing 9 tables (`athletes`, `seasons`, `survey_baselines`, `plan_artifacts`, `events`, `training_blocks`, `narrative_renders`, `publications`, `weekly_actuals`, `dossier_snapshots`) plus local Garmin OAuth token files (`auth/garmin/<athlete_id>/`).

### Core Architectural Goals
1. **Single Canonical Identity Spine (`core.people`):** Eliminate manual reconciliation (`_adopt_orphan_training_blocks`) across survey submissions, Strava scrapes, Beeper/WhatsApp JIDs, NYRR rosters, and race portals.
2. **Hard 501(c)(3) vs. LLC Firewall:** Enforce database-level schema and role separation between **Detour Run Club Inc.** (community roster, waivers, Bakline kit pool, race-day cheer logistics accessible to club officers Kelly and Cindy) and **Detour Athletics LLC** (commercial 1:1 coaching, physiological dossiers, VDOT/cardiac drift telemetry, and wearable OAuth tokens accessible only to Tanner and the individual athlete).
3. **Zero-Touch Static Portal Compilation:** Replace manual 5-file HTML/JS array editing (`nyc.html`, `nyc-spectator.html`, `nyc-hub.js`, count badges, Obsidian tables) with deterministic build-time generation from the database while keeping public race portals 100% static and offline-resilient.
4. **Composable UI Strategy:** Maintain 100% custom brand UX (`detour-brand-system.css`) for athlete-facing web/chat touchpoints while leveraging off-the-shelf grid views (two-way Google Sheets sync / Supabase Table Editor) for internal officer operations.

---

## 2. The 9-Persona Architecture Council

To prevent blind spots, this schema is architected through nine specialized lenses:

| Persona Lens | Primary Concern | Key Schema & System Mandates |
| :--- | :--- | :--- |
| **1. Systems Designer** | Canonical identity, state boundaries, anti-drift | Unified `person_id` slug (`kelly-hession`); separation of mutable contact attributes from immutable event-sourced physiological artifacts (`inputs_hash`). |
| **2. Backend Developer** | Serverless vs. local SQLite parity, zero busywork | Dual-target SQL compatibility (SQLite `detour.db` for local CLI speed + Managed Postgres/Supabase or Turso for Vercel `/api/*` webhooks); delegate email to Resend and payments to Stripe. |
| **3. Frontend Developer** | Eliminating manual HTML/JS edits; offline race resilience | Build-time compiler (`club.race_entries` -> `data/race-cms.json` -> static HTML/JS); never query live databases or Sheets from client browsers on race day. |
| **4. UI/UX Team** | Zero app-download friction for runners; fast officer triage | Keep athletes in WhatsApp, Strava, and mobile web (`/nyc`, `/survey`); give club officers (Kelly, Cindy) clean tabular views over `club.*` without building a custom React Admin app from scratch. |
| **5. Privacy & Security Architect (CISO)** | PII protection, OAuth token security, RAG red-teaming | Encrypt Garmin/Strava OAuth tokens at rest; enforce `scope: "private:<athlete_id>"` firewall in GBrain/MCP; strip residential addresses and raw phone numbers before emitting `race-cms.json` (`BANNED_DRIFT_PATTERNS`). |
| **6. Non-Profit & Tax Counsel (CPA)** | 501(c)(3) RRCA compliance, NY clickwrap waivers, UBIT firewall | Append-only `club.waiver_acceptances` table capturing immutable timestamp, waiver text version, and IP/UA hash; strict separation of tax-free Bakline gear margin (`club.kit_orders`) from LLC coaching revenue (`coaching.subscriptions`). |
| **7. Run Club COO & Supply-Chain Director** | Bakline 15-unit MOQ drops, float inventory, NYRR compliance, aid stations | Track singlet cuts/sizes, wholesale vs. club retail margin, unpaid claims, spare float inventory, NYRR club affiliation verification, and Mile 6.7 / Mile 18.2 aid station requests (Maurten 100/160, layer drops). |
| **8. Exercise Physiologist & Data Scientist** | Longitudinal fleet calibration, injury prevention, gear decay | Preserve `dossier_snapshots` (`responder`, `volume_vdot_corr`, `endurance_gap`, `Pa:Hr` drift), structured fueling/GI sensitivity (`gi_sensitivity_level`), and shoe mileage retirement alerts (>300 mi). |
| **9. AI & Agentic Context Architect** | Sub-10ms identity lookup for Coach Kip (WhatsApp) & MCP | Index `phone_e164` and `beeper_jid` on `core.people` so inbound athlete texts immediately resolve active season, pronouns, current training week, and pending `engine.events` proposals. |

---

## 3. Multi-Schema Entity-Relationship Architecture

In Postgres (Supabase), tables are partitioned across four explicit database schemas (`core`, `club`, `engine`, `coaching`) with Row-Level Security (RLS). In local SQLite (`output/detour.db`, `SCHEMA_VERSION = 8`), schemas map to table prefixes (`core_`, `club_`, `engine_`, `coaching_`) with identical column definitions.

```
                         ┌───────────────────────────────────────────────┐
                         │                  core.people                  │
                         │  id (PK slug: 'tanner-chung')                 │
                         │  first_name, last_name, display_name          │
                         │  pronouns, birthday, neighborhood             │
                         │  email (UQ), phone_e164 (UQ), beeper_jid      │
                         │  instagram_handle, strava_athlete_id (UQ)     │
                         │  nyrr_member_id (UQ), privacy_tier            │
                         └───────────────────────┬───────────────────────┘
                                                 │
        ┌────────────────────────────────────────┼────────────────────────────────────────┐
        │                                        │                                        │
        ▼                                        ▼                                        ▼
┌───────────────────────────────┐      ┌───────────────────────────────┐      ┌───────────────────────────────┐
│     TRACK 1: CLUB (501c3)     │      │   TRACK 2A: ENGINE (Kernel)   │      │  TRACK 2B: COACHING (LLC)     │
│  RLS: club_officer, admin     │      │  RLS: coach_admin, owner_only │      │  RLS: coach_admin, owner_only │
├───────────────────────────────┤      ├───────────────────────────────┤      ├───────────────────────────────┤
│ • club.memberships            │      │ • engine.seasons              │      │ • coaching.intakes            │
│ • club.waiver_acceptances     │      │ • engine.survey_baselines     │      │ • coaching.subscriptions      │
│ • club.emergency_contacts     │      │ • engine.plan_artifacts       │      │ • coaching.oauth_connections  │
│ • club.kit_drops              │      │ • engine.events               │      │ • coaching.equipment_shoes    │
│ • club.kit_orders             │      │ • engine.training_blocks      │      │ • coaching.session_notes      │
│ • club.races                  │      │ • engine.weekly_actuals       │      └───────────────────────────────┘
│ • club.race_entries           │      │ • engine.dossier_snapshots    │
│ • club.cheer_stations         │      │ • engine.narrative_renders    │
│ • club.race_schedule_events   │      │ • engine.publications         │
└───────────────────────────────┘      └───────────────────────────────┘
```

---

## 4. Detailed Table Specifications (DDL Contract)

### 4.1 `core` Schema — Canonical Identity & Channel Resolution

#### `core.people` (Upgraded from `athletes`)
The single source of truth for every human interacting with Detour (club member, race spectator/volunteer, or 1:1 coached athlete).

```sql
CREATE TABLE IF NOT EXISTS core_people (
    id TEXT PRIMARY KEY,                      -- Canonical slug, e.g. 'kelly-hession', 'tanner-chung'
    uuid TEXT UNIQUE NOT NULL,                -- Immutable UUIDv4 for external webhook references
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    display_name TEXT NOT NULL,               -- Public display name (e.g. 'Ignatius "Iggy" Petilla')
    pronouns TEXT,                            -- e.g. 'she/her', 'he/him', 'they/them'
    email TEXT UNIQUE,                        -- Normalized lowercase email
    phone_e164 TEXT UNIQUE,                   -- Normalized E.164 phone (e.g. '+14045551234')
    beeper_whatsapp_jid TEXT,                 -- For instant Coach Kip WhatsApp/Beeper resolution
    birthday TEXT,                            -- ISO 'YYYY-MM-DD' or 'MM-DD'
    neighborhood TEXT,                        -- e.g. 'Park Slope', 'Williamsburg', 'UES'
    address_private TEXT,                     -- Encrypted/restricted; NEVER exported to race-cms.json
    instagram_handle TEXT,                    -- Normalized without '@'
    strava_athlete_id TEXT UNIQUE,            -- Canonical numeric Strava ID (e.g. '12345678')
    strava_profile_url TEXT,                  -- Canonical https://www.strava.com/athletes/...
    nyrr_member_id TEXT UNIQUE,               -- NYRR Member ID for club roster & race lookup
    privacy_scope TEXT NOT NULL DEFAULT 'private', -- 'private:<id>' | 'cohort' | 'public'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_people_email ON core_people(email);
CREATE INDEX IF NOT EXISTS idx_people_phone ON core_people(phone_e164);
CREATE INDEX IF NOT EXISTS idx_people_strava ON core_people(strava_athlete_id);
```

---

### 4.2 `club` Schema — Detour Run Club Inc. (501(c)(3) Community & Race Ops)

Accessible to `club_officer` roles (Tanner, Kelly, Cindy) and synced two-way with the Officer Google Sheets.

#### `club.memberships`
Tracks club roster status, NYRR club affiliation compliance, and runner preferences from `/survey`.

```sql
CREATE TABLE IF NOT EXISTS club_memberships (
    person_id TEXT PRIMARY KEY REFERENCES core_people(id),
    cohort_year TEXT NOT NULL DEFAULT '2026 Founding',
    member_status TEXT NOT NULL DEFAULT 'active',  -- 'prospect' | 'active' | 'alumni' | 'officer'
    club_role TEXT NOT NULL DEFAULT 'member',      -- 'member' | 'president' | 'vp_medical' | 'captain'
    pace_bracket TEXT,                             -- e.g. '8:00-8:30/mi', '9:30-10:00/mi'
    primary_race_target TEXT,
    nyrr_member_status TEXT,                       -- 'active' | 'none' | 'expired'
    nyrr_club_affiliation TEXT,                    -- 'Detour Run Club' | 'Unattached' | 'Other'
    nyrr_recent_race TEXT,
    nyrr_volunteer_history TEXT,
    dietary_restrictions TEXT,
    fuel_brand_and_type TEXT,                      -- e.g. 'Maurten 100 (25g hydrogel)'
    gi_sensitivity_level TEXT,                     -- 'Iron Stomach' | 'Moderate' | 'Sensitive'
    post_run_treat_pref TEXT,
    founder_tag_vote TEXT,
    joined_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT
);
```

#### `club.waiver_acceptances` (Immutable Legal Audit Log)
Replaces mutable boolean columns with an append-only audit log for RRCA and NY General Obligations Law negligence waiver defense.

```sql
CREATE TABLE IF NOT EXISTS club_waiver_acceptances (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES core_people(id),
    waiver_type TEXT NOT NULL,                -- 'rrca_safety_negligence' | 'photo_media_release' | 'coaching_par_q'
    waiver_version TEXT NOT NULL,             -- e.g. '2026.1-ny-clickwrap'
    accepted INTEGER NOT NULL DEFAULT 1,
    accepted_at_utc TEXT NOT NULL,
    source_surface TEXT NOT NULL,             -- 'detourrunclub.com/survey' | 'google_form'
    ip_hash TEXT,                             -- SHA-256 salted hash for clickwrap verification
    user_agent TEXT,
    raw_payload_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_waivers_person ON club_waiver_acceptances(person_id, waiver_type);
```

#### `club.emergency_contacts`
Strictly scoped to `club_officer` and medical captains (Kelly) for race-day and long-run incident response; never exported to public JSON/HTML.

```sql
CREATE TABLE IF NOT EXISTS club_emergency_contacts (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES core_people(id),
    contact_name TEXT NOT NULL,
    contact_phone_e164 TEXT NOT NULL,
    relationship TEXT,
    medical_notes TEXT,
    updated_at TEXT NOT NULL
);
```

#### `club.kit_drops` & `club.kit_orders` (Bakline Supply-Chain & Treasury Ledger)
Manages the 75–90 day Bakline production clock, 15-unit MOQ tracking, silent treasury margins, and spare float inventory.

```sql
CREATE TABLE IF NOT EXISTS club_kit_drops (
    id TEXT PRIMARY KEY,                      -- e.g. '2026-fall-founding-mesh'
    name TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT 'Bakline',
    mechanism TEXT NOT NULL,                  -- 'hosted_shopify' | 'bulk_float_purchase'
    order_window_open TEXT,
    order_window_close TEXT,
    target_delivery_date TEXT,                -- Must precede key race date by >=14 days
    moq_threshold INTEGER NOT NULL DEFAULT 15,
    status TEXT NOT NULL DEFAULT 'planning'   -- 'planning' | 'open' | 'in_production' | 'delivered'
);

CREATE TABLE IF NOT EXISTS club_kit_orders (
    id TEXT PRIMARY KEY,
    drop_id TEXT NOT NULL REFERENCES club_kit_drops(id),
    person_id TEXT REFERENCES core_people(id), -- NULL if unallocated club float inventory
    is_float_inventory INTEGER NOT NULL DEFAULT 0,
    garment_sku TEXT NOT NULL,                -- 'mens_unisex_singlet' | 'womens_speed_crop' | 'half_zip'
    garment_cut_label TEXT NOT NULL,          -- 'MEN’S / UNISEX TEE' | 'WOMEN’S / SPEED CROP'
    size TEXT NOT NULL,                       -- 'XS' | 'S' | 'M' | 'L' | 'XL'
    secondary_items_json TEXT DEFAULT '[]',
    wholesale_cost_cents INTEGER NOT NULL,    -- e.g. 2900 ($29.00)
    club_price_cents INTEGER NOT NULL,        -- e.g. 4200 ($42.00)
    net_margin_cents INTEGER NOT NULL,        -- e.g. 1300 (+$13.00 tax-free to 501c3 treasury)
    payment_status TEXT NOT NULL DEFAULT 'interest_ballot', -- 'interest_ballot' | 'invoiced' | 'paid' | 'comped'
    payment_method TEXT,                      -- 'bakline_portal' | 'venmo' | 'zelle' | 'stripe'
    fulfillment_status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'handed_off' | 'exchanged'
    created_at TEXT NOT NULL,
    notes TEXT
);
```

#### `club.races`, `club.race_entries`, & `club.cheer_stations` (Race Command Center CMS)
Powers `data/race-cms.json`, `nyc.html`, and `nyc-spectator.html` without manual multi-file HTML edits.

```sql
CREATE TABLE IF NOT EXISTS club_races (
    race_slug TEXT PRIMARY KEY,               -- e.g. 'nyc-2026', 'chicago-2026', 'brooklyn-half-2027'
    name TEXT NOT NULL,                       -- '2026 TCS New York City Marathon'
    race_date TEXT NOT NULL,                  -- '2026-11-01'
    distance_m REAL NOT NULL DEFAULT 42195.0,
    cms_sheet_id TEXT,                        -- Linked Google Sheet ID for officer editing
    status TEXT NOT NULL DEFAULT 'upcoming',  -- 'upcoming' | 'live' | 'completed'
    config_json TEXT NOT NULL DEFAULT '{}'    -- Maps 01_Race_Config_&_Links
);

CREATE TABLE IF NOT EXISTS club_race_entries (
    id TEXT PRIMARY KEY,
    race_slug TEXT NOT NULL REFERENCES club_races(race_slug),
    person_id TEXT NOT NULL REFERENCES core_people(id),
    role TEXT NOT NULL DEFAULT 'runner',      -- 'runner' | 'cheer_squad' | 'aid_captain' | 'pacer'
    participation_status TEXT NOT NULL DEFAULT 'confirmed', -- 'confirmed' | 'deferred' | 'dns' | 'finished'
    bib_number TEXT,                          -- e.g. '19579', '41832'
    wave_number INTEGER,                      -- 1..5
    wave_label TEXT,                          -- e.g. 'Wave 1'
    corral_code TEXT,                         -- e.g. 'A', 'B', 'C'
    corral_color TEXT,                        -- 'Orange' | 'Blue' | 'Pink'
    gun_time_local TEXT,                      -- e.g. '09:10 AM'
    ferry_or_bus_time TEXT,                   -- e.g. '06:15 AM Ferry'
    start_village_gate TEXT,
    aid_station_requests_json TEXT DEFAULT '{}', -- Specific gels/layers held at Mile 6.7 or Mile 18.2
    finish_time_s INTEGER,                    -- Official chip time post-race
    public_visibility INTEGER NOT NULL DEFAULT 1, -- Controls inclusion in public nyc.html / nyc-spectator.html
    UNIQUE(race_slug, person_id)
);

CREATE TABLE IF NOT EXISTS club_cheer_stations (
    id TEXT PRIMARY KEY,
    race_slug TEXT NOT NULL REFERENCES club_races(race_slug),
    mile_marker REAL NOT NULL,                -- e.g. 6.7, 18.2 (validated against official course map)
    station_name TEXT NOT NULL,               -- e.g. 'Upper East Side DRC Aid Station'
    cross_streets TEXT NOT NULL,              -- e.g. '1st Ave & E 93rd St'
    runner_side TEXT NOT NULL,                -- 'Runner''s Right (East Curb)' | 'Runner''s Left (West Curb)'
    anchor_person_id TEXT REFERENCES core_people(id),
    transit_instructions TEXT,
    supplies_json TEXT DEFAULT '[]',          -- ['Water', 'Maurten 100', 'Candy', 'Layer Drop']
    sort_order INTEGER NOT NULL DEFAULT 0
);
```

---

### 4.3 `engine` & `coaching` Schemas — Detour Athletics LLC (Commercial & Physiological Firewall)

Strictly locked to `coach_admin` (Tanner), the deterministic `detour-engine`, and scoped athlete self-service (`private:<athlete_id>`). **Never exposed to `club_officer` spreadsheets or public build artifacts.**

#### Existing `detour-engine` Tables (Retained 1:1 with `person_id` Foreign Key Alignment)
1. `engine.seasons` (`id`, `athlete_id` -> `core_people.id`, `label`, `race_date`, `status`, `meta_json`)
2. `engine.survey_baselines` (`season_id`, `athlete_id`, `updated_at`, `payload_json`)
3. `engine.plan_artifacts` (`id`, `season_id`, `athlete_id`, `created_at`, `inputs_hash`, `plan_json`, `resolved_inputs_json`, `engine_version`, `club_policy_version`)
4. `engine.events` (`id`, `season_id`, `athlete_id`, `ts`, `source`, `status`, `event_type`, `payload_json`)
5. `engine.training_blocks` (`id`, `athlete_id`, `strava_athlete_id`, `source`, `scraped_at`, `marathon_date`, `marathon_name`, `marathon_time_s`, `block_start`, `block_end`, `weeks_json`, `report_json`, `profile_json`)
6. `engine.weekly_actuals` (`season_id`, `athlete_id`, `week_start`, `run_miles`, `source`, `updated_at`)
7. `engine.dossier_snapshots` (`id`, `season_id`, `athlete_id`, `computed_at`, `dossier_version`, `inputs_fingerprint`, `full_json`, `responder`, `demonstrated_opener_mpw`, `peak_mpw`, `sustainable_low_mpw`, `sustainable_high_mpw`, `volume_vdot_corr`, `endurance_gap`, `current_vdot`, `anchor_age_days`, `anchor_stale`, `injury_prone`)
8. `engine.narrative_renders` & `engine.publications`

#### New `coaching` Tables (`SCHEMA_VERSION = 8` Additions)

```sql
CREATE TABLE IF NOT EXISTS coaching_subscriptions (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES core_people(id),
    entity_legal_name TEXT NOT NULL DEFAULT 'Detour Athletics LLC',
    service_tier TEXT NOT NULL,               -- 'adaptive_1on1' | 'plan_audit' | 'club_scholarship'
    monthly_rate_cents INTEGER NOT NULL,      -- e.g. 17500 ($175/mo) to 25000 ($250/mo)
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'prospect',  -- 'prospect' | 'screen_scheduled' | 'active' | 'paused' | 'churned'
    par_q_cleared INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    coach_private_notes TEXT
);

CREATE TABLE IF NOT EXISTS coaching_oauth_connections (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES core_people(id),
    provider TEXT NOT NULL,                   -- 'garmin_connect' | 'strava' | 'coros'
    provider_user_id TEXT,
    token_store_ref TEXT NOT NULL,            -- Encrypted token reference or local vault path
    scopes TEXT,
    status TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'expired' | 'revoked'
    last_sync_at TEXT,
    UNIQUE(person_id, provider)
);

CREATE TABLE IF NOT EXISTS coaching_equipment_shoes (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES core_people(id),
    strava_gear_id TEXT UNIQUE,
    brand_model TEXT NOT NULL,                -- e.g. 'Brooks Ghost 16', 'Nike Alphafly 3'
    role TEXT NOT NULL DEFAULT 'daily',       -- 'daily' | 'long_run' | 'workout' | 'race_carbon'
    logged_miles REAL NOT NULL DEFAULT 0.0,
    retire_threshold_miles REAL NOT NULL DEFAULT 325.0,
    status TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'alert_near_limit' | 'retired'
    updated_at TEXT NOT NULL
);
```

---

## 5. Role-Based Access Control (RBAC) & Privacy Firewall Matrix

| Data Surface / Schema | Public Web (`race-cms.json`) | Club Officers (Kelly / Cindy) | Athlete Self / Own MCP | Coach Kip (Group Chat) | Coach Kip (1:1 DM) / Tanner |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`core.people` (Display Name, Hood, Strava URL)** | Read (Opt-in) | Read / Write | Read / Write (Own) | Read | Full |
| **`core.people` (Phone, Email, Address, DOB)** | **BLOCKED** | Read (`club_officer`) | Read / Write (Own) | **BLOCKED** | Full |
| **`club.memberships` & `club.kit_orders`** | **BLOCKED** | Read / Write | Read (Own) | **BLOCKED** | Full |
| **`club.emergency_contacts` & `waiver_acceptances`** | **BLOCKED** | Read (`vp_medical`) | Read / Write (Own) | **BLOCKED** | Full |
| **`club.race_entries` (Bib, Wave, Corral, Gun)** | Read (Active Runners) | Read / Write | Read / Write (Own) | Read | Full |
| **`engine.*` (VDOT, Plans, Dossiers, Injury Events)** | **BLOCKED** | **BLOCKED** | Read / Replan (Own) | **BLOCKED** (Zero Target-Time Blasting) | Full (`private:<id>`) |
| **`coaching.*` (Stripe Billing, Garmin OAuth)** | **BLOCKED** | **BLOCKED** | Read (Own) | **BLOCKED** | Full (LLC Only) |

---

## 6. Data Flow & Integration Pipelines

### Flow 1: Member Onboarding (`/survey` -> Canonical Spine + Sheets Mirror)
1. Athlete submits `detourrunclub.com/survey` (`api/survey-response.js`).
2. Server validates `safety_waiver` and `photo_waiver`, sanitizes formula injection (`sanitizeSheetCell`), and sends Resend confirmation receipt (`RESEND_API_KEY`).
3. **Dual Write:**
   - Upserts `core.people`, `club.memberships`, `club.waiver_acceptances`, `club.emergency_contacts`, and `club.kit_orders` in the canonical database.
   - Appends the 31-column row to the Founding Cohort Google Sheet (`17Kk8...`) so Kelly and Cindy have immediate visibility without changing their workflow.

### Flow 2: Zero-Touch Race Portal Build (`club.race_entries` <-> `race-cms.json` -> HTML)
1. Officers edit bibs, waves, corrals, or cheer station supplies in the Race Command Center Google Sheet (`1MlxS...`) **OR** Tanner updates `club.race_entries` via CLI/Hermes.
2. `scripts/sync_cms_sheet.py` runs bidirectional reconciliation with `club.race_entries`, validates `BANNED_DRIFT_PATTERNS` (no residential addresses, no unmasked phones, no target finish times), and emits `data/race-cms.json`.
3. A lightweight generator script (`scripts/build_race_portals.py`) reads `data/race-cms.json` and automatically renders the roster tables, wave gun cards, `RUNNERS` JS array, and dynamic runner/squad counter badges in `nyc.html` and `nyc-spectator.html`.

### Flow 3: Conversational Coaching & Event-Sourced Replan (WhatsApp/Beeper -> `engine.events`)
1. Athlete messages Coach Kip on WhatsApp/Beeper (`+1...` or JID).
2. Kip resolves `core.people.id` via `idx_people_phone` in <10ms and loads only `scope: "private:<athlete_id>"` context.
3. Unstructured feedback (e.g., *"Cut my long run at 12 miles, tight calf"*) is parsed into a typed `engine.events` row (`event_type: "injury_flag"`), triggering deterministic `replan()` and optional Garmin `.FIT` workout re-upload.

---

## 7. Phased Implementation Plan (Post-NYC Marathon 2026)

### Phase 1: Local Schema Upgrade (`SCHEMA_VERSION = 8` in `detour-engine`) — Week of Nov 3, 2026
- Upgrade `detour-engine/store/db.py` from `SCHEMA_VERSION = 7` to `8` by adding `core_people`, `club_memberships`, `club_waiver_acceptances`, `club_emergency_contacts`, `club_kit_drops`, `club_kit_orders`, `club_races`, `club_race_entries`, `club_cheer_stations`, and `coaching_*` tables.
- Maintain a backwards-compatible view/alias on `athletes` so all existing `detour-engine` CLI commands (`pull-intake`, `athlete-report`, `publish-sheet`) pass 100% of existing `pytest` suites without modification.

### Phase 2: Historical Backfill & Identity Deduplication — Week of Nov 3, 2026
- Write `scripts/backfill_unified_crm.py` to ingest and deduplicate:
  1. All 31-column rows from the Founding Member Survey Sheet (`17Kk8...`).
  2. All 213 rows from the NYC 2026 Race Command Center Sheet (`1MlxS...`).
  3. All existing `athletes`, `seasons`, and `training_blocks` in `output/detour.db`.
- Verify zero orphan Strava blocks and 100% slug alignment (`tanner-chung`, `kelly-hession`, `rohan-shetty`, `emily-bennett`, `cindy-kim`, `michelle-...`, `iggy-petilla`, `erika-...`, `gaurav-goel`, `nina-sayson`).

### Phase 3: Template-Driven Portal Builder & Cloud Sync — Mid-November 2026
- Replace hardcoded HTML/JS runner arrays in `detour-marathon-hub` with build-time generation from `club.race_entries` -> `data/race-cms.json`.
- Mirror `detour.db` to managed cloud storage (Supabase Postgres with RLS or Turso libSQL) and wire `detour-web/api/survey-response.js` to write directly to the canonical tables alongside the Google Sheet mirror.
