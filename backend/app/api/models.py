"""Model registry endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import crud
from backend.app.db.base import get_db
from backend.app.ml.loader import get_model, reload_model
from backend.app.scheduler.jobs import run_retrain
from backend.app.schemas import ModelInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelInfo]:
    """History các model version đã train."""
    mvs = await crud.list_model_versions(session)
    return [ModelInfo.model_validate(m) for m in mvs]


@router.get("/production", response_model=ModelInfo)
async def get_production(session: AsyncSession = Depends(get_db)) -> ModelInfo:
    mv = await crud.get_production_model(session)
    if mv is None:
        raise HTTPException(status_code=404, detail="No production model")
    return ModelInfo.model_validate(mv)


@router.post("/reload", status_code=202)
async def reload() -> dict[str, str]:
    """Force re-fetch model từ MLflow Registry. Gọi sau retrain promote.

    WHY POST: side effect (swap cache). Trả 202 vì swap đồng bộ trong process.
    """
    m = reload_model()
    return {"status": "reloaded", "version": m.version}


@router.get("/current/info")
async def get_current_info() -> dict[str, object]:
    """Thông tin model đang load in-memory (không qua DB)."""
    m = get_model()
    return {
        "version": m.version,
        "threshold": m.threshold,
        "n_features": len(m.feature_names),
    }


@router.post("/retrain", status_code=202)
async def trigger_retrain() -> dict[str, str]:
    """Trigger retrain thủ công. Job mất ~5–10 phút (XGBoost CPU), chạy
    background — endpoint trả 202 ngay, client poll `/api/models` để check
    version mới.
    """
    asyncio.create_task(_run_retrain_safe())
    return {"status": "accepted", "reason": "manual"}


async def _run_retrain_safe() -> None:
    try:
        await run_retrain(reason="manual")
    except Exception:
        logger.exception("Manual retrain failed")
