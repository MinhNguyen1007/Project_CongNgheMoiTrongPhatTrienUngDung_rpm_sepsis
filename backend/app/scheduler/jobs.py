"""APScheduler jobs cho drift check daily + retrain weekly.

WHY subprocess thay vì in-process import + call:
1. Evidently + XGBoost train là CPU heavy → block FastAPI event loop sẽ làm
   request bị timeout, WS bị gián đoạn.
2. Subprocess isolate memory — khi train xong, OS reclaim → backend không bị
   memory bloat 1GB+ sau mỗi retrain.
3. Failure isolation — drift_detect crash không kill backend.

Trade-off: subprocess overhead (~2s startup). Chấp nhận được vì job chạy
daily/weekly, không phải request-time.

Logic:
- daily_drift_check_job (2 AM): subprocess drift_detect → parse JSON → save
  drift_report → trigger retrain nếu drift_share > settings.drift_features_threshold.
- weekly_retrain_job (Sun 3 AM): subprocess retrain → reload model in-memory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.config import settings
from backend.app.db import crud
from backend.app.db.base import AsyncSessionLocal
from backend.app.ml.loader import reload_model

logger = logging.getLogger(__name__)


async def _run_subprocess(args: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    """Spawn `python -m <module>` subprocess. Trả (returncode, stdout, stderr).

    `timeout=30 phút` đủ cho retrain ~10 phút trên laptop. Drift check ~1 phút.

    WHY blocking subprocess.run + asyncio.to_thread thay vì create_subprocess_exec:
    Windows uvicorn dùng WindowsSelectorEventLoopPolicy, loop này raise
    NotImplementedError khi gọi create_subprocess_exec (chỉ ProactorEventLoop
    support). Blocking call trong thread cross-platform OK, và job
    daily/weekly không cần native async overhead — chỉ 1 subprocess/lần.
    """
    cmd = [sys.executable, *args]
    logger.info("Spawning: %s", " ".join(cmd))

    def _run() -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Subprocess timeout after {timeout}s") from exc
        return proc.returncode, proc.stdout, proc.stderr

    return await asyncio.to_thread(_run)


async def run_drift_check(reason: str = "manual") -> dict:
    """Drift check core — subprocess + save DB + trigger retrain.

    Có thể gọi từ:
    - Scheduler (daily 2AM): reason='daily'.
    - API POST /api/drift/check: reason='manual'.
    """
    rc, stdout, stderr = await _run_subprocess(
        ["-m", "ml.src.drift_detect", "--mode", reason],
        timeout=600,
    )
    if rc != 0:
        logger.error("Drift check failed (rc=%d): %s", rc, stderr[-500:])
        raise RuntimeError(f"drift_detect exited {rc}")

    result = json.loads(stdout.strip().split("\n")[-1])
    triggered = result["drift_share"] >= settings.drift_features_threshold

    # Save report vào DB.
    target = result.get("target_period", {})
    async with AsyncSessionLocal() as session:
        await crud.create_drift_report(
            session,
            ref_period_start=datetime.now(timezone.utc),  # reference is static training data
            ref_period_end=datetime.now(timezone.utc),
            target_period_start=_parse_dt(target.get("start")),
            target_period_end=_parse_dt(target.get("end")),
            drift_share=result["drift_share"],
            triggered_retrain=triggered,
            report_json=result,
        )
        await session.commit()

    logger.info("Drift check done. share=%.3f, triggered_retrain=%s",
                result["drift_share"], triggered)

    if triggered:
        logger.info("Drift > threshold → spawning retrain job")
        # Background task — không block scheduler (drift job complete trước).
        asyncio.create_task(run_retrain(reason="drift"))

    return result


async def run_retrain(reason: str = "manual") -> dict:
    """Retrain core — subprocess + reload model nếu promote.

    WHY reload sau promote: backend cache model in-memory (loader.py), nếu
    không reload thì vẫn dùng version cũ cho đến khi restart.
    """
    rc, stdout, stderr = await _run_subprocess(
        ["-m", "ml.src.retrain", "--reason", reason],
        timeout=1800,
    )
    if rc != 0:
        logger.error("Retrain failed (rc=%d): %s", rc, stderr[-500:])
        raise RuntimeError(f"retrain exited {rc}")

    result = json.loads(stdout.strip().split("\n")[-1])

    # Mirror vào ModelVersion table — frontend ModelInfo page query từ đây.
    async with AsyncSessionLocal() as session:
        if result["promoted"]:
            await crud.demote_production_models(session)
        await crud.upsert_model_version(
            session,
            version=str(result["new_version"]),
            mlflow_run_id=result["new_run_id"],
            auroc=result["new_auroc"],
            auprc=result["new_auprc"],
            utility=result["new_utility"],
            threshold=result["new_threshold"],
            status="production" if result["promoted"] else "staging",
        )
        await session.commit()

    if result["promoted"]:
        try:
            reload_model()
            logger.info("Backend model reloaded → version=%s", result["new_version"])
        except Exception:
            logger.exception("Reload model failed after promote")

    logger.info("Retrain done. promoted=%s, new_auroc=%.4f",
                result["promoted"], result["new_auroc"])
    return result


def _parse_dt(s: str | None) -> datetime:
    if s is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


# ============================================================================
# Scheduler wiring
# ============================================================================
def create_scheduler() -> AsyncIOScheduler:
    """Build scheduler với 2 cron job. Caller responsible cho start/shutdown."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        run_drift_check,
        trigger=CronTrigger(hour=2, minute=0),  # daily 2AM UTC
        id="daily_drift_check",
        kwargs={"reason": "daily"},
        max_instances=1,         # đảm bảo không chồng job nếu run lâu
        coalesce=True,           # missed runs → merge thành 1 lần
        misfire_grace_time=300,  # 5 phút grace nếu app start trễ
    )
    scheduler.add_job(
        run_retrain,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),  # Sun 3AM UTC
        id="weekly_retrain",
        kwargs={"reason": "scheduled"},
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )

    logger.info("Scheduler configured: daily_drift_check (2AM UTC), "
                "weekly_retrain (Sun 3AM UTC)")
    return scheduler
