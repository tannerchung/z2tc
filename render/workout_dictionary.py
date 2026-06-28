"""Generate the club "Workout Dictionary" tab from the engine catalog (deterministic).

The dictionary is built from the same source the generator runs, so it never drifts from the
plans. The named rotation sessions come from :data:`engine.plan.workouts.CATALOG_WORKOUTS`
(each carries its own definition and how the engine sizes it), the Daniels pace meanings come
from :data:`render.workout_glossary.PACE_LEGEND`, and the shared terminology plus other-method
vocabulary comes from :data:`render.workout_glossary.STATIC_GLOSSARY`. Styling mirrors the other
club tabs (Long Runs, Read Me).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.plan.workouts import CATALOG_WORKOUTS
from render.workout_glossary import PACE_LEGEND, STATIC_GLOSSARY

# Role order and the plain-language banner for each catalog group. Kept here (not in the engine)
# because it is presentation copy; the engine owns the workouts themselves.
_ROLE_ORDER: tuple[str, ...] = ("T", "I", "R", "M", "long")
_ROLE_TITLES: dict[str, str] = {
    "T": "Threshold (T), comfortably hard running that clears lactate so goal pace costs less",
    "I": "Interval (I), VO2max and aerobic power at about 5K effort",
    "R": "Repetition (R), short and fast running for speed and economy",
    "M": "Marathon pace (M), goal-pace rehearsal",
    "long": "Long runs, aerobic durability and race-specific blends",
}

_PACE_ROWS: tuple[tuple[str, str], ...] = (
    ("Easy (E)", PACE_LEGEND["E"]),
    ("Marathon (M)", PACE_LEGEND["M"]),
    ("Threshold (T)", PACE_LEGEND["T"]),
    ("Interval (I)", PACE_LEGEND["I"]),
    ("Repetition (R)", PACE_LEGEND["R"]),
)


@dataclass
class DictRow:
    kind: str          # title|subtitle|blank|colhead|group|workout|term
    cells: list[str]


@dataclass
class WorkoutDictionaryLayout:
    rows: list[DictRow]
    ncols: int
    column_widths: list[int]

    @property
    def values(self) -> list[list[str]]:
        return [r.cells for r in self.rows]


def build_workout_dictionary_layout() -> WorkoutDictionaryLayout:
    rows: list[DictRow] = [
        DictRow("title", ["Workout Dictionary", "", ""]),
        DictRow(
            "subtitle",
            ["Every session the plans use, decoded. This tab is generated from the engine catalog, "
             "so it stays in sync with what the plans prescribe.", "", ""],
        ),
        DictRow("blank", ["", "", ""]),
        DictRow("colhead", ["Workout", "What it's for", "How it's built"]),
    ]

    by_role: dict[str, list] = {role: [] for role in _ROLE_ORDER}
    for w in CATALOG_WORKOUTS:
        by_role.setdefault(w.role, []).append(w)
    for role in _ROLE_ORDER:
        entries = by_role.get(role) or []
        if not entries:
            continue
        rows.append(DictRow("group", [_ROLE_TITLES.get(role, role), "", ""]))
        for w in entries:
            rows.append(DictRow("workout", [w.name, w.purpose, w.generation]))

    rows.append(DictRow("blank", ["", "", ""]))
    rows.append(DictRow("group", ["Daniels paces (per mile)", "", ""]))
    for zone, meaning in _PACE_ROWS:
        rows.append(DictRow("term", [zone, meaning, ""]))

    rows.append(DictRow("blank", ["", "", ""]))
    rows.append(DictRow("group", ["Terminology and other methods", "", ""]))
    for term, meaning in STATIC_GLOSSARY:
        rows.append(DictRow("term", [term, meaning, ""]))

    return WorkoutDictionaryLayout(rows=rows, ncols=3, column_widths=[210, 470, 330])


# --- Formatting (mirrors the Read Me / Long Runs club tabs) ----------------------------------
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


def _merge(sheet_id, row, c0, c1):
    return {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": c0, "endColumnIndex": c1}}}


def build_workout_dictionary_format_requests(sheet_id: int, layout: WorkoutDictionaryLayout, theme) -> list[dict]:
    n = layout.ncols
    reqs: list[dict] = [
        {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": len(layout.rows) + 2, "startColumnIndex": 0, "endColumnIndex": n}}}
    ]
    for i, w in enumerate(layout.column_widths):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    merges: list[dict] = []
    for ri, row in enumerate(layout.rows):
        k = row.kind
        if k == "title":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, size=theme.title_font_size, fg=theme.navy, bg=(1, 1, 1))))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "subtitle":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1), wrap=True, valign="TOP")))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "colhead":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, fg=(1, 1, 1), bg=theme.navy)))
        elif k == "group":
            reqs.append(_rng(sheet_id, ri, 0, n, _cell(theme, bold=True, size=theme.header_font_size, fg=theme.navy, bg=theme.pace_section_rgb)))
            merges.append(_merge(sheet_id, ri, 0, n))
        elif k == "workout":
            reqs.append(_rng(sheet_id, ri, 0, 1, _cell(theme, bold=True, fg=theme.navy, bg=(1, 1, 1), wrap=True, valign="TOP")))
            reqs.append(_rng(sheet_id, ri, 1, 2, _cell(theme, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP")))
            reqs.append(_rng(sheet_id, ri, 2, 3, _cell(theme, size=theme.subtitle_font_size, fg=theme.gray_text, bg=(1, 1, 1), wrap=True, valign="TOP")))
        elif k == "term":
            reqs.append(_rng(sheet_id, ri, 0, 1, _cell(theme, bold=True, fg=theme.navy, bg=(1, 1, 1), wrap=True, valign="TOP")))
            reqs.append(_rng(sheet_id, ri, 1, n, _cell(theme, fg=theme.dark_text, bg=(1, 1, 1), wrap=True, valign="TOP")))
            merges.append(_merge(sheet_id, ri, 1, n))

    reqs.append({"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 4}}, "fields": "gridProperties.frozenRowCount"}})
    reqs.extend(merges)
    return reqs
