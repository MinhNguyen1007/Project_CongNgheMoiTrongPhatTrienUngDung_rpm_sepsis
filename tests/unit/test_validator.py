"""Smoke tests for the streaming record validator."""

from __future__ import annotations

from consumer.validator import validate_record


def test_record_with_all_normal_vitals_is_valid():
    ok, reason = validate_record({"HR": 80, "Temp": 37.0, "SBP": 120})
    assert ok
    assert reason == ""


def test_heart_rate_above_300_is_invalid():
    ok, reason = validate_record({"HR": 500})
    assert not ok
    assert "HR" in reason


def test_temperature_below_25_is_invalid():
    ok, reason = validate_record({"Temp": 10.0})
    assert not ok
    assert "Temp" in reason


def test_all_missing_vitals_is_invalid():
    ok, reason = validate_record({"Age": 65})
    assert not ok
    assert "null" in reason.lower()


def test_partial_missing_is_allowed_if_some_vital_present():
    ok, _ = validate_record({"HR": 80, "Temp": None, "SBP": None})
    assert ok
