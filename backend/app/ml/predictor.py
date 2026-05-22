"""Predict 1 row → sepsis risk. Stateless wrapper quanh model + buffer.

WHY pyfunc + DataFrame: model-agnostic — XGBoost, LightGBM, RandomForest
đều nhận pd.DataFrame input qua mlflow.pyfunc interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.app.ml.features import (
    PatientBuffer,
    compute_features,
    features_to_array,
)
from backend.app.ml.loader import get_model

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    sepsis_risk: float  # raw probability [0, 1]
    alert: bool  # risk >= threshold
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

    state = _buffer.update(patient_id, row)

    features = compute_features(state, current_row=row, demographics=demographics)
    x = features_to_array(features, model.feature_names)

    input_df = pd.DataFrame(x.reshape(1, -1), columns=model.feature_names)
    prediction = model.model.predict(input_df)
    risk = float(prediction[0]) if isinstance(prediction, np.ndarray) else float(prediction)

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
