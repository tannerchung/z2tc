# Formula reference (book-cited)

Provenance for every constant in [`engine/plan/common.py`](../../engine/plan/common.py). Each rule is tagged:

- **verbatim** — the number is stated in the book; page quote given.
- **house rule** — a Zone 2 coaching choice, not in the book (acceptable, but labelled).
- **divergence** — the code says something the book contradicts; should be fixed or re-justified.

Sources are the **latest editions**: *Daniels' Running Formula*, 3rd ed. (2013) and *Advanced Marathoning* (Pfitzinger & Douglas), 2nd ed. (2009). Both PDFs live in the repo.

## Reproducing a citation

Don't quote from memory. Use the page-indexed search tool ([`scripts/book_search.py`](../../scripts/book_search.py)):

```bash
python scripts/book_search.py build                                  # one-time text cache
python scripts/book_search.py search "150 minutes|25 percent" --regex --book daniels
python scripts/book_search.py page --book daniels --page 64          # exact quote
```

Page numbers below are the PDF's 1-based index (the running header is visible in each snippet).

**Page-number offset.** `scripts/book_search.py` uses the **PDF page index**, which differs from the printed book page:

- **Daniels:** `PDF index ≈ printed page + 14` (Contents is PDF p.4; ch.1 starts at printed p.1; the marathon chapter at printed p.213 ≈ PDF p.227). The chapter-start pages in the table below are **printed** pages — add 14 to jump there with the tool.
- **Pfitzinger:** the TOC (PDF p.2-5) lists titles without page numbers; cite by searching for a chapter's section heading. Confirmed anchors: ch.1 physiology ≈ PDF p.42-43, ch.5 taper ≈ PDF p.225, ch.7 workout definitions ≈ PDF p.256-264.

---

## Book map (table of contents + what each chapter is for)

Both tables of contents are transcribed verbatim from the PDFs; the per-chapter purpose is the **author's own description** from the preface (Daniels PDF p.10-11; Pfitzinger PDF p.14-17). The **Backs** column marks the chapters the engine actually draws on.

### Daniels' Running Formula (3rd ed., 2013)

Daniels frames the book as cumulative — "the chapters are sequenced to build on the previous content" (PDF p.10). His philosophy: maximum benefit from the *least* training stress, specific intensities for specific purposes, and "What is the purpose of this workout?" as the test for every session.

*Size = chapter pages · word count · estimated read time. Read time assumes ~220 wpm of prose; chapters dense in tables/figures (e.g., ch.14, the schedule chapters) read much faster than the word count implies because tables are reference, not linear reading.*

| Ch. | Title (printed p.) | Size | Conclusion (key takeaway) | Expected application |
|-----|--------------------|------|---------------------------|----------------------|
| 1 | Ingredients of Success (p.1) | 12 pp · 4.1k · ~19 min | Success = ability + intrinsic motivation + opportunity + direction; plus his "laws of running." | Intake should capture goal, motivation, and life constraints — not just fitness. |
| 2 | Training Principles & Technique (p.13) | 20 pp · 8.2k · ~37 min | Eight principles (stress→adaptation, specificity, individuality, recovery, diminishing returns…); rejects "eggs against the wall" overload. | Ramp + 4th-week cutback + easy-day fill **are** the stress/recovery principles in code. |
| 3 | Aerobic & Training Profiles (p.33) | 14 pp · 4.9k · ~22 min | Running speed maps to physiological stress via aerobic/lactate profiles. | Justifies the pace-zone model behind `engine/paces.py`. |
| 4 | **Training Runs & Intensities** (p.47) | 30 pp · 13.6k · ~62 min | The **E/M/T/I/R** system + per-bout and per-session caps (fig. 4.1, p.62). | ✅ all session caps, long-run, MP, tempo/cruise split. |
| 5 | **VDOT Values** (p.77) | 28 pp · 9.9k · ~45 min | One VDOT (from a recent ≥10K race) sets every training pace; age-graded. | ✅ `engine/paces.py`; intake needs a recent race result. |
| 6 | **Season Training** (p.105) | 12 pp · 4.4k · ~20 min | Build a season in phases (I-IV), each emphasizing a different training type. | ✅ phase structure (Base→Threshold→Race Prep→Taper). |
| 7 | Fitness Training (p.117) | 12 pp · 4.6k · ~21 min | White→red→blue→gold ladders for runners **without** a race goal. | Off-season / base athletes not yet in a marathon block. |
| 8 | Altitude Training (p.129) | 16 pp · 6.3k · ~29 min | Altitude helps some runners; it isn't required for success. | Not modeled. |
| 9 | 800 m Training (p.145) | 16 pp · 8.2k · ~37 min | Anaerobic-heavy R/I work for the 800. | Out of scope (not marathon). |
| 10 | 1,500 m–2 mi Training (p.161) | 14 pp · 7.0k · ~32 min | Speed + strength blend for mid-distance. | Out of scope. |
| 11 | 5K–10K Training (p.175) | 16 pp · 6.0k · ~27 min | High intensity + endurance for 5–10K. | A recent 10K is a valid VDOT input. |
| 12 | Cross Country (p.191) | 12 pp · 5.0k · ~23 min | XC-specific training. | Out of scope. |
| 13 | Half-Marathon (p.203) | 10 pp · 3.6k · ~16 min | Endurance + mileage focus for the half. | A recent **half is the best VDOT input** for a marathoner. |
| 14 | **Marathon Training** (p.213) | 50 pp · 20.3k · ~92 min | The **2Q programs** (Table 14.3): two quality sessions/wk — **Q1 a long, nonstop E/M/T blend**, Q2 a T/I session; paces progress 10 s→4 s→goal over 3×6 wk; needs ≥6 wk base. | ✅ the whole marathon generator; **Q1's blend justifies `mp_long_run`**. |
| 15 | Training Breaks & Supplemental (p.263) | 12 pp · 4.5k · ~20 min | Four layoff categories (≤5 d / ≤4 wk / 4–8 wk / >8 wk) with return protocols; "time off is part of training." | Intake asks recent time off/injury → lower `w_now` + base phase. |
| — | Appendices A-D + Index (p.275+) | ~32 pp | Aerobic profile test, equivalent-distance pace tables, time/pace conversions, high-stress workouts. | Reference tables. |

*(Book total ≈ 320 PDF pages incl. front matter, appendices, index. Chapter 4 + 14 alone are ~2.5 hours of reading and hold almost everything the engine cites.)*

### Advanced Marathoning — Pfitzinger & Douglas (2nd ed., 2009)

Pfitzinger's philosophy (PDF p.13-14): the schedules rest on exercise science, and "the more you understand why you're running a given workout, the more motivated you'll be." Part I explains the principles; Part II is the day-by-day schedules, split by weekly mileage.

| Ch. | Title | Size | Conclusion (key takeaway) | Expected application |
|-----|-------|------|---------------------------|----------------------|
| 1 | **Elements of Training** | 45 pp · 12.0k · ~54 min | *(longest chapter)* Five physiological targets (LT, glycogen, fat use, VO₂max, economy) + periodization (macro → 5 mesocycles → micro) + tune-up races. | ✅ philosophy, the Pfitzinger phase model, the tune-up-race flag. |
| 2 | Nutrition & Hydration | 41 pp · 9.2k · ~42 min | Carbohydrate, protein, iron, race-day fueling. | Coach note; not modeled. |
| 3 | **Balancing Training & Recovery** | 39 pp · 9.3k · ~42 min | Hard/easy principle, recovery days, supercompensation, overtraining signs. | ✅ down weeks + easy-day fill. |
| 4 | Supplementary Training | 72 pp · 9.6k · ~43 min | *(image-heavy)* Flexibility, core, strength, form drills, cross-training. | Supplemental; not in the numeric plan. |
| 5 | **Tapering** | 16 pp · 3.0k · ~14 min | Cut mileage −20-25% / −40% / −60% across the final 3 weeks (p.225). | ✅ `_taper_fracs`. |
| 6 | Race-Day Strategy | 20 pp · 5.0k · ~23 min | Section-by-section pacing (halves → 20 mi → final 10K). | Race day, not the block. |
| 7 | **Following the Schedules** | 30 pp · 5.6k · ~26 min | Defines every workout category (long, medium-long, MP, GA, LT, recovery, VO₂max, speed) + paces (p.256-264). | ✅ long-run / medium-long / MP / LT definitions. |
| 8 | Up to 55 mi/wk | 17 pp · 1.8k · ~8 min | *(tables)* Lowest-mileage 18- and 12-wk schedules; "challenging right from the start." | ✅ volume band; "from the start" → `needs_base_phase`. |
| 9 | 55–70 mi/wk | 18 pp · 1.8k · ~8 min | *(tables)* Mid-mileage 18/12-wk schedules. | ✅ volume band. |
| 10 | 70–85 mi/wk | 18 pp · 1.9k · ~9 min | *(tables)* High-mileage schedules + doubles. | ✅ volume band. |
| 11 | 85+ mi/wk | 19 pp · 2.1k · ~9 min | *(tables)* Elite schedules (100+ mi weeks). | Beyond our typical athletes. |
| 12 | Multiple Marathoning | 34 pp · 4.5k · ~20 min | 12/10/8/6/4-wk schedules between two close marathons. | ✅ `secondary_races` handling. |
| — | Appendices A-C + Glossary + Index (p.390+) | ~46 pp | Race-pace, LT, and VO₂max charts. | Reference charts. |

*(Book total ≈ 435 PDF pages. Part I, ch.1-4, is the bulk of the prose; the schedule chapters 8-11 are short in words but are the day-by-day reference tables.)*

**Where the engine's rules come from:** Daniels ch.4 (intensities + caps), ch.5 (VDOT→paces), ch.6 (phases), ch.14 (marathon programs); Pfitzinger ch.1 (physiology + periodization), ch.3 (recovery/down weeks), ch.5 (taper), ch.7 (long-run / medium-long / MP definitions) and ch.8-10 (volume bands). The constant-by-constant citations below all resolve to these chapters.

---

## Chapter notes (philosophy + intake/plan implications)

Indexing the chapters the engine *doesn't* cite directly — they still shape what we should ask runners at intake and how we frame a block. Grounded in the chapter text (page = PDF index).

### Daniels — the non-engine chapters

- **Ch.1 The Ingredients of Success** (PDF p.15) — four ingredients: **ability, intrinsic motivation, opportunity, direction**, plus his "basic laws of running." Opportunity = the time/life room to train; direction = good coaching. → *Intake:* capture goal + motivation and real-life constraints (days available, schedule), not just fitness.
- **Ch.2 Training Principles & Running Technique** (PDF p.27) — **eight training principles** (P1 *Stress Reaction*, P2 *Specificity*, then individuality, rate of growth, recovery/maintenance, etc.), how to build a plan, stride mechanics, breathing rhythm. Rejects the "eggs against the wall" overload method. → *Plan:* our ramp-then-cutback and easy-day fill **are** the stress-reaction + recovery principles in code.
- **Ch.3 Aerobic & Training Profiles** (PDF p.47) — aerobic and lactate profiles; how running speed maps to physiological stress. Background for why the pace zones exist.
- **Ch.7 Fitness Training** (PDF p.131) — white → red → blue → gold ladders for runners **without** a race goal. → relevant to off-season / base athletes not yet in a marathon block.
- **Ch.8 Altitude Training** (PDF p.143) — living/training high; not modeled.
- **Ch.9-13 Event training** (800 m → half) — event-specific. **Ch.13 Half-Marathon** (PDF p.217) is the most relevant: a recent half is the single best VDOT input for a marathoner (Daniels p.65 prefers a longer race for predicting MP).
- **Ch.15 Training Breaks & Supplemental Training** (PDF p.277) — "time off [is] part of the training process," with **four layoff categories**: I ≤5 days, II up to 4 weeks, III 4-8 weeks, IV >8 weeks (PDF p.284), each with its own return protocol; plus supplemental strength/mobility. → *Intake:* ask about recent time off / injury; a category II+ layoff should lower `w_now` and trigger a base phase.
- **No chapter 16** — the 3rd edition ends at ch.15. **Appendices A-D**: aerobic profile test protocol, equivalent-distance pace tables, time/pace conversions, high-stress workouts.
- **Ch.14 marathon prerequisite** (PDF p.232): *"Before starting any 2Q 18-week program, you should have at least 6 weeks of running under your belt."* Programs are chosen by **mileage category** and days available, in miles/km/**or time**. → this is exactly what `needs_base_phase` + method/volume selection encode.

### Pfitzinger — the non-engine chapters

- **Ch.2 Nutrition & Hydration** — carbohydrate, protein, iron, race-day fueling. Coach note; not modeled.
- **Ch.4 Supplementary Training** — flexibility, core, strength, form drills, cross-training. Supplemental, not in the numeric plan.
- **Ch.6 Race-Day Strategy** — section-by-section pacing (first half → 20 mi → final 10K). Race day, not the block.
- **Ch.11 85+ mi/wk** — elite schedules (100+ mi weeks). Beyond our typical athletes; our volume bands top out around ch.10.
- **Ch.12 Multiple Marathoning** — 12/10/8/6/4-week schedules between two close marathons. → relevant to `secondary_races` handling.
- **Deeper on the engine chapters:**
  - **Ch.1 periodization** (PDF p.61-62): a **macrocycle** (whole 4-6 month build, ~2/yr) → **five mesocycles** — (1) mileage/pure endurance, (2) lactate threshold + endurance, (3) race prep **with tune-up races**, (4) 3-week taper + marathon, (5) recovery — → **microcycles** (weeks). Our Pfitzinger phases (Endurance → LT + Endurance → Race Prep → Taper) **are** mesocycles 1-4; the tune-up-race flag mirrors mesocycle 3 (PDF p.64: tune-ups are "benchmarks of your fitness").
  - **Ch.3 recovery**: hard/easy principle, recovery days, supercompensation, overtraining signs → our down weeks + easy-day fill.
  - **Ch.8-11 "Before Starting the Schedules"** (PDF p.285): *"These schedules are challenging right from the start"* — you must already be at the schedule's opening mileage → `needs_base_phase`.

### Intake synthesis — what these chapters say we should ask

(Field-by-field matrix lives in [`docs/intake-and-engine.md`](../intake-and-engine.md); this is the *why*.)

- **Current weekly mileage + longest recent run** — gates program choice and week 1 (Daniels "6 weeks under your belt", Pfitzinger "challenging from the start"). Feeds `w_now` / `p_history`.
- **Recent time off / injury** — Daniels ch.15 layoff categories; should lower the start and add a base phase.
- **Days/week available + life constraints** — Daniels "opportunity"; drives `assign_method` and the day template.
- **Goal time, goal race date, secondary races** — Pfitzinger ch.12 multiple marathoning → `goal_marathon_s`, `race_date`, `secondary_races`.
- **Recent race result (a half is ideal)** — Daniels ch.5 + ch.13 → `vdot`.
- **Experience / motivation** — Daniels ch.1 → beginner-vs-advanced framing.

---

## The two long runs (steady endurance vs. marathon-specific)

This is the distinction the engine partially collapses. **Both authors separate a general endurance long run from a marathon-pace long run, and cap them differently.**

### Daniels: `L` run vs. `M` run are *different sessions*

- **`L` run (easy/steady long run)** — run at **E pace**, capped at the *lesser* of a percent-of-week share or **150 min**, and this cap holds **even when training for a marathon**:

  > "I also suggest that your longest steady run (unless preparing for some ultra events) be 150 minutes (2.5 hours), even if preparing for a marathon." — *Daniels p.63*

  > "limit any single L run to 30 percent of weekly mileage for runners who are totaling fewer than 40 miles … For those who are accumulating 40 or more miles per week, I suggest L runs be the lesser of 25 percent of weekly mileage or 150 minutes, whichever comes first." — *Daniels p.64*

- **`M` run (marathon-pace run)** — a **separate** marathon-specific session at goal MP, with its own, *tighter* cap:

  > "in addition to any L run, I also suggest limiting an M run to the lesser of 110 minutes or 18 miles (29 km), whichever comes first … M-pace running, in a single session of training, [should] not add up to more than the lesser of 20 percent of your weekly mileage or 18 miles, whichever [is less]." — *Daniels p.65*

  The intensity-type box on *Daniels p.62* states both ceilings together: **E = "30-150 min … 25-30% weekly miles"**, **M = "40-110 min; practice pace"**.

  Takeaway: Daniels does **not** grow the easy long run past 2.5 h for marathoners. The marathon-specific stimulus comes from M-pace work capped at **110 min / 18 mi / 20% week** — he is explicitly skeptical of monster easy long runs (*p.64-65*).

  **But note the program reality (ch.14):** the ch.4 caps describe the M run "*in addition to any L run*," yet Daniels' actual **2Q program blends them into one nonstop Q1 session** — e.g. *"Q1 = 3 E + 4 M + 1 T + 1 M + 2 E (nonstop workout if no rest shown)"* (Table 14.3, p.233) — consistent with p.65: *"I also like to mix M-pace running with both E- and T- (threshold) pace running."* So a single session legitimately combines E + M + T; the engine's blended `mp_long_run` follows this, not a strict L/M day split.

### Pfitzinger: long run vs. medium-long run vs. MP run — three categories, **no time cap**

  > "In the training schedules, a long run is any run of 16 miles (26 km) or longer … The most beneficial intensity range for most of your long runs is 10 to 20 percent slower than your goal marathon race pace … run the last 5 to 10 miles … at about 10 percent slower than your goal marathon race pace. The schedules also include marathon-specific long runs at goal marathon race pace." — *Pfitzinger p.257*

  > "A medium-long run is any run of 11 to 15 miles (18 to 24 km)." — *Pfitzinger p.259*

  > "long runs greater than 22 miles (35 km) take much more out of the body than do runs in the range of 20 to 22 miles." — *Pfitzinger p.43*

  Pfitzinger caps the long run by **distance (build to 20-22 mi, avoid >22)**, not by time, and prescribes it **10-20% slower than MP finishing near MP** — not pure easy pace.

### Who actually caps the long run by *time*, and who by *distance*

Be precise here — the four authors do **not** all use a time cap:

| Author | Long-run limit | Type | Cite |
|--------|----------------|------|------|
| **Daniels** | 150 min (2.5 h) | **time cap** | p.63 |
| **Hanson** | 2–3 h, "beyond → muscle breakdown" | **time cap/window** | p.66 |
| **Pfitzinger** | 20–22 mi (avoid >22); 90 min is a *floor* for benefit | **distance cap** | p.43, p.42 |
| **Higdon** | 20 mi | **distance cap** | p.28, 106 |

So the muscle-breakdown **time ceiling is a Daniels + Hanson position**. Pfitzinger and Higdon cap by **distance** and state no time cap. But their *rationale* converts cleanly to time and supports the same idea:

  > "The research tells us that **2:00–3:00 hours is the optimal window** … Beyond that, muscle breakdown begins to occur. … anyone planning on running slower than a 9:00-minute pace should avoid the 20-mile trek." — *Hanson p.66-67*

  > "it is only after about **2 hours of running—or about 20 miles for an accomplished runner**—that the body begins to fully deplete its stores of glycogen." — *Higdon p.27*

Higdon's "2 h ≈ 20 mi *for an accomplished runner*" is the tell: the real dose is **time**, and 20 mi only equals ~2–3 h at ~7:30–9:00/mi. **z2tc adopts the Daniels/Hanson time ceiling** (`LONG_RUN_WINDOW_MIN`, 3 h upper bound), so a slower runner's 16-miler earns the same time-on-feet credit as a faster runner's 20 — and a sub-9:00/mi runner isn't pushed to a counterproductive 3:40 long run. The 1/3-of-week supported bound and Daniels' 150-min anchor still gate the *prescription*; the window sets the productive ceiling. The pure-Higdon reference engine deliberately keeps the **distance** cap and applies no time lens at all (the divergence shows up in the [single-author fidelity audit](plan-engine.md), not as an in-engine flag). Citations: `engine/plan/citations.py` (`book_search.py cite long-run`); each plan carries the rationale in `TrainingPlan.notes`.

---

## Constant-by-constant audit of `engine/plan/common.py`

| Code | Value | Status | Source / note |
|------|-------|--------|---------------|
| `LONG_RUN_CAP_MIN = 150` | 150 min | **verbatim** | Daniels p.63-64 ("150 minutes (2.5 hours), even if preparing for a marathon"). Conservative/literal anchor; still drives the volume-too-low flag. |
| `LONG_RUN_WINDOW_MIN = (120, 180)` | 2-3 h | **verbatim** | Hanson p.66 ("2:00–3:00 hours is the optimal window … beyond that, muscle breakdown"). The 3 h upper bound is the marathon-build time ceiling. |
| `daniels_long_run` `share_pct` | 0.30 (<40 mpw), 0.25 (≥40) | **verbatim** | Daniels p.64 (30% under 40 mi; 25%-or-150-min over 40 mi). |
| `daniels_long_run` `marathon_build` branch | `min(3 h window cap, 18 mi, max(share, ⅓ week))` | **house rule (synthesis)** | z2tc targets Hanson's 2-3 h window rather than Daniels' conservative 150 min, so slower runners get full time-on-feet credit (e.g. 11:00/mi → ~16 mi not ~13.6). Daniels' literal rule is `min(150-min, 18, share)` (the `marathon_build=False` branch). |
| `session_caps["M"]` = `min(18, 0.20·wk, 110min)` | 18 mi / 20% / 110 min | **verbatim** *(fixed)* | Daniels p.62 ("40-110 min … 15-20% weekly miles") + p.65 ("lesser of 110 minutes or 18 miles … 20 percent of your weekly mileage"). The old 0.30-below-40-mpw branch and the missing 110-min ceiling were fixed; `mp_s` now threads in so the minute cap binds for slower runners. |
| `session_caps["T"]` | `min(10% week, 15 mi)` | **verbatim** | Daniels p.62 fig. 4.1 ("10% weekly miles"). The 15-mi absolute is a house guard (binds only above ~150 mpw). |
| `session_caps["I"]` | `min(8% week, 10K)` | **verbatim** | Daniels p.62 fig. 4.1 ("Lesser of 10k and 8% weekly miles"). |
| `session_caps["R"]` | `min(5% week, 5 mi)` | **verbatim** | Daniels p.62 fig. 4.1 ("Lesser of 5 miles and 5% weekly miles"). |
| `pfitzinger_long_run` 16 → 20-22, no time cap | base 16, peak 20 | **verbatim** | Pfitzinger p.257 (≥16 mi), p.43 (20-22, avoid >22). Peak default 20 is conservative within the band. |
| `medium_long_run` band (generator `min(15, max(11, …))`) | 11-15 mi | **verbatim** | Pfitzinger p.259 ("11 to 15 miles"). |
| `mp_long_run` (long run with MP finish) | block = `min(capM, max(2, 40% total))` | **house rule** | Neither author prescribes this exact single-session blend. Daniels keeps L and M as *separate days*; Pfitzinger lists "marathon-pace runs" as a distinct category (p.256). Defensible synthesis, but flag it. |
| `_taper_fracs` 3-wk | 0.80 / 0.62 / 0.45 | **approx** | Pfitzinger p.225: −20-25% / −40% / −60% (≈ 0.78 / 0.60 / 0.40). Engine race-week 0.45 runs slightly hotter than Pfitzinger's 0.40. |
| `recovery_days_after_race` | 1 day / 3000 m | **needs cite** | Rule-of-thumb; locate the Daniels passage (or relabel as house heuristic). |
| `peak_mileage = max(p_history, w_now)` | — | **house rule** | Injury-safe determinism choice; not a book formula. |
| `weekly_volumes` ramp | hold ~3 wk, +`min(days,10)` mi, recovery wk every 4th | **verbatim** | Daniels p.219 (printed 205): *"increasing weekly mileage about every 4th week … by 1 mile for every running session … don't increase by more than 10 miles"*; recovery week = Pfitzinger ch.3. Replaced the old every-week increment. |
| `weekly_volumes` taper base | off **achieved** peak, not P | **house rule** | Taper from the volume actually reached, so an unreached P doesn't inflate the taper. |
| `volume_step_ups` + VO2max defer | `I`→`T` on step-up weeks | **derived** | Daniels p.36 (Accelerating Setbacks) + Pfitzinger ch.3 (hard/easy): don't add hard VO2max on a mileage-jump week. |
| `vdot.predict_race_time` / `race_equivalent_times` | inverse of `vdot_from_race` | **verbatim** | Daniels VDOT equivalence (Table 5.1); validated to within seconds of the printed VDOT-50 row. |

---

## How each cap is leveraged (per-bout vs. per-session vs. warm-up/cool-down)

The p.62 box mixes two different limits per row — a **per-bout** duration and a **per-session total** — and warm-up/cool-down sit *outside* both. How the engine reads each:

| Type | Per-bout limit (duration column) | Per-session total (% column) | Recovery (W:R) | Engine |
|------|----------------------------------|------------------------------|----------------|--------|
| **T** | steady tempo ≈ **20 min**; cruise-interval bout 5-20 min (p.67) | ≤ **10% week** total at T pace (p.68) | 5:1 | `threshold_workout`: single tempo while work ≤ 20-min-equivalent, else **cruise intervals** (~1-mi reps, 60 s jog). wu/cd = `+3 mi`, outside the cap. |
| **M** | marathon-pace run **40-110 min** (p.62) | ≤ lesser of **18 mi / 20% week / 110 min** (p.65) | — | `session_caps["M"]` = `min(18, 0.20·wk, 110min)`; consumed as the MP finishing block of the long run. |
| **I** | each rep **≤ 5 min** hard (≈1000-1200 m) | ≤ lesser of **10K / 8% week** (p.62) | 1:1 (equal-time jog) | `interval_workout`: `n × 1000 m`, equal-time jog — matches per-rep + total + 1:1. |
| **R** | each rep **≤ 2 min** fast (≈200-400 m) | ≤ lesser of **5 mi / 5% week** (p.62) | 1:2-3 | Defined in `session_caps` but **not used** in the marathon generators (R is for shorter-race training, Daniels ch.9-12). |
| **E/L** | longest steady run ≤ **150 min** (p.63) | ≤ **25-30% week** (p.64) | — | `daniels_long_run` (easy long run); MP work is a *separate* session. |

**Key reading of your question:** for T, "20 min" is the **work in one continuous tempo bout** (not the whole workout, and not the session total). Warm-up/cool-down are extra. To accumulate more threshold work you switch to **cruise intervals** up to the **10%-of-week** session total — you don't run a longer continuous tempo. The engine now does exactly this.

## Open divergences to resolve

1. ~~**`M` session cap uses 30% under 40 mpw**~~ — **FIXED.** `session_caps["M"]` is now a flat 20% (Daniels p.62/p.65).
2. ~~**No 110-min ceiling on the MP block**~~ — **FIXED.** `session_caps(weekly, mp_s)` now also caps M at the 110-min M-pace ceiling (`LONG_RUN_CAP_MIN_M`), threaded through both generators.
3. ~~**Threshold prescribed as one continuous tempo up to 10% of the week**~~ — **FIXED.** `threshold_workout` now emits a steady tempo only while the T work fits in ~20 min (`TEMPO_MAX_MIN`), and switches to cruise intervals beyond that (Daniels p.67-68).
4. ~~**Pfitzinger long run forced up to a 16-mi floor**~~ — **FIXED (floor removed).** p.257's "a long run is any run of 16 miles or longer" is a *labeling definition* inside his 55–100 mpw schedules, not a floor — his ≤55 schedule opens with ~12-mi long runs (p.285). The ladder now starts ~12 mi and climbs by distance toward 20–22; it is no longer clamped up to 16.
5. ~~**`mp_long_run` conflates Daniels' `L` and `M` days**~~ — **RESOLVED + ENHANCED.** Daniels' 2Q program (Table 14.3, p.233-234) blends E + M + T into one nonstop Q1, so the blend was already faithful. The Daniels generator now emits a **multi-segment Q1** (`marathon_q1_workout`: `E → M → T → M → E`), e.g. `2.5 E + 4.2 M + 1 T + 1 M + 1.6 E`. (Pfitzinger keeps the simpler `mp_long_run` single-MP-block form, faithful to his ch.7.)
6. **Daniels long-run length** — *partially fixed.*
   - ~~Overshoots at high mileage~~ — **FIXED.** Added `LONG_RUN_CAP_MI = 18` (Table 14.3, p.237 *"lesser of 18 miles and 130 min"*); `daniels_long_run` is now `min(150-min, 18 mi, max(share, ⅓ week))`, so 68 mpw → 18.0 (was 19.1). Low/mid volume unchanged (31 → 10.3, 50 → 16.7).
   - **Open (deferred to the ch.14 audit):** Daniels holds Q1 length **near its cap and scales the *week* via the "fraction of peak" column + E days**, whereas the engine scales length with the *current week's share* — the root cause of the absurdly short early-week long runs. Reworking length to track peak (not the current week) is structural and depends on the full Table 14.3 / fraction-of-peak model; handle it in the chapter-14 ledger pass.
7. ~~**`weekly_volumes` increments every week**~~ — **FIXED.** The ramp now **holds ~3 weeks then steps up** by `min(days, 10)` mi with a recovery week every 4th (Daniels p.219 + Pfitzinger ch.3), instead of adding mileage every week. A build that can't reach an aggressive `P` inside the block is **flagged** (`peak not reached`) rather than over-ramped. The coach-facing **re-entry start**, **recommended P**, **goal feasibility**, **race-time prediction**, and **Table 15.1 break** model now live in [`engine/readiness.py`](../../engine/readiness.py) (see [athlete-readiness.md §10-12](athlete-readiness.md)).

## See also

- [plan-engine.md](plan-engine.md) — structural map of the generators.
- [`scripts/book_search.py`](../../scripts/book_search.py) — the citation tool used to build this doc.
