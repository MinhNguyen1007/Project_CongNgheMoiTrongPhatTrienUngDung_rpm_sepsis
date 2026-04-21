"""Smoke tests for the PhysioNet utility score helper.

Only the cheap, deterministic sub-functions are covered here — the full
`compute_normalized_utility` needs real patient arrays and is exercised
by the training script itself.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pandas")

from ml.src.utility_score import (  # noqa: E402
    DT_EARLY,
    DT_LATE,
    DT_OPTIMAL,
    U_FN,
    U_TP_MAX,
    _first_consecutive_alarm,
    _utility_tp,
)


def test_utility_tp_no_credit_before_early_window():
    assert _utility_tp(DT_EARLY - 1) == 0.0


def test_utility_tp_max_inside_optimal_window():
    assert _utility_tp(DT_OPTIMAL) == pytest.approx(U_TP_MAX)
    assert _utility_tp(0) == pytest.approx(U_TP_MAX)
    assert _utility_tp(DT_LATE) == pytest.approx(U_TP_MAX)


def test_utility_tp_penalised_as_fn_when_too_late():
    assert _utility_tp(DT_LATE + 1) == U_FN


def test_first_consecutive_alarm_finds_correct_index():
    preds = np.array([0, 1, 0, 1, 1, 1, 0])
    # First run of 3 consecutive 1s starts at index 3
    assert _first_consecutive_alarm(preds, k=3) == 3


def test_first_consecutive_alarm_returns_none_when_no_run():
    preds = np.array([0, 1, 0, 1, 0, 1])
    assert _first_consecutive_alarm(preds, k=3) is None


def test_warmup_masks_early_predictions():
    preds = np.array([1, 1, 1, 0, 0, 1, 1, 1])
    # With warmup=3, the first three 1s are masked → alarm from index 5
    assert _first_consecutive_alarm(preds, k=3, warmup=3) == 5
