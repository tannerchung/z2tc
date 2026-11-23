# Stage 0 MVP Plan: User-Friendly Coaching Lenses & The "App + Coach Tanner" Accountability Loop (`detourrunclub.com/training`)

## Goal
Ship the **Stage 0 MVP (`/training.html` + `engine/pace_calibration.py`)** with **human, runner-friendly UI Lens Pills (`SIMPLE & CLEAR` [Default] · `LEARN BY FEEL` · `DEEP DATA & SCIENCE`)** and an explicit **"How This Works: The Engine + Coach Tanner + Your Accountability Loop"** module designed so your very first test athlete (Cindy) immediately understands how the app fits into her week, where you come in as her human coach, and how you will keep her accountable without adding stress.

---

## 1. User-Friendly UI Lens Pill Names (Ordered so Athlete #1 Lands on `SIMPLE & CLEAR` by Default)

| Schema ID | **New User-Friendly UI Pill Name** | Subtitle on Pill | What It Shows |
| :--- | :--- | :--- | :--- |
| **`directive`** *(Default)* | **`1. SIMPLE & CLEAR`** | *"Tell me what to run + a quick why"* | Plain-English 3-step run brief (`Warm-Up -> Main Effort -> Cool-Down`) + one clear sentence on why today's run helps. |
| **`foundational`** | **`2. LEARN BY FEEL`** | *"Teach me how each pace should feel"* | Pairs every zone and workout with **Talk-Test & Breathing Cues** (*"Full sentences"* vs. *"3–4 words max"*). |
| **`analytical`** | **`3. DEEP DATA & SCIENCE`** | *"Show me the VDOT math & physiology"* | Full `%VO2max`, VDOT decay curves, official chip-vs-GPS math, and physiological limiters (`MCT1/MCT4`, `GCT`). |

---

## 2. What Cindy Expects (Interaction, Coach Tanner's Role & Accountability)

1. **How the App Interacts With Her Day-to-Day:**
   - **Zero Manual Spreadsheets:** She runs with her watch/Strava like normal; completed runs sync automatically.
   - **5-Second Morning Clarity:** Every workout reads like a text from a coach (*What to do* + *1 sentence on why it helps*).
   - **Guilt-Free Life Shuffling:** When work blows up mid-week, she taps **`🔄 Work Got Crazy — Shuffle My Week`** (or texts you) and her week rebalances around Saturday's DRC long run.
2. **Where Coach Tanner Comes In vs. The Engine ("The Co-Pilot Contract"):**
   - **The Engine (24/7 Math & Guardrails):** Pulls official NYRR chip results + 12 weeks of Strava volume, calculates `E/M/T/I/R` paces, and flags grey-zone habits (like running easy days 46s/mi too fast).
   - **Coach Tanner (Human-in-the-Loop):** Reviews her comfort check before locking Week 1, sends a personal **Sunday/Monday Gameplan Note** after reviewing her Strava week, reshapes her schedule when work/travel hits, and anchors Saturday morning's DRC long run.
3. **How You Keep Her Accountable (`Accountability & Check-In Contract`):**
   - **She Picks Her Accountability Style Up Front:**
     1. **`Warm & Supportive` (`warm_supportive`):** *"Celebrate my consistency, keep pressure low when work is hectic, and help me adjust smoothly."*
     2. **`Steady Weekly Partner` (`weekly_partner`):** *"Check in with me every Sunday/Monday on my 1 key weekday workout + Saturday club long run."*
     3. **`Keep Me Honest` (`high_accountability`):** *"Nudge me if I skip a run and call me out when Strava shows I ran my Easy day too fast!"*
   - **10-Second Post-Workout Pulse to Coach Tanner:** Right on the weekly schedule card, she can tap **`[👍 Nailed It]`**, **`[😮‍💨 Felt Heavy]`**, or **`[🔄 Work Got Crazy — Shuffle My Week]`**, previewing how Coach Tanner + the Engine respond and emit `EffortQuality` / `Difficulty` / `CoachNote` events.

(Full wireframes, user stories, and TDD tasks `Tasks 0.1–0.3` are in `/Users/tanner/.hermes/plans/2026-11-13_232844-detour-mvp-user-friendly-lenses-and-coach-accountability.md`.)
