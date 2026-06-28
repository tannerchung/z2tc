# Plan sheet layout & club workbook styling

**Owns:** deterministic structure and visual rules for athlete plan tabs written by
`publish-sheet` into the club Google workbook (`Z2TC_CLUB_SPREADSHEET_ID`).

**Code:** `render/plan_layout.py`, `render/plan_sheet_format.py`, `render/plan_sheet_theme.py`,
`render/workout_glossary.py`, `render/sheets.py`.

---

## 1. Design goals

1. **Deterministic** — same `TrainingPlan` + `AthleteInputs` always yields the same cell
   grid and formatting (no LLM in the render path).
2. **Matches the hand-styled club tabs** — the generated layout mirrors the shape and palette
   of the existing per-athlete tabs (e.g. `Cindy`): a tight narrative header, a paces block,
   and one color-coded week table with phase bands.
3. **Club-consistent** — palette is sampled verbatim from a real athlete tab, not invented.

Draft tabs are published **hidden** (`publish-sheet --hidden`); coaches unhide to review.

---

## 2. Tab structure (top → bottom)

Single integrated table — no separate brief/glossary sections (those live in the `Workout
Dictionary` tab and the per-week **Why** column).

| Section | Rows | Span | Content |
|---------|------|------|---------|
| **Title** | 1 | A:L merged | `{athlete}` |
| **Subtitle** | 1 | A:L merged | `VDOT {v} · Goal: {time} · Anchor: {last marathon} — {time}` |
| **Narrative** | 1 | A:L merged | Deterministic factual summary (weeks, method, goal, w_now→peak). Drops its "tailored to you" tail when the personalization section is present, to avoid repetition. Adds a responder-profile framing sentence when the dossier is supplied. |
| *(blank)* | 1 | | |
| **Personalization** | 1 header + 1 | A:L merged | `HOW THIS PLAN IS PERSONALIZED TO YOU` + history interpretation (only when a stored training block exists); closes with the dossier's race-history read (volume↔VDOT correlation, endurance gap) when available |
| *(blank)* | 1 | | |
| **Plan notes & cautions** | 1 header + 1 | A:L merged | `PLAN NOTES & CAUTIONS — READ THIS` (amber) — athlete-facing disclaimer in **first-person coach voice** ("I"/"me", not "we"/"your coach") that this is a textbook method *customized* to them: lists what the coach tailored (aggressive ramp, long-run cap, peak above demonstrated, responder bias) and the watch-outs that should prompt them to tell the coach (e.g. goal MP at/past current Threshold, plus weeks the monitor has flagged short or missing quality). Built deterministically by `_plan_caution_block` from coach overrides + the goal-vs-fitness gap + dossier/execution; omitted when there are no deviations. |
| *(blank)* | 1 | | |
| **Paces block** | 1 header + 3–5 | B:E | `YOUR PACES (per mile)` → Easy / **Marathon (goal)** / Threshold / *(Interval, Rep — only if the plan prescribes them)* |
| **Legend** | 1 | B:L merged | `Workout colors:  Easy · Marathon · Threshold …` — each word colored to match the in-cell pace coloring |
| *(blank)* | 1 | | |
| **Phase band** | 1 per phase | A:L merged | e.g. `BASE   Weeks 1–5 · Build the aerobic engine` |
| **Table header** | 1 per phase | B:L | `Wk · Date · Mon … Sun · Total · Why` — **repeated under each phase band** so the day labels return every few weeks (no frozen pane) |
| **Week rows** | 1 per week | B:L | Wk, week-Saturday date, the seven day cells (Mon→Sun), weekly total, Why |
| **Race band + row** | 2 | A:L / B:L | `RACE DAY  {date}` band, then the marathon in its actual weekday cell |

**Columns** read as a plain calendar week, **Monday → Sunday** (weekend last), with all seven days
shown — rest days are spelled out as `Rest Day` so the week reads with its full rhythm. Monday-first
matches the engine's chronological storage, so a **Sunday marathon lands in the last cell** of the
final row (after that week's shakeout) instead of being yanked to the front. The **Why** column sits
**last** (after Total), so the schedule and weekly volume come first and the rationale is there only
if the athlete wants it. The quality (Q2), long-run, and **medium-long** days are not separate
columns; they live in their weekday cells but get wider columns and bold navy emphasis. A
**medium-long** is a non-long easy day big enough to be a key session (`_is_medium_long`: ≥ 8 mi and
either ≥ 10 mi or ≥ 60% of the week's long run) — it is relabeled `Medium-long Run` and emphasized so
it doesn't read like filler. `WEEK_ORDER` in `render/plan_layout.py` owns the Monday-first ordering.

---

## 3. Palette (sampled from the club `Cindy` tab)

RGB are 0–1 fractions (`render/plan_sheet_theme.py`).

| Token | RGB | Used on |
|-------|-----|---------|
| Navy | `0.122, 0.227, 0.373` | title, table header bg, phase-band text, long-run + pace labels |
| Gray text | `0.502, 0.502, 0.502` | subtitle, **Why**, recovery weeks |
| Dark text | `0.149, 0.149, 0.149` | body cells |
| Phase — Base | `0.863, 0.902, 0.949` (light blue) | Base band |
| Phase — Threshold | `0.839, 0.918, 0.875` (light green) | Threshold band |
| Phase — Race Prep | `0.984, 0.906, 0.804` (light tan) | Race Prep band |
| Phase — Taper | `0.906, 0.882, 0.945` (light purple) | Taper band |
| Race day band | navy + white text | `RACE DAY` band |
| Race day row | `0.988, 0.894, 0.839` (peach) + `0.545, 0.18, 0` (dark orange) | the race row |
| Recovery row | `0.961, 0.961, 0.961` + italic gray | down weeks |
| Paces header | `0.933, 0.945, 0.961` | `YOUR PACES` |
| Pace label | `0.961, 0.969, 0.98` | Easy / MP / T / I labels |
| Row separator | `0.85, 0.85, 0.85` | hairline bottom border under each week row |
| Caution text | `0.6, 0.33, 0.0` (amber) | cautions header + body text |
| Caution header bg | `0.988, 0.882, 0.71` | `PLAN NOTES & CAUTIONS` band |
| Caution body bg | `0.996, 0.949, 0.863` | cautions body cell |
| Over-capacity Total | `0.988, 0.882, 0.71` | amber Total when a build week exceeds the demonstrated peak |

**In-cell pace zone colors** (`render/plan_sheet_format.py`, applied as Sheets `textFormatRuns`):

| Zone | RGB | |
|------|-----|--|
| Easy / warm-up / cool-down / steady / strides | `0.502, 0.502, 0.502` (gray) | |
| Marathon pace | `0.6, 0, 0` (maroon) | |
| Threshold / tempo | `0.82, 0.4, 0` (orange) | |
| VO2max intervals / reps | `0.45, 0.2, 0.6` (purple) | |

**Type:** title 15 bold; subtitle/header 9; body 10; pace values 11 bold; rest days 9 italic gray.
**Fonts** are set by the theme, not harvested: **Roboto** for the whole grid (Arial-like metrics, so
column widths are stable) and **Montserrat** for the athlete title only (`title_font_family`). The
harvested style bundle's font is intentionally overridden (`theme_from_style_spec`).

**Emphasis conventions**

- **Long-run, midweek-quality, and medium-long cells** are bold navy on every week row.
- **Why** column is italic gray, size 9, wrapped.
- **Rest days** are de-emphasized (size 9, italic gray) so the eye lands on days that carry work.
- **Over-capacity weeks** — any build week whose total exceeds the athlete's demonstrated peak
  (from the stored training block) gets an **amber Total** cell, a glance-level "this is more than
  you've done before" cue that pairs with the cautions block. Down weeks and the taper are exempt.
- **Wk / Date / Total** columns are center-aligned (header and week rows).
- A **hairline bottom border** separates week rows in the dense grid.
- **Recovery (down) weeks** shade the whole row gray + italic.
- Narrative, day, and Why cells wrap with top vertical alignment.

---

## 4. Per-week "Why" (deterministic)

`render/plan_layout._week_why()` produces the rationale without an LLM, and is written to **not
repeat the phase explanation every week**:

- **Phase intention** (`_PHASE_INTENT`) is stated **once per phase**, on the phase's first week
  (the week the phase band opens, `show_phase_intent`). Later weeks in the phase omit it.
- Down week → a fixed recovery-week note.
- **Each session type's rationale is spelled out once.** The first time a session type appears its
  bullet carries the *why* (e.g. "Wednesday cruise intervals to raise your lactate threshold…");
  later weeks list it tersely ("Wednesday cruise intervals."). Tracked via an `explained` set
  threaded top-down through the week loop (key from `_purpose_key`).
- The **VO2max-deferral caveat** is shown once (first step-up week that defers it), not every time.
- The volume story: the `+1 mi/day` ramp logic is spelled out on the **first** step-up week and just
  states the new number thereafter; the peak is narrated **only on the first peak week**.
- **Execution feedback** (`_execution_note`): once a week has been seen, that week's "Why" gains a
  coach-voice note. From the shortfall-only path (`summarize_execution`) that's a flagged miss —
  short volume (logged-vs-prescribed miles + ratio), a missed quality day, or a coach
  `WeeklyEvaluation` note. When `publish-sheet --training` supplies the current-block feed,
  `execution_from_actuals` scores every elapsed week, so **on-plan weeks get earned positive
  reinforcement** ("on plan — you logged ~X of Y…") and the notes block leads with the consistency
  tally before framing shortfalls as the reason for conservative choices. Sourced from
  `engine.execution.ExecutionSummary`; future / no-data weeks render unchanged.

### Hybrid prose (optional, number-safe)

The three paragraph surfaces (narrative, personalization, notes) are always built deterministically.
`publish-sheet --llm-narrative` then passes them through `llm.boundary.narrate_personalization` for a
tone/cohesion rewrite. The numbers stay the engine's: a subset guard (`validate_numbers_subset`)
rejects any rephrase that introduces a figure not already in the deterministic text, and any failure
(or no API key) falls back to the deterministic prose — so the default render stays test-locked.

---

## 5. Workout decoding

Workout shorthand is expanded by `render/workout_glossary.explain_workout_label()`, used to
fill the **Why** column. Example:

> `Marathon long run 13 mi (nonstop): 3.3 E + 5.5 M + 1 T + 1 M + 2.2 E (M @ 8:46/mi)`

→ *Marathon long run (13 mi continuous, no stops): 3.3 mi E (Easy); 5.5 mi M (Marathon pace); …*

**M** (marathon pace) uses **goal marathon pace** (goal time ÷ 26.2), not VDOT marathon pace.
The engine exposes this as `paces["marathon_goal"]` and the paces card renders it as
**`Marathon (goal)`**, so the card matches the MP cued in every workout cell. The VDOT
`marathon`/`marathon_s` entries are kept for goal-realism comparisons, not display. Workout cells
carry no `Q1`/`Q2` labels; quality days are distinguished visually (bold navy + zone coloring).

---

## 6. Race week

The engine folds race day into the final block week as a `WorkoutKind.RACE` long run
(`engine/plan/daniels.py`). The layout detects that week (`_is_race_week`), renders it as the
`RACE DAY` band + peach race row instead of a training row, and trims it from the phase span
so the taper band ends at the last training week.

---

## 7. Republish safety

Republishing reuses the tab. `render_plan()` **unmerges the whole sheet before writing
values** — otherwise cells under a stale merge from a previous (differently shaped) publish
are silently dropped and the new row renders blank. New merges are reapplied in the format
batch.

---

## 8. Refreshing the theme bundle

```bash
python main.py ingest-style
# → output/club_workbook_style.json (style_spec + spreadsheet_id)
```

`theme_from_style_spec()` keeps the sampled navy/phase palette and the theme's own typography
(**Roboto** grid + **Montserrat** title) as the source of truth — the harvested Arial font is
intentionally overridden, so re-harvesting the bundle won't revert the modern fonts.

---

## 7. Related docs

- [`../architecture/interpretation-layer.md`](../architecture/interpretation-layer.md) —
  coach briefs (design intent).
- [`../cheatsheets/01 - CLI Quick Reference.md`](../cheatsheets/01%20-%20CLI%20Quick%20Reference.md) —
  `publish-sheet --hidden`.
