"""Prediction endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import crud
from backend.app.db.base import get_db
from backend.app.schemas import AlertRecord, PredictionRecord

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/alerts", response_model=list[AlertRecord])
async def list_alerts(
    threshold: float | None = Query(None, ge=0.0, le=1.0),
    hours_window: int = Query(24, ge=1, le=168),
    session: AsyncSession = Depends(get_db),
) -> list[AlertRecord]:
    """Latest prediction của patients có risk > threshold."""
    thr = threshold if threshold is not None else settings.model_threshold
    rows = await crud.get_high_risk_alerts(
        session, threshold=thr, hours_window=hours_window
    )
    return [AlertRecord(**r) for r in rows]


@router.get("/{patient_id}", response_model=list[PredictionRecord])
async def get_patient_predictions(
    patient_id: str,
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[PredictionRecord]:
    preds = await crud.get_patient_predictions(session, patient_id, limit=limit)
    return [PredictionRecord.model_validate(p) for p in preds]
