# Official Race Ingestion, Runner Profiling & Continuous Coaching-Style Feedback Specification (`detour-engine` + `detour-web`)

## Goal
Extend `detour-engine` and `detour-web` (`/training`, `/coaching-intake`, `/profile`, and `/join`) with (1) **Official Race Results Ingestion & Multi-Distance Curve Diagnostics** (`NYRR RMS API`, `RTRT.me`, and official PR curves across `5K`–`Marathon` vs. GPS watch splits) and (2) an **End-to-End 3-Stage Runner Profiling & Continuous Coaching Communication Feedback Workflow** so runners can choose *what kind of runner they are* at sign-up, validate their paces during onboarding, and continuously tune *how they prefer to be talked to and coached* after receiving their plan.

---

## Current Context & Assumptions (`[Measured]` Codebase Audit)
- **Official Race Ingestion Already in Codebase (`[Measured]`):**
  - `detour-engine/lib/data_feeds/nyrr.py` (NYRR RMS API official chip lookup), `lib/data_feeds/rtrt.py` (RTRT.me official finish splits), and `lib/data_feeds/chip_lookup.py :: apply_official_chip_times` (which overrides noisy Strava GPS times with verified official chip seconds).
  - `detour-web/public/profile.html` already stores `nyrr_member_id` and official PRs (`pr_5k`, `pr_10k`, `pr_10m`, `pr_half`, `marathon_pr`) for real club members (e.g., Tanner `#53014284`, Cindy `#54608206`, Kelly `#54435032`).
- **Feedback Mechanism Audit (`[Measured]` Gap):**
  - `store/events.py` currently has physiological/load adjustment events (`DifficultyPayload`, `EffortQualityPayload`, `ManualOverridePayload`, `SetCoachingScopePayload`), and `engine/personalization.py` has a `signals` dict for LLM prose smoothing.
  - **Missing:** There are currently **no structured fields or UI workflows** for a runner to self-select their **Runner Information Profile** (`telemetry` Tanner Mode vs. `guided` Cindy Mode vs. `applied_translator` First-Timer Mode), their **Coaching Voice Preference** (`direct_analytical`, `warm_encouraging`, `high_accountability`), or to update how they are talked to / coached **post-onboarding** after receiving their plan.

---

## Architecture & Proposed Approach
We add `nyrr_member_id`, `communication_profile`, `coaching_voice`, and `pace_comfort_choice` to `AthleteInputs`, `SurveyInputs`, and `SetCoachingScopePayload` (`Ticket DRC-101`), and build `engine/pace_calibration.py` (`Ticket DRC-102`) to (1) analyze official multi-distance NYRR/RTRT race curves (`analyze_official_race_curve`) alongside Strava GPS habits, (2) translate `E / M / T / I / R` zones for each persona, and (3) power a **3-Stage Continuous Feedback Loop** across Sign-Up (`/join`, `/profile`), Plan Onboarding (`/training`, `/coaching-intake`), and Post-Onboarding Ongoing Check-Ins (`Tickets DRC-103` & `DRC-104`).

(Full copy-pasteable code, TDD tests, and verification commands are in `/Users/tanner/.hermes/plans/2026-11-13_221438-detour-official-races-and-coaching-feedback-spec.md`.)
