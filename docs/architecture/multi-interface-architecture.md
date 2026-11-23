# Detour Engine (`detour-engine`) — Multi-Interface Architecture & Execution Plan

**Status:** Approved & Active  
**Canonical Repository:** `/Users/tanner/Documents/Projects/detour-engine` (formerly `z2tc`)  
**Core Identity:** Deterministic Physiological Intelligence & Adaptive Periodization Kernel  
**Ecosystem Components:** Detour UI (Web), Detour AI (Coach Kip), Athlete's Own AI (Headless MCP)

---

## 1. Executive Summary & Architectural Philosophy

The **Detour Engine** (`detour-engine`) is the deterministic mathematical and physiological kernel powering training plan generation, athlete readiness modeling, continuous VDOT/pace solving, and event-sourced adaptive replanning for Detour Run Club (DRC).

### The Inviolable Deterministic Seam
The foundational premise of `detour-engine` is **strict determinism in the computational core**:
$$\text{AthleteInputs} + \text{EventHistory} \xrightarrow{\text{detour-engine}} \text{TrainingPlan}$$
- **Zero LLM in the numerical calculation loop:** No LLM is ever used to calculate mileage, pace zones, phase distributions, or down-week volume reductions. Every number originates from peer-reviewed exercise physiology equations (Daniels & Gilbert 1979, Minetti et al. 2002, Pfitzinger, Hansons, Furman FIRST).
- **Auditability & Reproducibility:** Given the identical input payload, the engine produces identical training plans across all execution environments. A coach or athlete can inspect the exact cited physiological rule behind every mileage cap and pace target.

### The Tri-Interface Model
Rather than coupling the engine to a single monolithic web interface, `detour-engine` is architected as a **headless computational kernel** serving three distinct interaction surfaces:
1. **Detour UI (Primary Focus / Starting Surface):** A modern, responsive web application for athlete intake, visual plan navigation, interactive workout cards, and one-click Garmin `.FIT` / Apple `.ICS` exports.
2. **Detour AI (Coach Kip / Hermes Agent):** A conversational agent (operating via Telegram and WhatsApp) that speaks with DRC club voice, debriefs workouts, explains physiological rationale, and translates unstructured athlete check-ins into structured event mutations.
3. **Athlete's Own AI (Headless MCP Server / Bring-Your-Own-Agent):** A standardized Model Context Protocol (MCP) server enabling athletes to connect their personal AI assistants (Claude Desktop, ChatGPT Enterprise, local LLMs) directly to the engine's deterministic toolset.

---

## 2. High-Level System Architecture

```
                                  ┌─────────────────────────────────────────┐
                                  │       DETOUR INTERACTION SURFACES       │
                                  └─────────────────────────────────────────┘
                                                       │
                 ┌─────────────────────────────────────┼─────────────────────────────────────┐
                 ▼                                     ▼                                     ▼
        [ 1. Detour UI ]                        [ 2. Detour AI ]                   [ 3. Athlete's Own AI ]
     (Next.js / Vercel Web)                 (Coach Kip / Hermes)                 (Headless MCP Server)
  • Web Intake & Onboarding             • High-touch voice & chat            • Bring-Your-Own-Agent (Claude/GPT)
  • Visual Calendar & Weekly Grid       • Workout debriefs & empathy         • Local or remote tool calling
  • Workout card detail & pacing        • Unstructured text → events         • Custom prompt & agent workflows
  • One-click Garmin .FIT / .ICS        • Proactive compliance nudges        • Read-only or full replan access
                 │                                     │                                     │
                 │ JSON HTTP / RPC                     │ Event Dispatch                      │ MCP Tool Execution
                 ▼                                     ▼                                     ▼
      ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
      │                                DETOUR ADAPTER / API GATEWAY                                 │
      │   (FastAPI / Python Entry Points / Headless CLI / `main.py` / `mcp_server.py`)              │
      └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
      ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
      │                              DETOUR ENGINE COMPUTATIONAL CORE                               │
      ├─────────────────────────────────────────────────────────────────────────────────────────────┤
      │  • Continuous Bioenergetics: Daniels-Gilbert (1979) continuous VDOT equations               │
      │  • Mechanical Grade-Power: Minetti & di Prampero metabolic terrain adjustments             │
      │  • Multi-Coach Periodization: Daniels 2Q, Pfitzinger 18/55–18/85, Hansons, Furman 3-Day     │
      │  • Safety & Physiology Gates: 3-Hour Continuous Long Run Ceiling & Confidence Protocols    │
      │  • Club Coaching Policy: House rules, volume ramp ceilings, tune-up race seating            │
      │  • Event-Sourced Replan Engine: Immutable event log → state folding → plan mutation         │
      │  • Execution & Compliance Monitor: Prescribed vs actual mileage, cardiac drift scoring      │
      │  • Export Generators: Garmin binary `.FIT` workout builder & standard `.ICS` feeds          │
      └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
      ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
      │                               PERSISTENCE & ARTIFACT STORAGE                                │
      │   `output/detour.db` (SQLite) + Event Sourced Storage + Encrypted Athlete Dossiers          │
      └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Surface Specifications & Integration Contracts

### Surface 1: Detour UI (Primary Starting Surface)
- **Role:** The official visual command center for Detour athletes.
- **Components:**
  - **Athlete Intake Portal:** Connects to `detour-survey` (or native React forms) to capture runner background, weekly volume history, goal race, target pace, days available per week, and injuries.
  - **Dynamic Calendar & Schedule Grid:** Visualizes microcycles (weeks), mesocycles (phases: Base, Quality, Peak, Taper), and individual daily workout cards.
  - **Workout Card Detail:** Displays split breakdowns (E-pace warmup, Threshold reps, Marathon pace tempo, cooldown), target power bands, and pacing guidance.
  - **One-Click Sync & Exports:**
    - `.FIT` files downloaded directly or synced to Garmin Connect for wrist-based step-by-step guidance.
    - `.ICS` iCalendar subscription URL for Apple Calendar / Google Calendar.
- **Contract:**
  - Consumes `PlanArtifact` JSON produced by `build_club_plan()` or `store/db.py`.
  - Sends updated athlete profile inputs (`AthleteInputs`) and returns full season plans.

### Surface 2: Detour AI (Coach Kip / Hermes Agent)
- **Role:** High-touch, conversational coaching partner available via Telegram and WhatsApp.
- **Components:**
  - **Persona:** Direct, encouraging, culturally dialed-in NYC runner ("ROUTES SUBJECT TO CHANGE" // DRC). Humorous, supportive, zero corporate stiffness.
  - **Interpretation & Event Distillation:** Listens to natural-language athlete statements:
    - *"My calf felt super tight at mile 12 on Saturday, had to cut the last 4 miles short."*
    - The LLM boundary (`llm/boundary.py`) parses this statement into a typed event:
      ```json
      {
        "event_type": "injury_flag",
        "date": "2026-10-24",
        "body_part": "calf",
        "severity": "mild",
        "action": "reduce_volume",
        "miles_completed": 12.0,
        "miles_prescribed": 16.0
      }
      ```
  - **Event Dispatch:** Dispatches the event to `detour-engine`'s event log.
  - **Deterministic Replan:** Runs `replan(athlete_id, events)` to adjust upcoming workouts (e.g. converting a midweek Threshold into Easy recovery or adding a cross-training swap).
  - **Coaching Debrief:** Explains the adaptation to the athlete with clinical warmth and psychological reassurance.

### Surface 3: Athlete's Own AI (Headless MCP Server / Bring-Your-Own-Agent)
- **Role:** Exposes `detour-engine` to personal AI agents (Claude, ChatGPT, open-weight models).
- **Components:**
  - **Detour MCP Server (`detour-mcp-server`):** Implements the Model Context Protocol over stdio or SSE.
  - **Exposed Tools:**
    - `detour_calculate_paces(vdot, recent_race_dist_m, recent_race_time_s)`: Returns continuous training pace bands (Easy, Marathon, Threshold, Interval, Repetition) and grade-adjusted power targets.
    - `detour_build_plan(athlete_inputs_json)`: Executes deterministic plan generation, returning structured weeks and workouts.
    - `detour_evaluate_readiness(athlete_id, target_marathon_time)`: Runs two-clock readiness and goal-realism checks.
    - `detour_replan_block(athlete_id, new_events_list)`: Submits events and computes mutated plan.
    - `detour_export_garmin_fit(athlete_id, week_number)`: Generates binary `.FIT` workout files.
  - **Security & Scope Isolation:**
    - Strict athlete ID scoping: external agents can only access the authenticated runner's dossier and plan.

---

## 4. Multi-Tenant Privacy & Knowledge Graph Firewall

The Detour intelligence platform enforces strict separation between public club data, cohort training info, and private athlete biometric/personal data:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KNOWLEDGE GRAPH SCOPES                          │
├────────────────────────────────────────────────────────────────────────┤
│ 1. `scope: "public"`                                                   │
│    • Public DRC routes, cheer stations, club announcements, nutrition  │
│    • Accessible to all UIs, bots, and unauthenticated visitors         │
├────────────────────────────────────────────────────────────────────────┤
│ 2. `scope: "cohort:<cohort_id>"` (e.g. `cohort:chicago_2026`)          │
│    • Group shakeout schedules, pace-group assignments, team dinners    │
│    • Accessible to authenticated runners within that season cohort     │
├────────────────────────────────────────────────────────────────────────┤
│ 3. `scope: "private:<athlete_id>"` (e.g. `private:tanner_19579`)       │
│    • Biometric history, Strava/Garmin auth tokens, injury logs         │
│    • Private coaching notes, financial records, household details      │
│    • STRICTLY FIREWALLED: Zero leakage to shared club chats or feeds  │
└────────────────────────────────────────────────────────────────────────┘
```

Adversarial privacy audits (Tier 5 Red-Team test harness) run on every retrieval query to ensure private dossiers are never surfaced to cohort or public interfaces.

---

## 5. Execution Roadmap & Milestones

### Phase 1: Engine Rebranding & Core Hardening (Current)
- [x] Rename directory from `~/Documents/Projects/z2tc` to `~/Documents/Projects/detour-engine`.
- [x] Create backwards-compatible filesystem symlinks (`z2tc -> detour-engine`).
- [x] Migrate database default to `output/detour.db` with symlink support for legacy `output/z2tc.db`.
- [x] Update core repository documentation (`README.md`, doc references).
- [x] Verify 100% test suite pass rate (`pytest`, 349 passing tests).
- [x] Author comprehensive multi-interface architecture specification.

### Phase 2: Detour UI Integration (Immediate Next Milestone)
- [ ] **Contract Definition:** Formalize the JSON schema exported by `build_club_plan()` for UI consumption.
- [ ] **Export Bridge:** Build lightweight CLI/API exporter generating frontend-ready `season_plan.json` payloads.
- [ ] **UI Implementation in Detour Web:**
  - Create the interactive Season Calendar and Workout Card component.
  - Implement direct client-side `.FIT` downloading and `.ICS` calendar subscription link generator.
- [ ] **Survey Ingestion Pipeline:** Connect `detour-survey` athlete onboarding directly to `AthleteInputs`.

### Phase 3: Detour AI (Coach Kip) Bridge
- [ ] **Event Distillation Layer:** Implement NLP event parser in `llm/boundary.py` mapping runner messages to typed `Event` objects (`MissedWorkout`, `InjuryFlag`, `TaperAdjustment`).
- [ ] **Webhook Gateway:** Connect Telegram/WhatsApp incoming messages to the Hermes agent runtime.
- [ ] **Automated Compliance Scoring:** Run weekly sync comparing Strava/Garmin actuals against prescribed sessions in `detour.db`.

### Phase 4: Headless MCP Server / Bring-Your-Own-AI
- [ ] **FastMCP Implementation:** Create `mcp/server.py` in `detour-engine` exposing core deterministic tools.
- [ ] **Client Setup Documentation:** Provide one-click connection configs for Claude Desktop, Cursor, and custom agent frameworks.
- [ ] **Authentication & Rate Limiting:** Enforce API key/token boundaries for remote multi-athlete access.
