# Club intake (Google Form) — Zone 2 Track Club

**Canonical architecture (intake + engine):** [intake-and-engine.md](intake-and-engine.md). **System map:** [architecture/overview.md](architecture/overview.md).

This replaces the ad-hoc fields in the older workbook ([legacy sheet](https://docs.google.com/spreadsheets/d/1XLM8Pioema3oiAmsihdpigR9vUTLPbHeS1Y-enFOL6o/edit?gid=989262572)) and form ([legacy form](https://docs.google.com/forms/d/12Vft9B-yZwsL-x-11Y01fUaOZuYW-1I-yod-bdkxx5s/edit)).

**Canonical club workbook:** [Zone 2 Track Club Marathon 2026](https://docs.google.com/spreadsheets/d/1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w/edit)

## What Strava already fills (skip on the form or mark “coach will fill”)

These are computed from `marathon-report` / `training` scrapes and should **not** be required from athletes unless you want a sanity check:

| Field | Source |
|-------|--------|
| `w_now` | Trailing ~4-week average run miles from weekly history |
| `p_history` | Max weekly run miles in the **last marathon training block** |
| `longest_run_mi` | Longest run in recent window (or block) |
| `vdot` | From best representative race (half > 10K > 5K > marathon) |

The form should focus on **what Strava cannot know**: goals, race calendar, schedule constraints, injuries, method override.

## Multi-marathon calendar (primary vs secondary)

The plan engine keys the **18-week block + taper + MP** off **one primary A-race** (`race_date`, `race_name`, `goal_marathon_s`). Additional marathons are stored as `secondary_races` for labels, Sheet UI, and coach flags (e.g. recovery between races). Examples:

| Athlete | Primary (block anchor) | Secondary |
|---------|------------------------|-----------|
| Tanner | Chicago (main goal / club build) | NYC |
| Emily | Chicago | NYC |
| Tamara | Berlin | — (or Chicago as social if she still runs with the group) |
| Gaurav | NYC | — |
| Default template | Chicago Oct 10, 2026 | — |

**Rule for the form:** one required “primary marathon” row; optional second (and third) marathon with name + date only (goal time optional later).

## Google Forms API (edit the live intake form)

The legacy form ID is ``12Vft9B-yZwsL-x-11Y01fUaOZuYW-1I-yod-bdkxx5s``. To **programmatically**
add universal 2026 questions and strip Chicago-only travel fields:

1. In [Google Cloud Console](https://console.cloud.google.com/) for the **same project**
   as your ``client_secret_*.json``, enable **Google Forms API**.
2. Run OAuth once (opens a browser; writes ``auth/z2tc_google_token.json``)::

       python scripts/google_oauth_z2tc.py
       export Z2TC_GOOGLE_TOKEN=$PWD/auth/z2tc_google_token.json

3. Preview what would change (no writes)::

       python scripts/update_marathon_intake_form.py --dry-run

4. Apply updates::

       python scripts/update_marathon_intake_form.py --apply

The updater appends a **“2026 Marathon — everyone”** block (primary marathon dropdown,
date, goal time, optional second marathon, days/week, Saturday long run, **one**
race-weekend coordination paragraph for *any* city, injuries, coach notes) and deletes
items whose titles look like hotel/flight-only prompts. Review the form in the UI
afterward (ordering, duplicates).

Override form id: ``Z2TC_INTAKE_FORM_ID=... python scripts/update_marathon_intake_form.py --apply``.

### Section A — Identity

1. **Full name** (short answer)  
2. **Strava profile URL or athlete ID** (short answer) — for matching rows to scrape output  

### Section B — Primary A-race (required)

3. **Primary marathon name** (dropdown or short answer) — e.g. Bank of America Chicago Marathon  
4. **Primary marathon date** (date) — ISO calendar date  
5. **Primary marathon goal time** (time or short answer) — e.g. `3:15:00` or “finish healthy”  

### Section C — Additional marathons (optional)

6. **Second marathon — name** (short answer, optional)  
7. **Second marathon — date** (date, optional)  
8. **Third marathon — name** (short answer, optional)  
9. **Third marathon — date** (date, optional)  

### Section D — Schedule & coaching

10. **Days per week you can run** (linear scale 3–7 or multiple choice)  
11. **Long run day** (multiple choice, single answer) — default **Saturday** only option: “Saturday (club long run)”  
12. **Injury history or current niggles** (paragraph, optional)  
13. **Daniels vs Pfitzinger** (multiple choice: Auto / Prefer Daniels / Prefer Pfitzinger) — default Auto  
14. **Anything else for the coach** (paragraph, optional)  

### Section E — Closing (optional; coach / deliverables, not the numeric engine)

These do not change Daniels/Pfitzinger week math in code today; they drive **human coaching**, club tips, and future “align deload to vacation” tooling.

15. **Do you have any races or vacations planned?** (paragraph) → `intake_races_vacations_notes`  
16. **Other than a training plan, are you looking for nutrition guidance, a music playlist, shoe recommendation, or other tips?** (checkboxes and/or short paragraph) → `intake_coaching_extras_notes`  
17. **Add information about your secondary marathon here if you’d like.** (paragraph) → `secondary_marathon_notes` (structured second marathon name/date still map to `secondary_races`)  
18. **Anything other notes?** (paragraph) → `free_notes`  

### Do **not** ask (unless optional “confirm Strava number”)

- Current weekly mileage, peak last block, recent long run distance, VDOT — unless you add “Confirm my Strava shows ~X mpw: Y/N”.

## Link Form responses into the club spreadsheet

1. In Google Forms: **Responses** tab → spreadsheet icon → **Select existing spreadsheet** → pick **Zone 2 Track Club Marathon 2026** (`1eBaCWrUVDXyrDdF4dN-W_Hxv2IrIbXqCGwv7IvKgS0w`).  
2. Google creates a tab (often **Form Responses 1**). Rename it to **`Intake_responses`**.  
3. Optional: on **Read Me First** or a small **Intake** tab, add `=HYPERLINK("https://docs.google.com/forms/d/<FORM_ID>/viewform","Open intake form")` with your live form URL.  
4. Pipeline later: Apps Script or Python reads `Intake_responses` and merges with Strava-derived columns into `AthleteInputs`.

## Column order (match this when creating the Form)

So the first row of the linked sheet lines up with tooling:

`Timestamp` | `Email` | `full_name` | `strava_id` | `primary_marathon` | `primary_date` | `primary_goal` | `marathon_2_name` | `marathon_2_date` | `marathon_3_name` | `marathon_3_date` | `days_per_week` | `long_run_day` | `injury_notes` | `method_choice` | `races_vacations_notes` | `coaching_extras_notes` | `secondary_marathon_notes` | `other_notes` | `coach_notes`

(Adjust names to match exactly what Google Forms exports; you can rename columns in the Form editor’s “Responses” settings.)

## Script helper

[`scripts/setup_club_intake_sheet.py`](../scripts/setup_club_intake_sheet.py) adds an **Intake_setup** tab to the club spreadsheet with these instructions and a placeholder for the form link (requires Sheets API auth via `render.runtime`).
