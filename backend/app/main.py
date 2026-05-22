"""FastAPI entry point.

Lifespan:
- Startup: load model cache → start Kafka consumer thread → start scheduler.
- Shutdown: stop scheduler → stop consumer → dispose DB engine.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from backend.app.api import drift, models, patients, predictions, websocket
from backend.app.config import settings
from backend.app.db.base import engine
from backend.app.ml.loader import get_model
from backend.app.scheduler.jobs import create_scheduler
from backend.app.streaming.consumer import ConsumerThread

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info(
        "Backend starting. db=%s mlflow=%s",
        settings.database_url.split("@")[-1],  # giấu password
        settings.mlflow_tracking_uri,
    )

    # Warm cache model. Nếu MLflow chưa có model → log warning, không crash
    # (cho phép start backend trước khi train xong, tiện dev).
    try:
        m = get_model()
        logger.info("Loaded model version=%s with %d features", m.version, len(m.feature_names))
    except Exception as exc:
        logger.warning("Model load failed (will retry on first predict): %s", exc)

    # Start Kafka consumer thread. Capture current event loop để thread submit
    # coroutine ngược lại (run_coroutine_threadsafe).
    loop = asyncio.get_running_loop()
    consumer_thread = ConsumerThread(loop=loop)
    consumer_thread.start()
    logger.info("Consumer thread started")

    # Start APScheduler (drift daily + retrain weekly). Chạy chung event loop
    # với FastAPI — job dùng subprocess nên không block.
    if settings.enable_scheduler:
        scheduler = create_scheduler()
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Scheduler started (drift daily 2AM, retrain Sun 3AM)")
    else:
        app.state.scheduler = None
        logger.info("Scheduler DISABLED (ENABLE_SCHEDULER=false)")

    yield

    logger.info("Backend shutting down")
    if app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
    consumer_thread.stop()
    consumer_thread.join(timeout=10)
    await engine.dispose()


app = FastAPI(
    title="Sepsis Early-Warning API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["meta"])

# Routers
app.include_router(patients.router)
app.include_router(predictions.router)
app.include_router(models.router)
app.include_router(drift.router)
app.include_router(websocket.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
