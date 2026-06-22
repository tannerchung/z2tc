"""Unit tests for ``store.intake_sheet`` (no live Google API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from store.intake_sheet import (
    _build_header_index,
    _map_header,
    _row_to_canonical,
    canonical_row_to_survey,
    find_matching_rows,
    strava_id_from_cell,
    unmapped_headers,
)
from store.models import SurveyInputs

# Live "Intake" tab headers (Zone 2 Track Club Marathon 2026), in sheet order.
LIVE_INTAKE_HEADERS = [
    "Timestamp", "Email Address", "Athlete First Name", "Athlete Last Name", "Birthday",
    "Email", "Instagram Handle", "Strava Profile Link",
    "Which marathons are you running this year?", "Which one is your primary?",
    "A Goal Time (HH:MM)", "B Goal Time (HH:MM)", "C Goal (HH:MM)",
    "What is your latest Half that you raced?", "What is your latest Half Time? (HH:MM:SS)",
    "What is your latest Marathon that you raced?", "What is your latest Marathon Time? (HH:MM:SS)",
    "When are you arriving to Chicago", "When are you arriving to your marathon?",
    "When are you departing from your marathon?", "Where are you staying?",
    "Are you down for carb loading?", "Are you down for a shakeout?",
    "How many days per week can you run?", "Injury history or current issues?",
    "Anything other notes?",
    "How many hard runs can you do a week", "Frequency of your long runs",
    "Hard run difficulty", "Difficulty of your long runs",
    "When are you starting your training?", "In general how do you want to train?",
]


@pytest.fixture
def kelly_defaults() -> SurveyInputs:
    p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "survey_kelly.json"
    return SurveyInputs.model_validate_json(p.read_text(encoding="utf-8"))


def test_strava_id_from_cell() -> None:
    assert strava_id_from_cell("https://www.strava.com/athletes/42251408") == "42251408"
    assert strava_id_from_cell("42251408") == "42251408"
    assert strava_id_from_cell("") is None


def test_canonical_row_overlays_defaults(kelly_defaults: SurveyInputs) -> None:
    row = {
        "full_name": "Kelly Example",
        "primary_marathon": "Chicago Marathon",
        "primary_date": "2026-10-11",
        "primary_goal": "3:50:00",
        "days_per_week": "5",
        "strava_id": "https://www.strava.com/athletes/99999999",
    }
    survey, sid = canonical_row_to_survey(row, defaults=kelly_defaults)
    assert sid == "99999999"
    assert survey.name == "Kelly Example"
    assert survey.race_name == "Chicago Marathon"
    assert survey.race_date == "2026-10-11"
    assert survey.goal_marathon_s == 3 * 3600 + 50 * 60
    assert survey.days_per_week == 5
    assert survey.vdot == kelly_defaults.vdot


def test_find_matching_rows_by_name() -> None:
    headers = ["Timestamp", "Email", "full_name", "strava_id", "primary_marathon"]
    data = [
        ["t", "a@b.co", "Jane Runner", "", "NYC"],
        ["t", "k@b.co", "Kelly Smith", "123", "Chicago"],
    ]
    m = find_matching_rows(headers, data, match_name="Kelly")
    assert len(m) == 1
    row_num, canon = m[0]
    assert row_num == 3
    assert "Kelly" in canon["full_name"]


def test_find_matching_rows_ambiguous_raises() -> None:
    headers = ["full_name"]
    data = [["Kelly A"], ["Kelly B"]]
    m = find_matching_rows(headers, data, match_name="Kelly")
    assert len(m) == 2


def test_live_intake_headers_fully_mapped() -> None:
    # Every meaningful column on the live form must map; none silently dropped.
    assert unmapped_headers(LIVE_INTAKE_HEADERS) == []
    keys = {_map_header(h) for h in LIVE_INTAKE_HEADERS}
    for expected in (
        "first_name", "last_name", "primary_marathon", "primary_goal", "goal_b", "goal_c",
        "latest_half_time", "days_per_week", "injury_notes", "arrival_date", "departure_date",
        "training_start", "training_philosophy",
    ):
        assert expected in keys, expected


def test_live_intake_row_to_survey(kelly_defaults: SurveyInputs) -> None:
    # A Kelly-shaped row through the real header index → SurveyInputs.
    row_vals = [
        "6/1/2026 12:50:54", "kell@gmail.com", "Kelly", "Hession", "3/13/1993",
        "kell@gmail.com", "Kellyhession_", "https://www.strava.com/athletes/42251408",
        "Chicago Marathon", "Chicago Marathon", "3:45:00", "3:48:00", "3:50:00",
        "", "1:45:00", "", "", "10/9/2026", "10/9/2026", "10/12/2026", "TBD",
        "Yes", "Yes", "5", "", "", "", "", "", "", "", "",
    ]
    hi = _build_header_index(LIVE_INTAKE_HEADERS)
    canon = _row_to_canonical(hi, row_vals)
    survey, sid = canonical_row_to_survey(canon, defaults=kelly_defaults)
    assert sid == "42251408"
    assert survey.name == "Kelly Hession"
    assert survey.race_name == "Chicago Marathon"
    assert survey.goal_marathon_s == 3 * 3600 + 45 * 60
    assert survey.goal_marathon_b_s == 3 * 3600 + 48 * 60
    assert survey.goal_marathon_c_s == 3 * 3600 + 50 * 60
    assert survey.latest_half_time_s == 1 * 3600 + 45 * 60
    assert survey.days_per_week == 5
    assert survey.marathon_arrival_date == "2026-10-09"
    assert survey.marathon_departure_date == "2026-10-12"
    # No date column on the form → race_date resolved from the official calendar.
    assert survey.race_date == "2026-10-11"
