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
| **Title** | 1 | A:I merged | `{athlete}` |
| **Subtitle** | 1 | A:I merged | `VDOT {v} · Goal: {time} · Anchor: {last marathon}` |
| **Narrative** | 1 | A:I merged | Deterministic factual summary (weeks, method, goal, w_now→peak) |
| *(blank)* | 1 | | |
| **Paces block** | 1 header + 4 | B:E | `YOUR PACES (per mile)` → Easy / Marathon Pace / Threshold / Interval |
| *(blank)* | 1 | | |
| **Table header** | 1 | B:I | `Wk · Date · Sun · Mon · Tue · Wed · Thu · Fri · Sat · Total · Why` |
| **Phase band** | 1 per phase | A:I merged | e.g. `BASE   Weeks 1–5 · Build the aerobic engine` |
| **Week rows** | 1 per week | B:I | Wk, week-Saturday date, the seven day cells (Sun→Sat), weekly total, Why |
| **Race band + row** | 2 | A:I / B:I | `RACE DAY  {date}` band, then the marathon in its actual weekday cell |

**Columns** read as a plain calendar week, **Sunday → Saturday**, with all seven days shown —
rest days are spelled out as `Rest Day` so the week reads with its full rhythm. The **Why**
column sits **last** (after Total), so the schedule and weekly volume come first and the rationale
is there only if the athlete wants it. The quality (Q2) and long-run days are not separate columns;
they live in their weekday cells but get wider columns and bold navy emphasis. `WEEK_ORDER` in
`render/plan_layout.py` owns the Sunday-first ordering (the engine stores weeks Monday-first).

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

**Type:** title 15 bold; subtitle/header 9; body 10; pace values 11 bold. Font from the
harvested style bundle (Arial fallback).

**Emphasis conventions**

- **Long-run column** is bold navy on every week row.
- **Why** column is italic gray, size 9, wrapped.
- **Recovery (down) weeks** shade the whole row gray + italic.
- Narrative, day, and Why cells wrap with top vertical alignment.

---

## 4. Per-week "Why" (deterministic)

`render/plan_layout._week_why()` produces the rationale without an LLM, and is written to **not
repeat the phase explanation every week**:

- **Phase intention** (`_PHASE_INTENT`) is stated **once per phase**, on the phase's first week
  (the week the phase band opens, `show_phase_intent`). Later weeks in the phase omit it.
- Down week → a fixed recovery-week note.
- Each week then carries only what's specific to it: its quality day(s) + the metric each targets,
  any notables (VO2max deferral on a step-up, the race-practice dress rehearsal), and the volume
  story — the `+1 mi/day` step-up on the weeks it steps, and the peak **only on the first peak week**.

---

## 5. Workout decoding

Workout shorthand is expanded by `render/workout_glossary.explain_workout_label()`, used to
fill the **Why** column. Example:

> `Marathon long run 13 mi (nonstop): 3.3 E + 5.5 M + 1 T + 1 M + 2.2 E (M @ 8:46/mi)`

→ *Marathon long run (13 mi continuous, no stops): 3.3 mi E (Easy); 5.5 mi M (Marathon pace); …*

**M** in the marathon long run uses **goal marathon pace** (A-goal time), not VDOT marathon
pace — the paces block shows VDOT zones for reference. Workout cells carry no `Q1`/`Q2`
labels; quality days are distinguished visually (bold navy) instead.

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

`theme_from_style_spec()` takes the font from the bundle and keeps the sampled navy/phase
palette as the source of truth.

---

## 7. Related docs

- [`../architecture/interpretation-layer.md`](../architecture/interpretation-layer.md) —
  coach briefs (design intent).
- [`../cheatsheets/01 - CLI Quick Reference.md`](../cheatsheets/01%20-%20CLI%20Quick%20Reference.md) —
  `publish-sheet --hidden`.
