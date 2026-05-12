"""Predict 1 row → sepsis risk. Stateless wrapper quanh model + buffer."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import xgboost as xgb

from backend.app.ml.features import (
    PatientBuffer,
    compute_features,
    features_to_array,
)
from backend.app.ml.loader import get_model

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    sepsis_risk: float        # raw probability [0, 1]
    alert: bool               # risk >= threshold
    model_version: str
    threshold: float


# Singleton buffer cho consumer thread. FastAPI worker thread không động đến.
_buffer = PatientBuffer()


def get_buffer() -> PatientBuffer:
    return _buffer


def predict_one(
    patient_id: str,
    row: dict[str, float | None],
    demographics: dict[str, float | None],
) -> PredictionResult:
    """Update buffer + compute features + predict.

    Args:
        patient_id: vd 'p000001'.
        row: 1 giờ vital + lab + demographics (PhysioNet schema).
        demographics: Age, Gender, Unit1, Unit2, HospAdmTime, ICULOS.

    Returns:
        PredictionResult với sepsis_risk + alert flag.
    """
    model = get_model()

    # Append row vào buffer TRƯỚC khi compute features — để rolling tính kể cả
    # giờ hiện tại trong window 6h (giống preprocess offline).
    state = _buffer.update(patient_id, row)

    features = compute_features(state, current_row=row, demographics=demographics)
    x = features_to_array(features, model.feature_names)

    # XGBoost predict: cần DMatrix với feature_names match. reshape(1, -1) → 1 row.
    dmat = xgb.DMatrix(x.reshape(1, -1), feature_names=model.feature_names)
    risk = float(model.booster.predict(dmat)[0])

    # Clip [0, 1] phòng numerical issue (logistic output thường an toàn).
    risk = max(0.0, min(1.0, risk))

    return PredictionResult(
        sepsis_risk=risk,
        alert=risk >= model.threshold,
        model_version=model.version,
        threshold=model.threshold,
    )


def predict_batch(
    rows: list[tuple[str, dict[str, float | None], dict[str, float | None]]],
) -> list[PredictionResult]:
    """Batch predict cho debug/test. Production dùng predict_one trong consumer."""
    return [predict_one(pid, r, d) for pid, r, d in rows]
