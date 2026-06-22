"""Curated book citations for the rules the engine encodes.

Each entry is verbatim source text (verified against the page-indexed PDFs via
``scripts/book_search.py``) so a plan can show *why* a prescription is what it is, in the
words of Daniels, Pfitzinger, Hanson, or Higdon — not the engine's say-so.

On the long run, only **Daniels (150 min) and Hanson (2–3 h window)** cap by *time*;
**Pfitzinger (20–22 mi, p.43) and Higdon (20 mi, p.28) cap by distance**. Higdon's glycogen
rationale (p.27, ~2 h ≈ 20 mi "for an accomplished runner") and Pfitz's 90-min benefit floor
(p.42) point toward time, but neither states a cap. The separate z2tc synthesis adopts the
Daniels/Hanson time window; the single-author engines stay faithful to their own book.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    key: str
    author: str
    book: str
    pages: str
    rule: str
    quote: str

    @property
    def ref(self) -> str:
        return f"{self.author}, {self.book} (p.{self.pages})"

    def __str__(self) -> str:
        return f"{self.ref}: {self.rule}"


CITATIONS: dict[str, Citation] = {
    "daniels_long_run": Citation(
        key="daniels_long_run",
        author="Daniels",
        book="Daniels' Running Formula",
        pages="63-64",
        rule="longest steady run ≤ 150 min (2.5 h); single L run ≤ 30% of weekly miles "
        "under 40 mpw, or the lesser of 25% and 150 min at 40+ mpw",
        quote="I also suggest that your longest steady run (unless preparing for some ultra "
        "events) be 150 minutes (2.5 hours), even if preparing for a marathon. … I like to "
        "limit any single L run to 30 percent of weekly mileage for runners who are totaling "
        "fewer than 40 miles per week. For those who are accumulating 40 or more miles per "
        "week, I suggest L runs be the lesser of 25 percent of weekly mileage or 150 minutes.",
    ),
    "hanson_long_run_window": Citation(
        key="hanson_long_run_window",
        author="Hanson (Humphrey)",
        book="Hansons Marathon Method",
        pages="66-67",
        rule="2:00–3:00 h is the productive long-run window; beyond it, muscle breakdown — so "
        "a runner slower than ~9:00/mi should not chase a 20-miler",
        quote="The research tells us that 2:00–3:00 hours is the optimal window for development "
        "in terms of long runs. Beyond that, muscle breakdown begins to occur. … a runner "
        "traveling at an 11:00-minute pace will take nearly 3:00 hours to finish [16 miles]. … "
        "anyone planning on running slower than a 9:00-minute pace should avoid the 20-mile trek.",
    ),
    "hanson_16_cap": Citation(
        key="hanson_16_cap",
        author="Hanson (Humphrey)",
        book="Hansons Marathon Method",
        pages="62",
        rule="16 mi is the longest run in the standard program — run the last 16 of the "
        "marathon (cumulative fatigue), not the first 16",
        quote="a 16-mile long run is the longest training day for the standard Hansons program. … "
        "It's not like running the first 16 miles of the marathon, but the last 16!",
    ),
    "pfitz_long_run_cap": Citation(
        key="pfitz_long_run_cap",
        author="Pfitzinger",
        book="Advanced Marathoning",
        pages="43",
        rule="long runs of 20–22 mi; beyond 22 takes disproportionately more out of the body",
        quote="long runs greater than 22 miles (35 km) take much more out of the body than do "
        "runs in the range of 20 to 22 miles … I believe that I ran slower in my marathons "
        "because [of 27–30 mi runs].",
    ),
    "higdon_20": Citation(
        key="higdon_20",
        author="Higdon",
        book="Marathon: The Ultimate Training Guide",
        pages="28, 106",
        rule="builds to a single 20-mile long run by DISTANCE (no time cap) — '20' is the "
        "conventional peak, partly because it is a round number",
        quote="Twenty miles is the longest distance that I ask people using my training programs "
        "to run in practice for a marathon. … Twenty is the peak distance used in most training "
        "programs, if only because 20 is a round number.",
    ),
    "higdon_glycogen": Citation(
        key="higdon_glycogen",
        author="Higdon",
        book="Marathon: The Ultimate Training Guide",
        pages="27",
        rule="glycogen rationale: ~2 h of running depletes glycogen — '20 miles for an "
        "accomplished runner' — i.e. the dose is really TIME, which is fewer miles for a slower runner",
        quote="it is only after about 2 hours of running—or about 20 miles for an accomplished "
        "runner—that the body begins to fully deplete its stores of glycogen, the energy source "
        "that fuels the muscles.",
    ),
    "pfitz_long_run_floor": Citation(
        key="pfitz_long_run_floor",
        author="Pfitzinger",
        book="Advanced Marathoning",
        pages="42",
        rule="aerobic-adaptation TIME floor: runs of 90 min or longer (a minimum for benefit, "
        "not a cap)",
        quote="For marathoners, the primary type of training to stimulate these adaptations is "
        "runs of 90 minutes or longer. Your total training volume, however, also contributes.",
    ),
    "pfitz_pace_basis": Citation(
        key="pfitz_pace_basis",
        author="Pfitzinger",
        book="Advanced Marathoning",
        pages="41",
        rule="lactate-threshold pace is similar to 15K to half marathon race pace",
        quote="For experienced runners, lactate-threshold pace is very similar to race pace for "
        "15K to the half marathon. ... In terms of heart rate, lactate threshold typically occurs "
        "at 82 to 91 percent of maximal heart rate or 77 to 88 percent of heart rate reserve in "
        "well-trained runners.",
    ),
    "hanson_pace_basis": Citation(
        key="hanson_pace_basis",
        author="Hanson (Humphrey)",
        book="Hansons Marathon Method",
        pages="104",
        rule="Table 3.5 determines workout paces based on goal marathon times",
        quote="To be utilized in determining how fast to run your workouts, Table 3.5 demonstrates "
        "pace per mile based on various goal marathon times. ... The Marathon Pace is the speed "
        "at which your tempo runs should be run. The Strength column will be your reference for "
        "strength workouts, and the 10K and 5K columns for your speed workouts.",
    ),
    "higdon_pace_basis": Citation(
        key="higdon_pace_basis",
        author="Higdon",
        book="Marathon: The Ultimate Training Guide",
        pages="115, 126",
        rule="run regular and long runs at a comfortable, conversational pace",
        quote="Do not worry about how fast you run your regular workouts. Run at a comfortable pace. "
        "If you are training with a friend, the two of you should be able to hold a conversation. "
        "If you cannot, you are running too fast. ... Speed is of limited importance during long runs. "
        "More important is time on your feet.",
    ),
    "pfitz_ch8_schedule": Citation(
        key="pfitz_ch8_schedule",
        author="Pfitzinger",
        book="Advanced Marathoning",
        pages="292-295",
        rule="verbatim 18-week schedule for up-to-55 miles per week",
        quote="Chapter 8: Schedules Up to 55 Miles per Week. 18-Week Schedule.",
    ),
    "hanson_beginner_schedule": Citation(
        key="hanson_beginner_schedule",
        author="Hanson (Humphrey)",
        book="Hansons Marathon Method",
        pages="124-126",
        rule="verbatim 18-week schedules for Just Finish (Table 4.2), Beginner (Table 4.3), and Advanced (Table 4.4)",
        quote="Table 4.2: Just Finish Program; Table 4.3: Beginner Program; Table 4.4: Advanced Program.",
    ),
    "higdon_novice_schedule": Citation(
        key="higdon_novice_schedule",
        author="Higdon",
        book="Marathon: The Ultimate Training Guide",
        pages="46, 78",
        rule="verbatim 18-week schedules for Novice 1, Novice 2, Intermediate 1, and Intermediate 2",
        quote="The gradual buildup of a lot of miles turns a 5K runner into a marathoner. In my novice "
        "program, Tuesdays and Thursdays are easy days, when runners go only 3 to 5 miles, most often "
        "running at a conversational pace.",
    ),
}

# Ordered for display: the unifying time-window rule first, then the per-method distances.
LONG_RUN_KEYS = [
    "hanson_long_run_window",
    "daniels_long_run",
    "pfitz_long_run_cap",
    "higdon_20",
    "hanson_16_cap",
]


def get(key: str) -> Citation:
    try:
        return CITATIONS[key]
    except KeyError:
        raise KeyError(f"Unknown citation {key!r}. Known: {', '.join(sorted(CITATIONS))}")


def long_run_citations() -> list[Citation]:
    """The book references behind the time-on-feet long-run cap."""
    return [CITATIONS[k] for k in LONG_RUN_KEYS]


def long_run_rationale(recommended_mi: float, time_on_feet_min: float, window_min: tuple[int, int]) -> str:
    """One-line, athlete-facing justification for a long-run length, in time-on-feet terms."""
    lo, hi = window_min
    h = int(time_on_feet_min // 60)
    m = int(round(time_on_feet_min % 60))
    win = f"the {lo // 60}-{hi // 60} h productive window (Hanson p.66)"
    if time_on_feet_min > hi + 1:
        tail = f"*above* {win} — long for this pace; muscle-breakdown risk"
    elif time_on_feet_min < lo - 1:
        tail = f"*below* {win} — room to go longer"
    else:
        tail = f"within {win}; same time-on-feet stimulus as a faster runner's longer run"
    return f"{recommended_mi:g} mi ≈ {h}:{m:02d} on feet — {tail}."


PACE_BASIS = {
    "higdon": "distances verbatim from halhigdon.com; paces shown are VDOT-derived equivalents; book prescribes conversational pace / by feel, and goal MP for pace runs.",
    "pfitzinger": "distances verbatim from Advanced Marathoning; paces shown are VDOT-derived equivalents; book prescribes LT as 15K-to-half-marathon race pace, and specific %HRmax/HRR bands.",
    "hanson": "distances verbatim from Hansons Marathon Method; paces shown are VDOT-derived equivalents; book prescribes goal-MP Table 3.5 (speed at 5K-10K, strength at MP-10s/mi, tempo at goal MP).",
}

