"""Tests for indexing Runna & historical Strava workouts into categorized catalog archetypes."""

from __future__ import annotations

from engine.workout_harvester import classify_historical_workout, harvest_activities


def test_classify_runna_activity_into_taxonomy():
    sample_runna = {
        "id": 1001,
        "name": "Runna: Over/Unders • 8mi",
        "description": "2km warm up, 3x (1km at 4:05/km, 1km at 4:25/km), 2km cool down #Runna",
        "distance": 12874.0,
        "workout_type": 3,
    }
    res = classify_historical_workout(sample_runna)
    assert res is not None
    assert res.detected_source == "Runna"
    assert res.category == "lactate_shuttle"
    assert res.matched_catalog_key == "over_unders"


def test_harvest_identifies_unindexed_runna_archetypes():
    activities = [
        {
            "id": 1002,
            "name": "Kenyan Hills • 7mi",
            "description": "25 mins continuous rolling hills at steady/threshold effort #Runna",
            "distance": 11265.0,
            "workout_type": 3,
        },
        {
            "id": 1003,
            "name": "Morning Run",
            "description": "",
            "distance": 6437.0,
            "workout_type": 0,
        },
    ]
    report = harvest_activities(activities)
    assert len(report.quality_sessions) == 1
    assert report.quality_sessions[0].category == "hill_strength"
    assert report.quality_sessions[0].matched_catalog_key is None
    assert "Kenyan Hills" in report.unindexed_candidates[0].title
