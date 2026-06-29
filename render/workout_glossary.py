"""Decode plan workout labels into coach-readable explanations (deterministic)."""

from __future__ import annotations

import re

from engine.plan.models import WorkoutKind, QUALITY_KINDS

PACE_LEGEND: dict[str, str] = {
    "E": "Easy, conversational aerobic running (Daniels E zone; see the paces table above).",
    "M": "Marathon pace, your goal-race pace (from the A-goal time) rather than VDOT marathon pace.",
    "T": "Threshold or tempo, comfortably hard at about hour-race effort (Daniels T).",
    "I": "Interval, VO2max reps with equal-time jog recoveries (Daniels I).",
    "R": "Repetition, short fast reps with full recovery (Daniels R).",
}

STATIC_GLOSSARY: list[tuple[str, str]] = [
    ("Q1", "The first quality session of a Daniels 2-Quality week, usually the Saturday long run blending E/M/(T)/M/E."),
    ("Q2", "The second quality session of a Daniels 2-Quality week, a threshold or VO2max effort mid-week."),
    ("warm-up / cool-down", "Easy running before and after the main set (typically 1.5 mi each)."),
    ("strides (ST)", "6 x about 20 sec light, quick pickups (not sprints) with about 60 s jog between, for economy work on easy days (Daniels)."),
    ("nonstop", "One continuous run with no stopping between segments. Change pace on the clock."),
    ("MP", "Marathon pace, the same as M (your goal-race pace)."),
    ("Easy", "A recovery or aerobic day. Stay inside the Easy pace range."),
    ("Rest", "No run (or optional very easy cross-training if your coach agrees)."),
    ("Cross", "A non-running aerobic session that does not count toward run mileage."),
    ("Tempo (terminology)", "Watch the word. In Daniels a 'tempo' is THRESHOLD pace (comfortably hard), "
                            "while in the Hansons method a 'tempo' is goal MARATHON pace. Your sheet labels which one."),
    ("General aerobic", "A Pfitzinger term for steady everyday aerobic mileage, a notch above recovery pace."),
    ("Recovery run", "A Pfitzinger term for deliberately slow easy running to recover between hard days."),
    ("Strength", "A Hansons SOS session of long reps slightly faster than goal marathon pace (about MP minus 10s/mi) for fatigue resistance."),
]


# All nonstop blend-style long runs share the "... (nonstop): <parts> (M @ x:xx/mi)" shape:
# the Daniels E/M/T blend, marathon-pace blocks, thirds progression, and the fast finish.
_BLEND_RE = re.compile(
    r"^(?P<name>Marathon long run|Marathon-pace blocks|Progression long run|Fast-finish long run|Race-practice long run) "
    r"(?P<total>[\d.]+) mi \(nonstop\): (?P<blend>.+?) \(M @ (?P<mp>[\d:]+)/mi\)$"
)
_BLEND_INTRO = {
    "Marathon long run": "Marathon long run (Daniels 2Q), a single nonstop run blending easy, marathon-pace and a short threshold surge",
    "Marathon-pace blocks": "Marathon-pace blocks, a long run with two marathon-pace blocks split by an easy float for race rhythm and fueling rehearsal",
    "Progression long run": "Progression long run, one nonstop run that builds from easy to steady to marathon pace for pacing discipline and a strong finish",
    "Fast-finish long run": "Fast-finish long run, mostly easy then a controlled marathon-pace close for late-race grit",
    "Race-practice long run": "Race-practice long run (the dress rehearsal), one sustained marathon-pace block to practice goal pace, fueling and kit (Pfitzinger; Runna)",
}
_TEMPO_RE = re.compile(r"^Tempo run:")
_CRUISE_RE = re.compile(r"^Cruise intervals:")
_BROKENT_RE = re.compile(r"^Broken-T intervals:")
_OVERUNDER_RE = re.compile(r"^Over/unders:")
_TLADDER_RE = re.compile(r"^Threshold ladder:")
_VO2_LADDER_RE = re.compile(r"^VO2max pyramid:")
_VO2_DESC_RE = re.compile(r"^Descending intervals:")
_DROPSET_RE = re.compile(r"^Drop set:")
_VO2_RE = re.compile(r"^VO2max intervals:")
_ROLLING_RE = re.compile(r"^Rolling 400s:")
_REPS_RE = re.compile(r"^Speed reps:")
_MPREPS_RE = re.compile(r"^Race-pace reps:")
_MPRUN_RE = re.compile(r"^Race-pace run:")
_LR_FARTLEK_RE = re.compile(r"^Long run w/ fartlek (?P<mi>[\d.]+) mi")
_LR_EASY_RE = re.compile(r"^Long run (?P<mi>[\d.]+) mi @ Easy")
_LR_MP_RE = re.compile(r"^Long run (?P<mi>[\d.]+) mi w/ (?P<blk>[\d.]+) mi @ MP")
_MLR_RE = re.compile(r"^Medium-long run (?P<mi>[\d.]+) mi")

# --- Grid-method vocabulary (Pfitzinger / Hansons / Higdon) ----------------------------------
# These generators emit their own labels (not the Daniels rotation), so the glossary decodes them
# here too — otherwise a Pfitz/Hanson/Higdon athlete's cells fall through as raw text.
_PFITZ_LT_RE = re.compile(r"^Lactate threshold (?P<mi>[\d.]+) mi w/ (?P<blk>[\d.]+) mi @ (?P<at>.+)$")
_PFITZ_GA_RE = re.compile(r"^General aerobic(?P<speed> \+ speed)? (?P<mi>[\d.]+) mi(?P<rest>.*)$")
_PFITZ_REC_RE = re.compile(r"^Recovery(?P<speed> \+ speed)? (?P<mi>[\d.]+) mi(?P<rest>.*)$")
_PFITZ_MP_RE = re.compile(r"^Marathon-pace run (?P<mi>[\d.]+) mi w/ (?P<blk>[\d.]+) mi @ marathon race pace$")
_PFITZ_VO2_RE = re.compile(r"^VO.?max (?P<mi>[\d.]+) mi w/ (?P<set>.+?) @ 5K race pace", re.IGNORECASE)
_PFITZ_DRESS_RE = re.compile(r"^Dress rehearsal (?P<mi>[\d.]+) mi w/ (?P<blk>[\d.]+) mi @ marathon race pace$")
_PLAIN_LONG_RE = re.compile(r"^Long run (?P<mi>[\d.]+) mi$")
_TUNEUP_RACE_RE = re.compile(r"tune-up race", re.IGNORECASE)
# Hanson "Tempo" is goal marathon pace (NOT threshold) — the key "tempo" overload to disambiguate.
_HANSON_TEMPO_RE = re.compile(r"^Tempo run (?P<mi>[\d.]+) mi @ goal MP$")
_HANSON_EASY_RE = re.compile(r"^Easy (?P<mi>[\d.]+) mi run$")
_HANSON_SPEED_RE = re.compile(r"^SPEED:\s*(?P<desc>.+)$", re.IGNORECASE)
_HANSON_STRENGTH_RE = re.compile(r"^STRENGTH:\s*(?P<desc>.+)$", re.IGNORECASE)
_HIGDON_MP_RE = re.compile(r"^Marathon pace run (?P<mi>[\d.]+) mi$")
_HIGDON_HM_TUNEUP_RE = re.compile(r"^Half marathon \(tune-up\)")
_CROSS_RE = re.compile(r"^Cross training")
_SHAKEOUT_RE = re.compile(r"[Ss]hakeout")
_RACE_DAY_RE = re.compile(r"^(Goal marathon|Marathon - race day)$")


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
            f"{intro}. It runs {m.group('total')} mi continuous, going "
            + " then ".join(parts)
            + f", with the marathon-pace segments at goal pace {m.group('mp')}/mi."
        )

    if _TEMPO_RE.match(text):
        return (
            "One continuous comfortably-hard effort at threshold pace (Daniels T), bracketed by a "
            "1.5 mi easy warm-up and 1.5 mi easy cool-down."
        )
    if _CRUISE_RE.match(text):
        return (
            "Mile threshold-pace repeats with short 60 s jogs (Daniels T), the same comfortably-hard "
            "effort broken up, plus a 1.5 mi easy warm-up and cool-down."
        )
    if _BROKENT_RE.match(text):
        return (
            "Half-mile threshold-pace repeats with short 60 s jogs (Daniels T). This is the same "
            "comfortably-hard threshold work as cruise intervals, just in more and shorter reps for a "
            "sharper feel, and it includes a 1.5 mi easy warm-up and cool-down."
        )
    if _OVERUNDER_RE.match(text):
        return (
            "Alternate 0.5 mi at threshold (the \"over\") with 0.5 mi at marathon pace (the \"under\"), "
            "nonstop. This is the same lactate-clearance work as cruise intervals, but floating to MP "
            "instead of jogging trains pace changes at race-adjacent efforts, and it is bracketed by a "
            "1.5 mi easy warm-up and cool-down."
        )
    if _TLADDER_RE.match(text):
        return (
            "Descending threshold blocks (one long, then shorter) at comfortably-hard threshold pace "
            "with 60 s jogs between (Runna 'Tempo 2-1-1'). It is the same threshold effort as cruise "
            "intervals in a varied shape, and it includes a 1.5 mi easy warm-up and cool-down."
        )
    if _VO2_DESC_RE.match(text):
        return (
            "A 1200-1000-800-600-400 m set at about 5K effort with equal-time jog recoveries "
            "(Daniels I). The shortening reps keep pace honest as fatigue builds, and it includes a "
            "1.5 mi easy warm-up and cool-down."
        )
    if _DROPSET_RE.match(text):
        return (
            "A single 1000-800-600-400-200 m descending ladder at about 5K effort with equal-time jog "
            "recoveries (Runna). It is short and sharp, finishing fast on tired legs, and it includes "
            "a 1.5 mi easy warm-up and cool-down."
        )
    if _VO2_LADDER_RE.match(text):
        return (
            "A 400-800-1200-800-400 m pyramid at about 5K effort with equal-time jog recoveries "
            "(Daniels I), plus a 1.5 mi easy warm-up and cool-down. It is the same VO2max stimulus as "
            "straight intervals, but the changing rep length keeps it fresh."
        )
    if _VO2_RE.match(text):
        return (
            "Hard reps at about 5K effort with equal-time jog recovery (Daniels I), plus a 1.5 mi easy "
            "warm-up and cool-down."
        )
    if _ROLLING_RE.match(text):
        return (
            "400 m reps at Rep pace (about mile race pace) with only a short 200 m jog float between "
            "(Runna). It is a continuous, rhythm-focused turnover set with less recovery than full "
            "speed reps, and it includes a 1.5 mi easy warm-up and cool-down."
        )
    if _REPS_RE.match(text):
        return (
            "Short, fast reps (400 m, or 200 m for pure turnover) at Daniels Repetition pace, roughly "
            "mile race pace, with a full jog recovery. They build speed and running economy rather "
            "than lactate tolerance, and they include a 1.5 mi easy warm-up and cool-down."
        )
    if _MPREPS_RE.match(text):
        return (
            "Short half-mile reps at goal marathon pace with a 60 s jog (Runna 'Race Pace Practice "
            "Half Miles'). It is a low-fatigue way to rehearse race rhythm, ideal in the taper and "
            "race week, and it includes a 1.5 mi easy warm-up and cool-down."
        )
    if _MPRUN_RE.match(text):
        return (
            "Continuous goal-marathon-pace miles, a midweek race-practice run to rehearse goal pace, "
            "rhythm and fueling (Pfitzinger midweek MP; Higdon pace run). It is bounded to stay a "
            "midweek session, with a 1.5 mi easy warm-up and cool-down."
        )

    m = _LR_FARTLEK_RE.match(text)
    if m:
        return (
            f"Aerobic long run {m.group('mi')} mi with light fartlek surges (about 1 min at 10K effort) "
            "sprinkled in. It stays an easy long-run day, and the surges just break it up and add a "
            "touch of turnover (Humphrey)."
        )

    m = _LR_MP_RE.match(text)
    if m:
        return (
            f"Long run {m.group('mi')} mi with the final {m.group('blk')} mi at goal marathon pace "
            "(a quality long run)."
        )
    m = _LR_EASY_RE.match(text)
    if m:
        return f"Aerobic long run {m.group('mi')} mi, staying Easy throughout."

    m = _MLR_RE.match(text)
    if m:
        return f"Medium-long run {m.group('mi')} mi, aerobic and slightly shorter than the weekly long run."

    # --- Grid-method vocabulary -----------------------------------------------------------------
    m = _PFITZ_LT_RE.match(text)
    if m:
        return (
            f"A Pfitzinger lactate threshold run of {m.group('mi')} mi total with {m.group('blk')} mi "
            f"at {m.group('at')} (comfortably-hard threshold effort), inside an easy warm-up and "
            "cool-down. It raises the lactate threshold so marathon pace costs less."
        )
    m = _PFITZ_MP_RE.match(text)
    if m:
        return (
            f"A Pfitzinger marathon-pace run of {m.group('mi')} mi total with {m.group('blk')} mi at "
            "goal marathon race pace. It banks race-pace volume and rehearses fueling and rhythm."
        )
    m = _PFITZ_DRESS_RE.match(text)
    if m:
        return (
            f"A Pfitzinger dress rehearsal of {m.group('mi')} mi total with {m.group('blk')} mi at goal "
            "marathon race pace. It is the final race-pace tune-up, so practice pacing, fueling and kit "
            "exactly as on race day."
        )
    m = _PFITZ_VO2_RE.match(text)
    if m:
        return (
            f"Pfitzinger VO2max intervals of {m.group('mi')} mi total with {m.group('set')} at about 5K "
            "race pace, jogging 50 to 90% of the interval time between. It builds VO2max and aerobic power."
        )
    m = _PFITZ_GA_RE.match(text)
    if m:
        speed = " with 100 m strides to sharpen turnover" if m.group("speed") else ""
        return (
            f"A Pfitzinger general aerobic run of {m.group('mi')} mi at a steady aerobic effort{speed}. "
            "It is the everyday mileage that builds the aerobic base, a notch above recovery pace."
        )
    m = _PFITZ_REC_RE.match(text)
    if m:
        speed = " with 100 m strides" if m.group("speed") else ""
        return (
            f"A Pfitzinger recovery run of {m.group('mi')} mi easy{speed}, deliberately slow running to "
            "promote recovery between hard days. Keep it relaxed."
        )
    if _TUNEUP_RACE_RE.search(text):
        return (
            f"{text}. This is a mid-block tune-up race run hard, and it re-measures your fitness (VDOT) "
            "and tells you whether goal pace is on track. Race it, then recover."
        )
    m = _HANSON_TEMPO_RE.match(text)
    if m:
        return (
            f"A Hansons tempo run of {m.group('mi')} mi continuous at goal marathon pace. In the "
            "Hansons method 'tempo' means MARATHON pace, not the faster threshold 'tempo' of Daniels, "
            "so it is sustained goal-pace work to lock in race rhythm."
        )
    m = _HANSON_SPEED_RE.match(text)
    if m:
        return (
            f"A Hansons speed workout, {m.group('desc')}, run as VO2max-range intervals with jog "
            "recoveries for aerobic power and turnover. It includes an easy warm-up and cool-down."
        )
    m = _HANSON_STRENGTH_RE.match(text)
    if m:
        return (
            f"A Hansons strength workout, {m.group('desc')}, run as longer reps a touch faster than goal "
            "marathon pace (about MP minus 10s/mi) to build fatigue resistance. It includes an easy "
            "warm-up and cool-down."
        )
    m = _HANSON_EASY_RE.match(text)
    if m:
        return f"Easy run {m.group('mi')} mi, conversational aerobic mileage that makes up the bulk of cumulative-fatigue volume."
    m = _HIGDON_MP_RE.match(text)
    if m:
        return (
            f"A Higdon marathon pace run of {m.group('mi')} mi at goal marathon pace, race-pace practice "
            "in place of an easy run to dial in goal effort."
        )
    if _HIGDON_HM_TUNEUP_RE.match(text):
        return (
            "A half-marathon tune-up race, run hard mid-block to re-anchor your VDOT. Reset paces off "
            "the result afterward."
        )
    m = _PLAIN_LONG_RE.match(text)
    if m:
        return f"Long run {m.group('mi')} mi, steady aerobic time on feet at easy effort (the week's endurance anchor)."
    if _CROSS_RE.match(text):
        return "Cross training, non-impact aerobic work (bike, swim, elliptical) that supports fitness without run-mileage load."
    if _RACE_DAY_RE.match(text.strip()):
        return "Race day, your goal marathon. Execute the plan with even pacing, fuel early, and trust the build."
    if _SHAKEOUT_RE.search(text):
        return "A shakeout, a short and very easy jog (often with a few light strides) to stay loose before race day."

    if "strides" in text.lower():
        return (
            "An easy aerobic run with strides. After the easy miles, add 6 x about 20 sec light, quick "
            "pickups (not sprints) with about 60 s easy jog between each (Daniels ST). The run stays an "
            "easy day, and the strides just sharpen turnover and economy."
        )
    if text.lower().startswith("easy"):
        return "Easy aerobic run, conversational effort inside the Easy pace range."
    if text.lower() == "rest":
        return "Rest day, no prescribed run."

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
