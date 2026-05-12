"""Patient endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import crud
from backend.app.db.base import get_db
from backend.app.schemas import PatientSummary, VitalRecord

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("", response_model=list[PatientSummary])
async def list_patients(
    hours_window: int = Query(24, ge=1, le=168),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[PatientSummary]:
    """List patients active trong N giờ qua, sort theo current_risk DESC."""
    rows = await crud.list_active_patients_with_risk(
        session, hours_window=hours_window, limit=limit
    )
    return [PatientSummary(**r) for r in rows]


@router.get("/{patient_id}/vitals", response_model=list[VitalRecord])
async def get_vitals(
    patient_id: str,
    limit: int = Query(24, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[VitalRecord]:
    """Vital history mới nhất (sort hour ASC sau khi reverse trong CRUD)."""
    vitals = await crud.get_patient_vitals(session, patient_id, limit=limit)
    if not vitals:
        raise HTTPException(status_code=404, detail=f"No vitals for patient {patient_id}")
    return [VitalRecord.model_validate(v) for v in vitals]
