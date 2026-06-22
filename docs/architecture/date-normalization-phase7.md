# Phase 7 — date normalization (policy)

Canonical behavior and narrative live in [Event sourcing — LLM and coach approval](event-sourcing.md). This page records **only** the locked decisions.

## Decisions

1. **Where normalization runs:** **`extract_events` only** (`llm/boundary.py`), after payloads parse and before `_apply_date_flags`. It does **not** run at `review` (no silent SQLite row rewrites when the coach reads proposals).

2. **What gets rewritten:** Only fields returned by `_payload_date_fields` (grounded LLM/coach kinds). Monitor-generated payloads are out of scope.

3. **Determinism:** Same `(today, race_date, block_weeks, raw_payload)` always yields the same normalized ISO strings (same month-day preference, same clamp, same Monday tie-break).

4. **Coach visibility:** Each rewrite emits **`Date normalized …`** to **stderr** with `was` / `now`. **`review`** continues to print **`!! date warning`** for rows still out of window after extraction (e.g. legacy DB rows, or unparseable values left unchanged).

## Implementation

- `llm/boundary.py` — `normalize_payload_calendar_dates`, `_normalize_proposed_records`, `_resolve_calendar_date_into_window`, `_mondays_in_window`.
- `tests/test_boundary.py` — normalization + `extract_events` stub coverage.
