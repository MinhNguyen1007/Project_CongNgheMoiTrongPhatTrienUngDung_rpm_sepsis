"""Smoke tests for the streaming feature engineer.

Covers the core invariants that the rest of the pipeline relies on:
- stable feature count (131) — training/serving parity
- rolling mean is actually computed over the window
- clinical scores (qSOFA, SIRS) respect their textbook thresholds
- missing-indicator flips correctly
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from consumer.feature_engineer import FeatureEngineer

# Expected feature count:
#   8 vitals * 3 windows * 5 stats (mean/std/min/max/slope) = 120
# + 8 missing indicators
# + 3 clinical (qsofa_score, sirs_count, iculos_hours)
EXPECTED_FEATURE_COUNT = 131


def _base_record(**overrides) -> dict:
    rec = {
        "HR": 80,
        "O2Sat": 98,
        "Temp": 37.0,
        "SBP": 120,
        "MAP": 85,
        "DBP": 70,
        "Resp": 16,
        "EtCO2": 35,
        "ICULOS": 1,
    }
    rec.update(overrides)
    return rec


def test_feature_count_is_131():
    fe = FeatureEngineer()
    feats = fe.update("p1", _base_record())
    assert len(feats) == EXPECTED_FEATURE_COUNT


def test_rolling_mean_matches_manual_computation():
    fe = FeatureEngineer()
    hrs = [80, 90, 100]
    for i, hr in enumerate(hrs):
        feats = fe.update("p1", _base_record(HR=hr, ICULOS=i + 1))
    assert feats["mean_hr_6h"] == pytest.approx(sum(hrs) / len(hrs))
    assert feats["max_hr_6h"] == pytest.approx(100)
    assert feats["min_hr_6h"] == pytest.approx(80)


def test_qsofa_thresholds():
    fe = FeatureEngineer()
    # Normal vitals → qSOFA = 0
    normal = fe.update("p1", _base_record())
    assert normal["qsofa_score"] == 0

    # Hypotension (SBP<=100) + tachypnea (Resp>=22) → qSOFA = 2
    fe2 = FeatureEngineer()
    abnormal = fe2.update("p2", _base_record(SBP=90, Resp=25))
    assert abnormal["qsofa_score"] == 2


def test_sirs_counts_four_criteria():
    fe = FeatureEngineer()
    rec = _base_record(Temp=39.0, HR=110, Resp=24)
    rec["WBC"] = 15  # above 12 → SIRS +1
    feats = fe.update("p1", rec)
    # Temp>38, HR>90, Resp>20, WBC>12 → 4
    assert feats["sirs_count"] == 4


def test_missing_indicator_flips_correctly():
    fe = FeatureEngineer()
    rec = _base_record(HR=None)
    feats = fe.update("p1", rec)
    assert feats["missing_hr"] == 1
    assert feats["missing_temp"] == 0


def test_per_patient_isolation():
    """History for patient A must not leak into patient B's features."""
    fe = FeatureEngineer()
    fe.update("A", _base_record(HR=200))
    feats_b = fe.update("B", _base_record(HR=70))
    assert feats_b["mean_hr_6h"] == pytest.approx(70)
