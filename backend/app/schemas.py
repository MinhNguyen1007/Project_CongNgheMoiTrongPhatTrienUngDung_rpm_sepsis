"""Pydantic schemas cho API request/response.

Quy tắc:
- 1 schema cho mỗi endpoint output (không reuse SQLAlchemy model).
- `from_attributes=True` để parse trực tiếp từ ORM instance.
- Field naming snake_case khớp DB. Frontend TS type sẽ match (xem frontend/CLAUDE.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Patient
# ============================================================================
class PatientSummary(BaseModel):
    """List view: id + risk hiện tại + last update."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    age: float | None
    gender: int | None
    current_risk: float
    last_updated: datetime


# ============================================================================
# Vital
# ============================================================================
class VitalRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hour: int
    hr: float | None
    o2sat: float | None
    temp: float | None
    sbp: float | None
    map: float | None
    dbp: float | None
    resp: float | None
    etco2: float | None
    lab_values: dict[str, Any] | None
    sepsis_label: int | None
    is_validated: bool
    created_at: datetime


# ============================================================================
# Prediction
# ============================================================================
class PredictionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hour: int
    sepsis_risk: float
    model_version: str
    predicted_at: datetime


class AlertRecord(BaseModel):
    """Output `/predictions/alerts`. Subset của PredictionRecord."""

    patient_id: str
    hour: int
    sepsis_risk: float
    predicted_at: datetime


# ============================================================================
# Model
# ============================================================================
class ModelInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: str
    mlflow_run_id: str
    auroc: float | None
    auprc: float | None
    utility: float | None
    threshold: float | None
    model_type: str | None
    status: str
    created_at: datetime


# ============================================================================
# Drift
# ============================================================================
class DriftReportRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ref_period_start: datetime
    ref_period_end: datetime
    target_period_start: datetime
    target_period_end: datetime
    drift_share: float
    triggered_retrain: bool
    created_at: datetime


# ============================================================================
# WebSocket message
# ============================================================================
class WSPredictionEvent(BaseModel):
    """Broadcast tới frontend qua /ws/predictions."""

    type: str = Field(default="prediction", description="Discriminator cho frontend")
    patient_id: str
    hour: int
    sepsis_risk: float
    alert: bool
    model_version: str
    predicted_at: datetime
