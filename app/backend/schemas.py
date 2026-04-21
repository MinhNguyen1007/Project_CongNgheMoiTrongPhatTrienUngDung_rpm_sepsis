"""Pydantic schemas for API I/O."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Role = Literal["admin", "doctor", "viewer"]


class PredictRequest(BaseModel):
    patient_id: str
    iculos_hours: int = Field(ge=0)
    features: dict[str, float]


class PredictResponse(BaseModel):
    patient_id: str
    timestamp: datetime
    proba: float
    alarm: bool
    threshold: float
    consecutive_above: int
    warmup_muted: bool


class AlertEvent(BaseModel):
    """Broadcast to all WebSocket listeners when a patient fires an alarm."""

    event: str = "alert"
    patient_id: str
    timestamp: datetime
    proba: float
    iculos_hours: int


class HealthResponse(BaseModel):
    status: str
    model_uri: str
    feature_count: int
    threshold: float
    min_consecutive: int
    warmup_hours: int


# ── New REST endpoint schemas ──────────────────────────


class PatientSummary(BaseModel):
    """Summary of a patient's current status, served by GET /patients."""

    patient_id: str
    latest_proba: float
    latest_alarm: bool
    last_update: str
    iculos_hours: int


class VitalRecord(BaseModel):
    """Single hourly vital-signs snapshot."""

    timestamp: str
    hr: float | None = None
    o2sat: float | None = None
    temp: float | None = None
    sbp: float | None = None
    map: float | None = None
    dbp: float | None = None
    resp: float | None = None
    iculos_hours: int = 0


class ProbaPoint(BaseModel):
    """Single point in the sepsis probability timeline."""

    timestamp: str
    proba: float
    alarm: bool = False
    streak: int = 0


# ── Auth schemas ───────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = ""
    role: Role = "viewer"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool


class UserUpdateRequest(BaseModel):
    """Partial update for a user — admin only."""

    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


# ── Alert schemas ──────────────────────────────────────


class AlertResponse(BaseModel):
    id: int
    patient_id: str
    timestamp: datetime
    proba: float
    iculos_hours: int
    consecutive_above: int
    acknowledged: bool
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class AcknowledgeRequest(BaseModel):
    """Body for PUT /alerts/{id}/acknowledge."""
    pass  # username comes from JWT token

