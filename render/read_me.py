"""Generate the "Read Me First" orientation tab from a plan's shape.

Mostly templated narrative; the data-driven bits are the race name/date, block length, and
the four phase week-ranges (pulled from the spine plan's phase bands so they stay in sync
with the Long Runs banners). Tab styling mirrors the hand-built club page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from collections import Counter

from engine.execution import ON_TRACK_RATIO
from engine.plan.models import TrainingPlan
from render.long_runs import _is_marathon_week, canonical_phase

_PHASE_ORDER = ["Base", "Threshold", "Race Prep", "Taper"]
_PHASE_DESC = {
    "Base": "Aerobic endurance + running rhythm.",
    "Threshold": "Tempo work raises the pace you can sustain. Long runs begin carrying marathon-pace blocks.",
    "Race Prep": "VO2max intervals and a tune-up race sharpen speed. The race-practice long run is the peak.",
    "Taper": "Volume drops, intensity stays. You arrive fresh.",
}

_RESOURCES = (
    "Daniels-running-formula.pdf\n"
    "Advanced Marathoning - Pfitzinger, Pete.pdf\n"
    "Hansons Marathon Method - Luke Humphrey.pdf\n"
    "Marathon, Revised and Updated_ The Ultimat - Hal Higdon.pdf"
)


@dataclass
class ReadMeRow:
    kind: str                      # title|subtitle|blank|header|section
    cells: list[str]


@dataclass
class ReadMeLayout:
    rows: list[ReadMeRow]
    ncols: int
    column_widths: list[int]

    @property
    def values(self) -> list[list[str]]:
        return [r.cells for r in self.rows]


def _phase_spans(plan: TrainingPlan) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for w in plan.weeks:
        if _is_marathon_week(w):
            continue
        canon = canonical_phase(w.phase)
        a, b = spans.get(canon, (w.index, w.index))
        spans[canon] = (min(a, w.index), max(b, w.index))
    return spans


def _phases_body(plan: TrainingPlan) -> str:
    spans = _phase_spans(plan)
    lines: list[str] = []
    for phase in _PHASE_ORDER:
        if phase not in spans:
            continue
        a, b = spans[phase]
        rng = f"Week {a}" if a == b else f"Weeks {a}-{b}"
        lines.append(f"{phase} ({rng}): {_PHASE_DESC.get(phase, '')}".rstrip())
    return "\n".join(lines)


def _friendly_date(iso: object) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d:%B} {d.day}, {d.year}"
    except (ValueError, TypeError):
        return str(iso or "race day")


def _race_year(spine: TrainingPlan) -> int:
    try:
        return date.fromisoformat(str(spine.goal.get("date"))[:10]).year
    except (ValueError, TypeError):
        return date.today().year


def _race_date_obj(plan: TrainingPlan) -> date | None:
    try:
        return date.fromisoformat(str(plan.goal.get("date"))[:10])
    except (ValueError, TypeError):
        return None


def _countdown_formula(name: str, d: date) -> str:
    """A *live* per-race countdown computed in-sheet from ``TODAY()`` — "15 weeks to the Chicago
    Marathon · October 11, 2026" — so the number ticks down on its own and never goes stale. Reads
    days inside race week, "Race day" on the day, and a ✓ once the race is past."""
    suffix = f"{name} · {d:%B} {d.day}, {d.year}".replace('"', '""')
    iso = f"DATE({d.year},{d.month},{d.day})"
    return (
        f'=LET(rem,{iso}-TODAY(),IFS('
        f'rem<0,"✓ {suffix}",'
        f'rem=0,"Race day — {suffix}",'
        f'rem<7,rem&IF(rem=1," day"," days")&" to the {suffix}",'
        f'TRUE,ROUND(rem/7,0)&IF(ROUND(rem/7,0)=1," week"," weeks")&" to the {suffix}"))'
    )


def _countdown_lines(marathons: list[tuple[str, date, int]]) -> list[str]:
    """One live countdown formula per race, chronological — the generic title plus these lines tell
    each runner how far out their race is and which races the group is training for."""
    return [_countdown_formula(name, d) for name, d, _ in sorted(marathons, key=lambda t: t[1])]


def _bullets(text: str) -> str:
    """Turn a newline-separated body into scannable bullets (each logical line its own point)."""
    return "\n".join(f"•  {ln.strip()}" for ln in text.split("\n") if ln.strip())


def _typical_quality_count(plan: TrainingPlan) -> int:
    """The modal number of quality (hard) days in a normal build week — so the copy can say what
    this plan actually does (one or two quality efforts) instead of hard-coding 'two'."""
    counts = [
        len(w.quality_days)
        for w in plan.weeks
        if not _is_marathon_week(w) and not w.is_down_week
    ]
    if not counts:
        return 2
    return Counter(counts).most_common(1)[0][0]


def _week_body(plan: TrainingPlan) -> str:
    n = _typical_quality_count(plan)
    if n <= 1:
        effort = (
            "Most weeks carry one quality effort plus the Saturday long run, so two harder days "
            "in total, and the rest is easy aerobic running."
        )
    else:
        effort = (
            "Most weeks carry two quality efforts. When the long run has marathon-pace work, "
            "Thursday stays easy, so the hard days are Tuesday and Saturday. When the long run is "
            "easy, Thursday upgrades to a second workout, so the hard days are Tuesday and Thursday."
        )
    return (
        "A typical week runs a long run on Saturday, rest on Sunday and Monday, a workout on "
        "Tuesday, easy on Wednesday, easy or a second workout on Thursday, and strength on Friday. "
        f"{effort} You can shift days to fit your life, but never stack two quality sessions back to back."
    )


def _legend_body(plan: TrainingPlan) -> str:
    pct = int(round(ON_TRACK_RATIO * 100))
    return (
        "The Wk column is the week number and Date is that week's Saturday. The seven day cells from "
        "Monday to Sunday hold each day's run, Total is the week's planned mileage, and the Why column "
        "gives a plain note on what the week is for.\n"
        "The workout letters follow Daniels' shorthand for effort. E is easy aerobic running, M is goal "
        "marathon pace, T is threshold (comfortably hard), I is interval or VO2max work at about 5K "
        "effort, R is repetition (short and fast with full recovery), and steady sits between easy and "
        "marathon pace. Watch one word. In the Hansons method 'tempo' means marathon pace, while in "
        "Daniels 'tempo' means threshold, and your sheet always spells out which one applies.\n"
        "Colored banners mark the four phases (Base, Threshold, Race Prep, Taper), and the Workout "
        "Dictionary tab decodes every session by name.\n"
        "A tune-up race cell turns green when your result keeps the goal in reach, amber when it is worth "
        "watching, and red when you are behind and we should re-anchor. An amber Total means the week "
        "climbs above mileage you have demonstrated before, so ramp into it carefully.\n"
        f"A slate-blue week number means your logged running (from Strava) came in under about {pct}% of "
        "what was prescribed that week. It is a heads-up rather than a failure, and the Why note explains "
        "it. A short week is shaded differently from the amber over-capacity cue on purpose, because "
        "coming up short is not the same as doing too much.\n"
        f"Once a week is logged we compare your actual mileage against what was prescribed. At or above "
        f"about {pct}% reads as on plan, and anything below that is flagged short so you and your coach "
        "can adjust the next block."
    )


def build_read_me_layout(
    spine: TrainingPlan,
    *,
    athletes: list[str] | None = None,
    marathons: list[tuple[str, date, int]] | None = None,
) -> ReadMeLayout:
    race_date = _friendly_date(spine.goal.get("date"))
    year = _race_year(spine)
    roster = [a for a in (athletes or []) if a]
    # Without an explicit roster (e.g. a single-race build), still show the spine race's countdown.
    if not marathons:
        sd = _race_date_obj(spine)
        if sd is not None:
            marathons = [(str(spine.goal.get("name") or "Marathon"), sd, spine.block_weeks or len(spine.weeks))]

    sections: list[tuple[str, str]] = [
        (
            "This plan is yours",
            "Everything here is voluntary. You can follow it to the letter, use just the Saturday "
            "long runs, or ignore it entirely. If a workout feels too hard or a distance feels too "
            "far on a given day, scale it back. The plan is designed to maximize fitness gains and "
            "minimize injury risk, but your body on the day always overrides what a spreadsheet says. "
            "If you want to stay with the group on a long run even though your plan says a shorter "
            "distance, go for it. If you want to peel off early, that is fine too. Every tab explains "
            "why each session was built the way it was and how it connects to the Daniels and "
            "Pfitzinger training philosophies, so you can make informed decisions rather than "
            "following blindly.",
        ),
        (
            "How this plan was built",
            "Your paces come from your most recent race, converted to a fitness score (VDOT) using "
            "Daniels' Running Formula — Daniels' idea is that one number from a real result can set "
            "every training pace to your current physiology, so you train at the right effort instead "
            "of guessing. That score sets your Easy and Threshold paces; Marathon Pace is the one zone "
            "set to your goal rather than current fitness. Weekly mileage opens at a level your body "
            "already handles and builds ~10% per week with a step-back every 3-4 weeks.\n"
            "How the hard work is shaped depends on your base. If you come in with a higher mileage "
            "base, your plan follows Pfitzinger's approach: he builds marathon-specific endurance by "
            "rehearsing race demands, so you get marathon-pace blocks inside the long run, medium-long "
            "midweek runs, and two quality efforts a week. If you are rebuilding from lower mileage, "
            "your plan follows Daniels' approach: he prioritizes the aerobic base and doses intensity "
            "carefully, so long runs stay easy and time-capped (the aerobic benefit plateaus while "
            "injury risk keeps climbing) with one quality effort a week. Both are established methods "
            "from the source books (see Resources).",
        ),
        (
            "Why most running is easy",
            "About 80% of your running should be conversational (Garmin Zone 2). This builds the "
            "aerobic engine that lets you sustain pace over 26.2 miles. Easy running makes your hard "
            "days effective.",
        ),
        ("How to read this sheet", _bullets(_legend_body(spine))),
        ("The four training phases", _phases_body(spine)),
        ("Your week", _week_body(spine)),
        (
            "Saturday long runs",
            "The one session we all do together. Loop course, warm up as a group, split into pace "
            "packs for the marathon-pace miles, regroup at water stops. Everyone finishes around the "
            "same time because different distances at different speeds land in the same window. The "
            "Long Runs tab shows every runner's distance side by side for course planning, with a "
            "race-day band for each marathon in the group. Each runner's own tab has their full "
            "weekly plan, and the Workout Dictionary tab decodes every session by name.",
        ),
        ("Resources", _bullets(_RESOURCES)),
    ]

    if roster:
        names = ", ".join(roster)
        sections.insert(
            1,
            (
                "Who this is for",
                f"This block is built for {len(roster)} runners training together. The group is {names}. "
                "Everyone trains off the same Saturday calendar, but each runner has their own paces, "
                "mileage, and goal, so check your own tab for the specifics.",
            ),
        )

    # Stacked single-column flow: a tinted header band per section over a full-width body, with a
    # blank spacer between, reads far better than a label-column / wall-of-text-column table.
    rows: list[ReadMeRow] = [
        ReadMeRow("title", [f"Zone 2 Track Club — {year} Marathon Plan"]),
    ]
    countdowns = _countdown_lines(marathons) if marathons else [f"{spine.block_weeks or len(spine.weeks)} weeks to {race_date}"]
    for line in countdowns:
        rows.append(ReadMeRow("countdown", [line]))
    rows.append(ReadMeRow("blank", [""]))
    for title, body in sections:
        rows.append(ReadMeRow("section_header", [title]))
        rows.append(ReadMeRow("section_body", [body]))
        rows.append(ReadMeRow("blank", [""]))
    return ReadMeLayout(rows=rows, ncols=1, column_widths=[760])


# ---------------------------------------------------------------------------------
def _rgb(t: tuple[float, float, float]) -> dict[str, float]:
    return {"red": t[0], "green": t[1], "blue": t[2]}


def _cell(theme, *, bold=False, size=None, fg=None, bg=None, wrap=False, valign=None):
    text = {"fontFamily": theme.font_family, "fontSize": size or theme.body_font_size, "bold": bold}
    if fg:
        text["foregroundColor"] = _rgb(fg)
    cell: dict = {"textFormat": text}
    if bg:
        cell["backgroundColor"] = _rgb(bg)
    if wrap:
        cell["wrapStrategy"] = "WRAP"
    if valign:
        cell["verticalAlignment"] = valign
    return cell


_FIELDS = "userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment)"


def _rng(sheet_id, row, c0, c1, cell):
    return {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": c0, "endColumnIndex": c1}, "cell": {"userEnteredFormat": cell}, "fields": _FIELDS}}


def build_read_me_format_requests(sheet_id: int, layout: ReadMeLayout, theme) -> list[dict]:
    n = layout.ncols
    reqs: list[dict] = []
    for i, w in enumerate(layout.column_widths):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    for ri, row in enumerate(layout.rows):
        k = row.kind
        if k == "title":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, size=theme.title_font_size, fg=theme.navy, bg=(1, 1, 1))))
        elif k == "countdown":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1))))
            # A live "=...TODAY()..." countdown: the RAW values write stored it as literal text, so set
            # it as a real formula here (applied after the write) and Sheets recomputes it daily.
            cell0 = row.cells[0] if row.cells else ""
            if isinstance(cell0, str) and cell0.startswith("="):
                reqs.append({
                    "updateCells": {
                        "range": {"sheetId": sheet_id, "startRowIndex": ri, "endRowIndex": ri + 1, "startColumnIndex": 0, "endColumnIndex": 1},
                        "rows": [{"values": [{"userEnteredValue": {"formulaValue": cell0}}]}],
                        "fields": "userEnteredValue",
                    }
                })
        elif k == "section_header":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=theme.pace_section_rgb, wrap=True, valign="MIDDLE")))
        elif k == "section_body":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP")))

    reqs.append({"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}})
    return reqs
