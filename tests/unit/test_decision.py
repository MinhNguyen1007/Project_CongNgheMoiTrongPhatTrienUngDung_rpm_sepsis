"""Smoke tests for the serving-side alarm decision logic.

`decide()` must match `ml/src/utility_score._first_consecutive_alarm`
because the same hysteresis rule is used to tune the threshold offline
and to fire alarms online. If this drifts, the registered threshold
becomes meaningless.
"""

from __future__ import annotations

import pytest

pytest.importorskip("redis")

from app.backend.decision import decide


def test_no_alarm_below_threshold():
    d = decide(
        history=[0.1, 0.2, 0.1, 0.3],
        iculos_hours=20,
        threshold=0.5,
        min_consecutive=3,
        warmup_hours=0,
    )
    assert d.alarm is False
    assert d.consecutive_above == 0


def test_alarm_fires_after_k_consecutive_above_threshold():
    d = decide(
        history=[0.1, 0.6, 0.6, 0.6],
        iculos_hours=20,
        threshold=0.5,
        min_consecutive=3,
        warmup_hours=0,
    )
    assert d.alarm is True
    assert d.consecutive_above == 3


def test_streak_resets_on_dip():
    d = decide(
        history=[0.6, 0.6, 0.1, 0.6, 0.6],
        iculos_hours=20,
        threshold=0.5,
        min_consecutive=3,
        warmup_hours=0,
    )
    assert d.alarm is False
    assert d.consecutive_above == 2


def test_warmup_mutes_alarm_even_with_full_streak():
    d = decide(
        history=[0.9, 0.9, 0.9, 0.9],
        iculos_hours=2,
        threshold=0.5,
        min_consecutive=3,
        warmup_hours=6,
    )
    assert d.alarm is False
    assert d.warmup_muted is True


def test_empty_history_returns_zero_proba_no_alarm():
    d = decide(
        history=[],
        iculos_hours=10,
        threshold=0.5,
        min_consecutive=3,
        warmup_hours=0,
    )
    assert d.alarm is False
    assert d.proba == 0.0
