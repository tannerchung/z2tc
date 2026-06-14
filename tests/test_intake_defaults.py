"""Tests for optional intake default resolution."""

from __future__ import annotations

import pytest

from engine.plan import common
from engine.plan.intake import (
    HARD_Q_ONE_OR_TWO,
    HARD_Q_TWO,
    INTENSITY_NORMAL,
    LR_DIFF_CLUB,
    LR_FREQ_WEEKLY,
    PHILOSOPHY_STEADY,
    SOCIAL_UNKNOWN,
    resolve_intake_defaults,
)
from engine.plan.models import AthleteInputs


def HMS(h, m, s=0):
    return h * 3600 + m * 60 + s


def _base(**kw):
    d = dict(
        name="Test",
        vdot=45.0,
        goal_marathon_s=HMS(3, 30),
        w_now=35.0,
        p_history=45.0,
        longest_run_mi=14.0,
        days_per_week=5,
        race_date="2026-10-10",
    )
    d.update(kw)
    return AthleteInputs(**d)


def test_defaults_fill_philosophy_and_social():
    a = resolve_intake_defaults(_base())
    assert a.training_philosophy == PHILOSOPHY_STEADY
    assert a.social_carb_load == SOCIAL_UNKNOWN
    assert a.social_shakeout == SOCIAL_UNKNOWN


def test_hard_quality_auto_pfitzinger():
    a = resolve_intake_defaults(
        _base(p_history=50.0, days_per_week=6, hard_quality_sessions_pref=None, method=None)
    )
    assert common.assign_method(a) == common.PFITZINGER
    assert a.hard_quality_sessions_pref == HARD_Q_TWO


def test_hard_quality_auto_daniels():
    a = resolve_intake_defaults(
        _base(p_history=30.0, days_per_week=4, hard_quality_sessions_pref=None, method=None)
    )
    assert common.assign_method(a) == common.DANIELS
    assert a.hard_quality_sessions_pref == HARD_Q_ONE_OR_TWO


def test_explicit_hard_quality_preserved():
    a = resolve_intake_defaults(_base(hard_quality_sessions_pref="one"))
    assert a.hard_quality_sessions_pref == "one"


def test_auto_string_resolved():
    a = resolve_intake_defaults(_base(hard_quality_sessions_pref="auto", p_history=50, days_per_week=6))
    assert a.hard_quality_sessions_pref == HARD_Q_TWO
