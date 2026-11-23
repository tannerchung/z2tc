# Deterministic Biomechanics Engine, Side-by-Side Co-Run Coaching Signal, and Canonical Drill & Telemetry Detector Catalog (`detour-engine` + `detour-web`)

## Goal
Replace any reliance on per-run LLM calls for biomechanical analysis with **100% deterministic Python telemetry detectors**, elevate **Coach Tanner's In-Person Saturday Co-Run Observations (physical gait + breathing + mental well-being)** into a first-class coaching input, and establish a **Single Canonical Registry** for all **Endurance Running Drills, Strength Prescriptions, Telemetry Detectors, and 23 Running Workouts** across `detour-engine` and `detour-web`.

---

## Summary of Answers & Architecture

1. **Deterministic Biomechanics (`0` LLM Calls Required):**
   - All 10 biomechanical & physiological detectors (`TELEMETRY_DETECTORS`) run in pure Python (`<10 ms`) over Strava 1 Hz streams, Garmin `.FIT` running dynamics (`GCT ms`, `Stride Length cm`, `Vertical Ratio %`, `L/R GCT Balance %`), official race curves, and a deterministic Strava-note keyword lexicon:
     - `det_grey_zone_easy_drift` (`easy_low_s - actual_pace_s >= 20`)
     - `det_gct_elastic_sink` (`avg_gct_ms >= 255` or `late_run_gct_delta_ms >= 10`)
     - `det_late_stride_collapse` (`late_stride_length_cm < 120` or `stride_drop_pct >= 8%`)
     - `det_vertical_bounce_waste` (`avg_vertical_ratio_pct > 8.0`)
     - `det_cadence_overstride` (`avg_cadence_spm < 166` or `late_run_cadence_delta_spm <= -5`)
     - `det_aerobic_cardiac_drift` (`pa_hr_decoupling_pct > 5.0` or `pw_hr_decoupling_pct > 5.0`)
     - `det_glycogen_power_fade` (`final_3mi_pace_drop_pct >= 8.0` and `hr_delta <= 0`)
     - `det_lr_asymmetric_guarding` (`abs(gct_balance_left_pct - 50.0) >= 1.5` or unilateral pain keyword)
     - `det_vdot_endurance_gap` (`vdot_10k_or_half - vdot_marathon >= 3.5`)
     - `det_dead_foam_shoe_mileage` (`daily_trainer_miles >= 350` or `carbon_racer_miles >= 160`)
2. **In-Person Saturday Side-by-Side Co-Run Signal (`CO_RUN_OBSERVATION_CUES`):**
   - Captures what only an in-person coach running beside the athlete can see across **3 quick-tap dimensions**:
     - **Breathing / Talk-Test Beside Me** (`Full Sentences` vs. `Clipped on Bridges`)
     - **Visual Gait & Posture Cues** (`Tall & Quiet` vs. `Loud Foot-Slap Late` vs. `Shortened Shuffle` vs. `Tight Shoulders`)
     - **Mental & Life Well-Being** (`Energized by Pack` vs. `Mentally Drained from Work Stress`)
   - Deterministically maps your Saturday observation to next week's midweek workout (`Mona Fartlek` vs. `Broken-T` vs. `Over/Unders`), her 2x8-min drills, and your Sunday Week-Unlock note!
3. **Where All Drills, Detectors & Workouts Are Cataloged (Single Source of Truth):**
   - Canonical Python registries in `detour-engine` (`engine/pace_calibration.py` + `engine/plan/workouts.py`) auto-export to:
     - `detour-web/public/data/engine-prototype-bundle.json` (rendered as an interactive **📚 Coaching Codex Tab** inside `/training.html`), and
     - `detour-engine/docs/coaching-drills-and-detectors-codex.md` (auto-generated markdown reference so code, UI, and Hermes skills never drift).

(Full tables, schemas, and TDD steps `Tasks 0.1–0.3` are in `/Users/tanner/.hermes/plans/2026-11-16_123156-detour-deterministic-biomech-side-by-side-coaching-and-drill-catalog.md`.)
