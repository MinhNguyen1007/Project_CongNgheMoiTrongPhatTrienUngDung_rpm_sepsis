"""Drift report endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import crud
from backend.app.db.base import get_db
from backend.app.scheduler.jobs import run_drift_check
from backend.app.schemas import DriftReportRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drift", tags=["drift"])


@router.get("/reports", response_model=list[DriftReportRecord])
async def list_drift_reports(
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[DriftReportRecord]:
    reports = await crud.list_drift_reports(session, limit=limit)
    return [DriftReportRecord.model_validate(r) for r in reports]


@router.post("/check", status_code=202)
async def trigger_drift_check() -> dict[str, str]:
    """Trigger drift check thủ công. Job chạy background (subprocess Evidently
    có thể mất 30–60s), endpoint trả 202 ngay.
    """
    asyncio.create_task(_run_drift_safe())
    return {"status": "accepted", "reason": "manual"}


async def _run_drift_safe() -> None:
    """Wrapper để exception trong background task không silent-fail."""
    try:
        await run_drift_check(reason="manual")
    except Exception:
        logger.exception("Manual drift check failed")
