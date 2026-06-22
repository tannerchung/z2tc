"""Read club ``Intake_responses`` (Google Form → Sheets) into ``SurveyInputs``.

Form column names vary slightly with question wording; we match using normalized
headers plus aliases (see ``docs/intake-google-form.md``). Strava-derived numerics
(``vdot``, ``w_now``, …) are **not** on the form — supply a ``defaults`` ``SurveyInputs``
(merge: sheet non-empty cells overlay defaults).

Requires ``render.runtime.sheets_service`` (Hermes token + ``spreadsheets`` scope).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from lib.marathon_calendar import resolve_race_date, year_hint_from_iso
from store.models import MarathonRaceIn, SurveyInputs

_log = logging.getLogger(__name__)


def _norm_header(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


def _escape_tab(title: str) -> str:
    if "'" in title or " " in title:
        return "'" + title.replace("'", "''") + "'"
    return title


# (normalized needle, canonical internal key) — first match wins per header cell.
# Legacy fallbacks; the live club form is disambiguated in ``_map_header`` first.
_HEADER_RULES: list[tuple[str, str]] = [
    ("timestamp", "timestamp"),
    ("email", "email"),
    ("full name", "full_name"),
    ("full_name", "full_name"),
    ("strava", "strava_id"),
    ("primary marathon", "primary_marathon"),
    ("primary_marathon", "primary_marathon"),
    ("primary date", "primary_date"),
    ("primary_date", "primary_date"),
    ("primary goal", "primary_goal"),
    ("primary_goal", "primary_goal"),
    ("marathon_2_name", "marathon_2_name"),
    ("marathon_2_date", "marathon_2_date"),
    ("marathon_3_name", "marathon_3_name"),
    ("marathon_3_date", "marathon_3_date"),
    ("days per week", "days_per_week"),
    ("days_per_week", "days_per_week"),
    ("long run day", "long_run_day"),
    ("long_run_day", "long_run_day"),
    ("injury", "injury_notes"),
    ("injury_notes", "injury_notes"),
    ("method", "method_choice"),
    ("method_choice", "method_choice"),
    ("races", "races_vacations_notes"),
    ("races_vacations_notes", "races_vacations_notes"),
    ("vacation", "races_vacations_notes"),
    ("coaching", "coaching_extras_notes"),
    ("coaching_extras_notes", "coaching_extras_notes"),
    ("secondary marathon", "secondary_marathon_notes"),
    ("secondary_marathon_notes", "secondary_marathon_notes"),
    ("other notes", "other_notes"),
    ("other_notes", "other_notes"),
    ("coach notes", "coach_notes"),
    ("coach_notes", "coach_notes"),
    ("birthday", "birthday"),
    ("instagram", "instagram_handle"),
]

# Headers whose presence is expected but intentionally carries no engine signal.
_IGNORED_HEADER_NEEDLES = ("timestamp", "email", "birthday", "instagram", "where are you staying")


def _map_header(cell: str) -> str | None:
    h = _norm_header(cell)
    if not h:
        return None
    # Live club form ("Intake" tab) — disambiguate before the legacy substring rules.
    if "first name" in h:
        return "first_name"
    if "last name" in h:
        return "last_name"
    if "which marathons" in h or "running this year" in h:
        return "marathons_selected"
    if "your primary" in h:  # "Which one is your primary?"
        return "primary_marathon"
    if "a goal" in h:
        return "primary_goal"
    if "b goal" in h:
        return "goal_b"
    if "c goal" in h:
        return "goal_c"
    if "latest half" in h:
        return "latest_half_time" if "time" in h else "latest_half_race"
    if "latest marathon" in h:
        return "latest_marathon_time" if "time" in h else "latest_marathon_race"
    if "departing" in h:
        return "departure_date"
    if "arriving" in h:
        return "arrival_date"
    if "carb" in h:
        return "carb_load"
    if "shakeout" in h:
        return "shakeout"
    if "starting your training" in h:
        return "training_start"
    if "how do you want to train" in h:
        return "training_philosophy"
    if "hard run" in h or "hard runs" in h:
        return "hard_session_intensity_pref" if "difficult" in h else "hard_quality_sessions_pref"
    if "long run" in h or "long runs" in h:
        if "difficult" in h:
            return "long_run_difficulty_pref"
        if "frequency" in h:
            return "long_run_frequency_pref"
        if "day" in h:
            return "long_run_day"
    if "marathon 3" in h or "third marathon" in h:
        return "marathon_3_date" if "date" in h else "marathon_3_name"
    if "marathon 2" in h or "second marathon" in h:
        return "marathon_2_date" if "date" in h else "marathon_2_name"
    for needle, key in _HEADER_RULES:
        if needle == h or needle in h or h in needle:
            return key
    return None


def unmapped_headers(header_row: list[Any]) -> list[str]:
    """Non-empty headers that ``_map_header`` does not recognize (excluding known-ignored)."""
    out: list[str] = []
    for cell in header_row:
        h = _norm_header(str(cell or ""))
        if not h or _map_header(str(cell or "")):
            continue
        if any(n in h for n in _IGNORED_HEADER_NEEDLES):
            continue
        out.append(str(cell).strip())
    return out


def strava_id_from_cell(raw: str | None) -> str | None:
    """Digits from profile URL or bare id."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"strava\.com/athletes/(\d+)", s, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", s)
    return m.group(1) if m else None


def _sheets_serial_to_iso(n: float) -> str | None:
    """Google/Excel serial date → ISO (approximate; good for Form date cells)."""
    try:
        d = int(float(n))
    except (TypeError, ValueError):
        return None
    base = date(1899, 12, 30)
    try:
        return (base + timedelta(days=d)).isoformat()
    except OverflowError:
        return None


def _parse_date_cell(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return _sheets_serial_to_iso(float(s))
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_goal_seconds(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if any(x in low for x in ("finish", "healthy", "complete", "unsure", "n/a")):
        return None
    m = re.match(r"^(\d+):(\d{2}):(\d{2})$", s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"^(\d+):(\d{2})$", s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = re.match(r"^(\d+)\s*h\s*(\d+)\s*m", low)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    return None


def _parse_days_per_week(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        n = int(float(s))
        if 3 <= n <= 7:
            return n
    except ValueError:
        pass
    m = re.search(r"\b([3-7])\b", s)
    return int(m.group(1)) if m else None


def _parse_method(raw: str | None) -> str | None:
    if raw is None:
        return None
    low = str(raw).strip().lower()
    if not low or "auto" in low or "you tell" in low:
        return None
    if "daniels" in low:
        return "daniels"
    if "pfitz" in low or "pfitzinger" in low:
        return "pfitzinger"
    return None


def _injury_prone_from_notes(raw: str | None) -> bool:
    if not raw:
        return False
    low = str(raw).lower()
    if any(x in low for x in ("none", "n/a", "no injury", "healthy", "no issues")):
        return False
    return len(str(raw).strip()) > 3


def _build_header_index(header_row: list[Any]) -> dict[int, str]:
    idx: dict[int, str] = {}
    used_keys: set[str] = set()
    for i, cell in enumerate(header_row):
        key = _map_header(str(cell or ""))
        if not key:
            continue
        if key in used_keys:
            continue
        used_keys.add(key)
        idx[i] = key
    return idx


def _row_to_canonical(
    header_index: dict[int, str], row: list[Any]
) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, key in header_index.items():
        if i < len(row):
            v = row[i]
            out[key] = "" if v is None else str(v).strip()
    return out


def fetch_intake_rows(
    spreadsheet_id: str,
    tab: str = "Intake",
    *,
    service: Any = None,
) -> tuple[list[str], list[list[Any]]]:
    """Return ``(header_row, data_rows)`` from the linked responses tab."""
    from render.runtime import sheets_service

    svc = service or sheets_service()
    rng = f"{_escape_tab(tab)}!A1:ZZ2000"
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=rng)
        .execute()
    )
    rows = res.get("values") or []
    if not rows:
        return [], []
    header = list(rows[0])
    missed = unmapped_headers(header)
    if missed:
        _log.warning("intake tab %r: %d unmapped column(s) dropped: %s", tab, len(missed), missed)
    return header, rows[1:]


def canonical_row_to_survey(
    row: dict[str, str],
    *,
    defaults: SurveyInputs,
) -> tuple[SurveyInputs, str | None]:
    """Merge mapped row + defaults → ``SurveyInputs``; return ``(survey, strava_id)``."""
    d = defaults.model_dump(mode="json")
    combined = " ".join(
        p for p in ((row.get("first_name") or "").strip(), (row.get("last_name") or "").strip()) if p
    )
    name = (row.get("full_name") or "").strip() or combined or d.get("name") or "Athlete"
    d["name"] = name

    if row.get("email"):
        d["email"] = row["email"]

    sid = strava_id_from_cell(row.get("strava_id"))
    if sid:
        d["strava_profile_url"] = f"https://www.strava.com/athletes/{sid}"

    if row.get("primary_marathon"):
        d["race_name"] = row["primary_marathon"].strip()
    pd = _parse_date_cell(row.get("primary_date"))
    if pd:
        d["race_date"] = pd
    elif row.get("primary_marathon"):
        # No date column on the live form: resolve from the official calendar, using the
        # arrival/departure year as a hint when present.
        year = year_hint_from_iso(
            _parse_date_cell(row.get("arrival_date")),
            _parse_date_cell(row.get("departure_date")),
        )
        official = resolve_race_date(row["primary_marathon"], year)
        if official:
            d["race_date"] = official

    goal = _parse_goal_seconds(row.get("primary_goal"))
    if goal is not None:
        d["goal_marathon_s"] = goal
    goal_b = _parse_goal_seconds(row.get("goal_b"))
    if goal_b is not None:
        d["goal_marathon_b_s"] = goal_b
    goal_c = _parse_goal_seconds(row.get("goal_c"))
    if goal_c is not None:
        d["goal_marathon_c_s"] = goal_c

    if row.get("marathons_selected"):
        d["marathons_selected"] = tuple(
            s.strip() for s in re.split(r"[;,]", row["marathons_selected"]) if s.strip()
        )

    if row.get("latest_half_race"):
        d["latest_half_race_text"] = row["latest_half_race"]
    half_s = _parse_goal_seconds(row.get("latest_half_time"))
    if half_s is not None:
        d["latest_half_time_s"] = half_s
    if row.get("latest_marathon_race"):
        d["latest_marathon_race_text"] = row["latest_marathon_race"]
    mar_s = _parse_goal_seconds(row.get("latest_marathon_time"))
    if mar_s is not None:
        d["latest_marathon_time_s"] = mar_s

    arrival = _parse_date_cell(row.get("arrival_date"))
    if arrival:
        d["marathon_arrival_date"] = arrival
    departure = _parse_date_cell(row.get("departure_date"))
    if departure:
        d["marathon_departure_date"] = departure
    if row.get("carb_load"):
        d["social_carb_load"] = row["carb_load"]
    if row.get("shakeout"):
        d["social_shakeout"] = row["shakeout"]

    ts = _parse_date_cell(row.get("training_start"))
    if ts:
        d["intake_training_start_date"] = ts
    for key, field in (
        ("training_philosophy", "training_philosophy"),
        ("hard_quality_sessions_pref", "hard_quality_sessions_pref"),
        ("hard_session_intensity_pref", "hard_session_intensity_pref"),
        ("long_run_frequency_pref", "long_run_frequency_pref"),
        ("long_run_difficulty_pref", "long_run_difficulty_pref"),
    ):
        if row.get(key):
            d[field] = row[key]

    days = _parse_days_per_week(row.get("days_per_week"))
    if days is not None:
        d["days_per_week"] = days

    method = _parse_method(row.get("method_choice"))
    if method is not None:
        d["method"] = method

    if row.get("injury_notes"):
        d["intake_injury_notes"] = row["injury_notes"]
        d["injury_prone"] = _injury_prone_from_notes(row["injury_notes"])

    if row.get("races_vacations_notes"):
        d["intake_races_vacations_notes"] = row["races_vacations_notes"]
    if row.get("coaching_extras_notes"):
        d["intake_coaching_extras_notes"] = row["coaching_extras_notes"]
    if row.get("secondary_marathon_notes"):
        d["secondary_marathon_notes"] = row["secondary_marathon_notes"]

    extras: list[str] = []
    if row.get("other_notes"):
        extras.append(row["other_notes"])
    if row.get("coach_notes"):
        extras.append(f"[coach] {row['coach_notes']}")
    if row.get("long_run_day"):
        extras.append(f"long_run_day: {row['long_run_day']}")
    if extras:
        prev = (d.get("free_notes") or "").strip()
        tail = "\n\n".join(extras)
        d["free_notes"] = f"{prev}\n\n{tail}".strip() if prev else tail

    sec: list[MarathonRaceIn] = []
    n2, d2 = row.get("marathon_2_name"), row.get("marathon_2_date")
    if n2 and _parse_date_cell(d2):
        sec.append(MarathonRaceIn(name=n2.strip(), date=_parse_date_cell(d2) or ""))
    n3, d3 = row.get("marathon_3_name"), row.get("marathon_3_date")
    if n3 and _parse_date_cell(d3):
        sec.append(MarathonRaceIn(name=n3.strip(), date=_parse_date_cell(d3) or ""))
    if sec:
        d["secondary_races"] = [r.model_dump() for r in sec]

    if row.get("birthday"):
        d["birthday"] = _parse_date_cell(row["birthday"]) or row["birthday"]
    if row.get("instagram_handle"):
        d["instagram_handle"] = row["instagram_handle"]

    survey = SurveyInputs.model_validate(d)
    return survey, sid


def find_matching_rows(
    header_row: list[Any],
    data_rows: list[list[Any]],
    *,
    match_name: str | None = None,
    match_strava_id: str | None = None,
) -> list[tuple[int, dict[str, str]]]:
    """Return list of ``(1-based sheet row number, canonical_row_dict)`` matches."""
    hi = _build_header_index(header_row)
    matches: list[tuple[int, dict[str, str]]] = []
    mname = (match_name or "").strip().lower()
    msid = (match_strava_id or "").strip()
    for i, row in enumerate(data_rows):
        canon = _row_to_canonical(hi, row)
        if mname:
            fn = (
                canon.get("full_name")
                or " ".join(
                    p for p in (canon.get("first_name", ""), canon.get("last_name", "")) if p
                )
            ).lower()
            if mname not in fn and fn not in mname:
                continue
        if msid:
            got = strava_id_from_cell(canon.get("strava_id"))
            if got != msid:
                continue
        matches.append((i + 2, canon))  # 1 header + 1-based
    return matches


def pull_survey_for_athlete(
    *,
    defaults: SurveyInputs,
    spreadsheet_id: str,
    tab: str = "Intake",
    match_name: str | None = None,
    match_strava_id: str | None = None,
    service: Any = None,
) -> tuple[SurveyInputs, str | None, int]:
    """Fetch tab, find row, merge with defaults. Returns ``(survey, strava_id, sheet_row_1based)``."""
    if not match_name and not match_strava_id:
        raise ValueError("pass match_name and/or match_strava_id")
    header, data = fetch_intake_rows(spreadsheet_id, tab, service=service)
    if not header:
        raise ValueError(f"empty or missing tab {tab!r} in spreadsheet {spreadsheet_id}")
    found = find_matching_rows(header, data, match_name=match_name, match_strava_id=match_strava_id)
    if not found:
        raise ValueError(
            f"no Intake row matched name={match_name!r} strava={match_strava_id!r} in {tab!r}"
        )
    if len(found) > 1:
        names = [
            (r.get("full_name") or " ".join(p for p in (r.get("first_name", ""), r.get("last_name", "")) if p) or "?")
            for _, r in found
        ]
        raise ValueError(f"ambiguous match ({len(found)} rows): {names!r}")
    row_num, canon = found[0]
    survey, sid = canonical_row_to_survey(canon, defaults=defaults)
    return survey, sid, row_num
