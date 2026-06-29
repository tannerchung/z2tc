# z2tc docs — table of contents

Index of every doc, what it **owns** (the canonical home for that topic), and what it links
out to. Read this first to find the right doc and to **avoid duplicating** material that
already has a home elsewhere. Anti-duplication is a project convention (see `CLAUDE.md`): when
a topic has an owner below, link it — don't re-explain it.

## Start here

- [`../CLAUDE.md`](../CLAUDE.md) — agent/contributor map: scope, important files, `output/`
  layout, conventions. **Read order starts here.**
- [`architecture/overview.md`](architecture/overview.md) — the layer + data-flow map (CLI →
  feeds → analysis → plan engine → store → render). Owns: *how the pieces connect*.

## The model (how athlete data becomes a plan)

| Doc | Owns (canonical) | Don't duplicate elsewhere |
|-----|------------------|---------------------------|
| [`architecture/athlete-readiness.md`](architecture/athlete-readiness.md) | The **decision/reasoning layer**: two clocks (fitness vs volume), freshness + Table 15.1 breaks, re-entry start, recommended P/tier, **goal realism** (§10), **volume-vs-VO2max balance** (§11), the `engine/readiness.py` map (§12), Kelly worked example. | Coaching judgement, break math, goal-feasibility logic. |
| [`architecture/formula-reference.md`](architecture/formula-reference.md) | **Book provenance** for every constant in `engine/plan/common.py` (verbatim / house rule / divergence), the two book tables of contents, and the citation tool. | Page-cited constants; the L-vs-M long-run distinction. |
| [`architecture/plan-engine.md`](architecture/plan-engine.md) | **Structural map** of the generators (Daniels 2Q + Pfitzinger), phases, week assembly. | Generator structure / phase boundaries. |
| [`architecture/workout-catalog.md`](architecture/workout-catalog.md) | The **workout dictionary**: every catalog session (`engine/plan/workouts.py`) with its definition, how the engine sizes/paces it, and the Q1/Q2 rotation per phase. | What each workout is; how it's generated; rotation. |
| [`architecture/event-sourcing.md`](architecture/event-sourcing.md) | The **event log + replan fold** contract. | Event vocabulary, replan semantics. |
| [`architecture/interpretation-layer.md`](architecture/interpretation-layer.md) | The **interpretation & coaching layer** (design): data-selection directives, race-condition adjustments, the NL→structured boundary, live-monitor signals, coach briefs. | How coach/LLM input is applied deterministically; staging. |
| [`architecture/feeds-and-analysis.md`](architecture/feeds-and-analysis.md) | **Scraping, `analyze`, `marathon-report`** behavior. | Strava feed + analysis pipeline. |
| [`architecture/date-normalization-phase7.md`](architecture/date-normalization-phase7.md) | **Phase 7 policy snapshot:** extraction-only deterministic calendar rewrites (`extract_events`); locked decisions; pointer to code + tests. Narrative + semantics: [`architecture/event-sourcing.md`](architecture/event-sourcing.md). | |

## Intake (form → engine)

| Doc | Owns (canonical) |
|-----|------------------|
| [`intake-and-engine.md`](intake-and-engine.md) | The **field-by-field intake matrix** → `AthleteInputs` contract (the *one* place the full field list lives). |
| [`intake-google-form.md`](intake-google-form.md) | Google Form / Sheets **operations** (OAuth, tabs, scripts). |

## Tutorials (learning, narrative)

| Doc | Owns (canonical) |
|-----|------------------|
| [`tutorials/e2e-walkthrough.md`](tutorials/e2e-walkthrough.md) | **Hands-on end-to-end walkthrough** for a first-time operator: the input model (survey/events/feeds), running `build-plan` → `replan` → `review` → `monitor` one step at a time with verify/pause points, and how to read the results at each layer. Links out for canonical depth; does not re-own the intake matrix or event vocabulary. |

## Cheatsheets (reference, not narrative)

| Doc | Owns (canonical) |
|-----|------------------|
| [`cheatsheets/01 - CLI Quick Reference.md`](cheatsheets/01%20-%20CLI%20Quick%20Reference.md) | **CLI flag tables** for `main.py` + `bin/` + scripts. |
| [`cheatsheets/08 - Schemas & Config Reference.md`](cheatsheets/08%20-%20Schemas%20&%20Config%20Reference.md) | **Schema/config** field reference. |
| [`design/plan-sheet-layout.md`](design/plan-sheet-layout.md) | **Plan tab layout & club workbook styling** for `publish-sheet`. |

## Citing the books

Both source PDFs (Daniels 3rd ed., Pfitzinger 2nd ed.) live in the repo. Reproduce any page
quote with [`../scripts/book_search.py`](../scripts/book_search.py) — never quote from memory.
The page-number offset (PDF index vs printed page) is documented in
[`architecture/formula-reference.md`](architecture/formula-reference.md).

## Verifying doc references

After renaming or adding a first-class module, run [`../bin/check-doc-refs`](../bin/check-doc-refs)
to confirm no doc cites a path that no longer exists.
