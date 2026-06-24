"""Decode plan workout labels into coach-readable explanations (deterministic)."""

from __future__ import annotations

import re

from engine.plan.models import WorkoutKind, QUALITY_KINDS

PACE_LEGEND: dict[str, str] = {
    "E": "Easy — conversational aerobic (Daniels E zone; see paces table above).",
    "M": "Marathon pace — goal-race pace (from A-goal time), not VDOT marathon pace.",
    "T": "Threshold / tempo — comfortably hard (~hour-race effort; Daniels T).",
    "I": "Interval — VO2max reps (Daniels I; equal-time jog recoveries).",
    "R": "Repetition — short fast reps with full recovery (Daniels R).",
}

STATIC_GLOSSARY: list[tuple[str, str]] = [
    ("Q1", "Daniels 2-Quality week: first quality session — usually Saturday long run blending E/M/(T)/M/E."),
    ("Q2", "Daniels 2-Quality week: second quality session — threshold or VO2max mid-week."),
    ("warm-up / cool-down", "Easy running before and after the main set (typically 1.5 mi each)."),
    ("strides (ST)", "6 x ~20 sec light, quick pickups (not sprints), ~60 s jog between — economy work on easy days (Daniels)."),
    ("nonstop", "One continuous run — do not stop between segments; change pace on the clock."),
    ("MP", "Marathon pace — same as M (goal-race pace)."),
    ("Easy", "Recovery / aerobic day — stay inside the Easy pace range."),
    ("Rest", "No run (or optional very easy cross-training if coach agrees)."),
    ("Cross", "Non-running aerobic session; does not count toward run mileage."),
]


# All nonstop blend-style long runs share the "... (nonstop): <parts> (M @ x:xx/mi)" shape:
# the Daniels E/M/T blend, marathon-pace blocks, thirds progression, and the fast finish.
_BLEND_RE = re.compile(
    r"^(?P<name>Marathon long run|Marathon-pace blocks|Progression long run|Fast-finish long run|Race-practice long run) "
    r"(?P<total>[\d.]+) mi \(nonstop\): (?P<blend>.+?) \(M @ (?P<mp>[\d:]+)/mi\)$"
)
_BLEND_INTRO = {
    "Marathon long run": "Marathon long run (Daniels 2Q): a single nonstop run blending easy, marathon-pace and a short threshold surge",
    "Marathon-pace blocks": "Marathon-pace blocks: a long run with two marathon-pace blocks split by an easy float (race rhythm + fueling rehearsal)",
    "Progression long run": "Progression long run: one nonstop run that builds easy → steady → marathon pace (pacing discipline, strong finish)",
    "Fast-finish long run": "Fast-finish long run: mostly easy, then a controlled marathon-pace close (late-race grit)",
    "Race-practice long run": "Race-practice long run (dress rehearsal): one sustained marathon-pace block — practice goal pace, fueling and kit (Pfitzinger; Runna)",
}
_TEMPO_RE = re.compile(r"^Tempo run:")
_CRUISE_RE = re.compile(r"^Cruise intervals:")
_OVERUNDER_RE = re.compile(r"^Over/unders:")
_TLADDER_RE = re.compile(r"^Threshold ladder:")
_VO2_LADDER_RE = re.compile(r"^VO2max pyramid:")
_VO2_DESC_RE = re.compile(r"^Descending intervals:")
_DROPSET_RE = re.compile(r"^Drop set:")
_VO2_RE = re.compile(r"^VO2max intervals:")
_ROLLING_RE = re.compile(r"^Rolling 400s:")
_REPS_RE = re.compile(r"^Speed reps:")
_MPREPS_RE = re.compile(r"^Race-pace reps:")
_LR_FARTLEK_RE = re.compile(r"^Long run w/ fartlek (?P<mi>[\d.]+) mi")
_LR_EASY_RE = re.compile(r"^Long run (?P<mi>[\d.]+) mi @ Easy")
_LR_MP_RE = re.compile(r"^Long run (?P<mi>[\d.]+) mi w/ (?P<blk>[\d.]+) mi @ MP")
_MLR_RE = re.compile(r"^Medium-long run (?P<mi>[\d.]+) mi")


def explain_workout_label(label: str) -> str:
    """Return a plain-language reading of a workout cell label."""
    text = (label or "").replace("\n", " ").strip()
    if not text:
        return ""

    m = _BLEND_RE.match(text)
    if m:
        names = {"E": "easy", "M": "marathon pace", "T": "threshold", "steady": "steady (between easy and MP)"}
        parts = []
        for chunk in m.group("blend").split(" + "):
            chunk = chunk.strip()
            if not chunk:
                continue
            miles, abbr = chunk.rsplit(" ", 1)
            parts.append(f"{miles} mi {names.get(abbr, abbr)}")
        intro = _BLEND_INTRO.get(m.group("name"), m.group("name"))
        return (
            f"{intro} — {m.group('total')} mi continuous: "
            + " → ".join(parts)
            + f". Marathon-pace segments use goal pace {m.group('mp')}/mi."
        )

    if _TEMPO_RE.match(text):
        return (
            "Threshold tempo (Daniels T): one continuous comfortably-hard effort at threshold pace, "
            "bracketed by a 1.5 mi easy warm-up and 1.5 mi easy cool-down."
        )
    if _CRUISE_RE.match(text):
        return (
            "Threshold cruise intervals (Daniels T): threshold-pace repeats with short 60 s jogs "
            "(same comfortably-hard effort, broken up), plus a 1.5 mi easy warm-up and cool-down."
        )
    if _OVERUNDER_RE.match(text):
        return (
            "Over/unders (threshold): alternate 0.5 mi at threshold (the \"over\") with 0.5 mi at "
            "marathon pace (the \"under\"), nonstop — the same lactate-clearance work as cruise "
            "intervals, but floating to MP instead of jogging trains pace changes at race-adjacent "
            "efforts. Bracketed by a 1.5 mi easy warm-up and cool-down."
        )
    if _TLADDER_RE.match(text):
        return (
            "Threshold ladder (Runna 'Tempo 2-1-1'): descending threshold blocks (one long, then "
            "shorter) at comfortably-hard threshold pace with 60 s jogs between — same T effort as "
            "cruise intervals, varied shape. Includes a 1.5 mi easy warm-up and cool-down."
        )
    if _VO2_DESC_RE.match(text):
        return (
            "VO2max descending intervals (Daniels I): a 1200-1000-800-600-400 m set at ~5K effort "
            "with equal-time jog recoveries — the shortening reps keep pace honest as fatigue "
            "builds. Includes a 1.5 mi easy warm-up and cool-down."
        )
    if _DROPSET_RE.match(text):
        return (
            "VO2max drop set (Runna): a single 1000-800-600-400-200 m descending ladder at ~5K "
            "effort with equal-time jog recoveries — short and sharp, finishing fast on tired legs. "
            "Includes a 1.5 mi easy warm-up and cool-down."
        )
    if _VO2_LADDER_RE.match(text):
        return (
            "VO2max pyramid (Daniels I): a 400-800-1200-800-400 m pyramid at ~5K effort with "
            "equal-time jog recoveries, plus a 1.5 mi easy warm-up and cool-down. Same VO2max "
            "stimulus as straight intervals, but the changing rep length keeps it fresh."
        )
    if _VO2_RE.match(text):
        return (
            "VO2max intervals (Daniels I): hard reps at ~5K effort with equal-time jog recovery, "
            "plus a 1.5 mi easy warm-up and cool-down."
        )
    if _ROLLING_RE.match(text):
        return (
            "Rolling 400s (Runna): 400 m reps at Rep pace (~mile race pace) with only a short 200 m "
            "jog float between — a continuous, rhythm-focused turnover set (less recovery than full "
            "speed reps). Includes a 1.5 mi easy warm-up and cool-down."
        )
    if _REPS_RE.match(text):
        return (
            "Speed reps (Daniels R = Repetition pace, roughly mile race pace): short, fast reps "
            "(400 m, or 200 m for pure turnover) with a full jog recovery — for speed and running "
            "economy, not lactate tolerance. Includes a 1.5 mi easy warm-up and cool-down."
        )
    if _MPREPS_RE.match(text):
        return (
            "Race-pace reps (Runna 'Race Pace Practice Half Miles'): short half-mile reps at goal "
            "marathon pace with a 60 s jog — a low-fatigue way to rehearse race rhythm, ideal in the "
            "taper and race week. Includes a 1.5 mi easy warm-up and cool-down."
        )

    m = _LR_FARTLEK_RE.match(text)
    if m:
        return (
            f"Aerobic long run {m.group('mi')} mi with light fartlek surges (~1 min, ~10K effort) "
            "sprinkled in — stays an easy long-run day; the surges just break it up and add a touch "
            "of turnover (Humphrey)."
        )

    m = _LR_MP_RE.match(text)
    if m:
        return (
            f"Long run {m.group('mi')} mi with the final {m.group('blk')} mi at goal marathon pace "
            "(quality long run)."
        )
    m = _LR_EASY_RE.match(text)
    if m:
        return f"Aerobic long run {m.group('mi')} mi — stay Easy throughout."

    m = _MLR_RE.match(text)
    if m:
        return f"Medium-long run {m.group('mi')} mi — aerobic, slightly shorter than the weekly long."

    if "strides" in text.lower():
        return (
            "Easy aerobic run with strides: after the easy miles, add 6 x ~20 sec light, quick "
            "pickups (NOT sprints) with ~60 s easy jog between each (Daniels ST). The run stays an "
            "easy day — the strides just sharpen turnover and economy."
        )
    if text.lower().startswith("easy"):
        return "Easy aerobic run — conversational effort inside the Easy pace range."
    if text.lower() == "rest":
        return "Rest day — no prescribed run."

    return text


def kind_highlight(kind: WorkoutKind) -> str:
    """Cell highlight bucket for sheet formatting."""
    if kind in (WorkoutKind.REST, WorkoutKind.CROSS):
        return "rest"
    if kind in (WorkoutKind.LONG, WorkoutKind.MEDIUM_LONG):
        return "long"
    if kind in QUALITY_KINDS:
        return "quality"
    return "easy"
