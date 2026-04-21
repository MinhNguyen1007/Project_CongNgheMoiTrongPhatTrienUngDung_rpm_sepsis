"""FastAPI entrypoint — inference + real-time alert broadcast + auth + alerts.

Routes:
  GET  /health                              — liveness + loaded model info
  POST /predict                             — score single patient hourly snapshot
  WS   /ws/alerts                           — push alert events to subscribed dashboards
  GET  /patients                            — list active patients from Redis
  GET  /patients/{patient_id}/vitals        — hourly vitals for chart
  GET  /patients/{patient_id}/proba_history — proba timeline for chart
  POST /auth/login                          — get JWT token
  POST /auth/register                       — create user account
  GET  /auth/me                             — current user info
  GET  /alerts                              — list persisted alerts
  PUT  /alerts/{id}/acknowledge             — acknowledge an alert

Run locally::
    uvicorn app.backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    create_access_token,
    hash_password,
    require_auth,
    require_role,
    verify_password,
)
from .config import Settings, get_settings
from .database import create_tables, get_db
from .db_models import Alert as AlertModel
from .db_models import User
from .decision import (
    append_proba,
    decide,
    get_active_patients,
    get_proba_history,
    get_vitals_history,
    record_prediction,
    store_patient_meta,
)
from .model import ModelBundle, load_bundle, predict_proba
from .schemas import (
    AlertEvent,
    AlertResponse,
    HealthResponse,
    LoginRequest,
    PatientSummary,
    PredictRequest,
    PredictResponse,
    ProbaPoint,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
    VitalRecord,
)
from .ws_manager import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.bundle = load_bundle()
    app.state.redis = redis.from_url(s.redis_url, decode_responses=True)

    # Create PostgreSQL tables
    try:
        await create_tables()
        logger.info("PostgreSQL tables ready.")
    except Exception as exc:
        logger.warning("PostgreSQL not available — auth/alerts disabled: %s", exc)

    # Seed default admin user if none exists
    try:
        from .database import async_session

        async with async_session() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            if result.scalar_one_or_none() is None:
                admin = User(
                    username="admin",
                    hashed_password=hash_password("admin123"),
                    full_name="Administrator",
                    role="admin",
                )
                db.add(admin)
                await db.commit()
                logger.info("Seeded default admin user (admin/admin123).")
    except Exception:
        pass  # DB not available — skip seed

    logger.info("Backend ready.")
    yield
    await app.state.redis.close()


app = FastAPI(title="Sepsis Early-Warning API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics (optional) ──
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    logger.info("Prometheus metrics enabled at /metrics")
except ImportError:
    logger.info("prometheus-fastapi-instrumentator not installed — /metrics disabled")


def bundle_dep() -> ModelBundle:
    return app.state.bundle


def redis_dep() -> redis.Redis:
    return app.state.redis


# ── Health ─────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health(
    bundle: ModelBundle = Depends(bundle_dep), s: Settings = Depends(get_settings)
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_uri=s.model_uri,
        feature_count=len(bundle.feature_cols),
        threshold=bundle.threshold,
        min_consecutive=bundle.min_consecutive,
        warmup_hours=bundle.warmup_hours,
    )


# ── Predict ────────────────────────────────────────────


@app.post("/predict", response_model=PredictResponse)
async def predict(
    req: PredictRequest,
    bundle: ModelBundle = Depends(bundle_dep),
    r: redis.Redis = Depends(redis_dep),
) -> PredictResponse:
    try:
        proba = predict_proba(bundle, req.features)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"prediction failed: {exc}") from exc

    history = await append_proba(r, req.patient_id, proba)
    decision = decide(
        history=history,
        iculos_hours=req.iculos_hours,
        threshold=bundle.threshold,
        min_consecutive=bundle.min_consecutive,
        warmup_hours=bundle.warmup_hours,
    )
    ts = datetime.now(UTC)
    await record_prediction(r, req.patient_id, ts.isoformat(), decision)
    await store_patient_meta(r, req.patient_id, req.iculos_hours)

    if decision.alarm:
        event = AlertEvent(
            patient_id=req.patient_id,
            timestamp=ts,
            proba=decision.proba,
            iculos_hours=req.iculos_hours,
        )
        await manager.broadcast(event.model_dump(mode="json"))

        # Persist alarm to PostgreSQL
        try:
            from .database import async_session

            async with async_session() as db:
                alert = AlertModel(
                    patient_id=req.patient_id,
                    timestamp=ts,
                    proba=decision.proba,
                    iculos_hours=req.iculos_hours,
                    consecutive_above=decision.consecutive_above,
                )
                db.add(alert)
                await db.commit()
        except Exception as exc:
            logger.warning("Failed to persist alert to DB: %s", exc)

    return PredictResponse(
        patient_id=req.patient_id,
        timestamp=ts,
        proba=decision.proba,
        alarm=decision.alarm,
        threshold=decision.threshold,
        consecutive_above=decision.consecutive_above,
        warmup_muted=decision.warmup_muted,
    )


# ── Patients REST ──────────────────────────────────────


@app.get("/patients", response_model=list[PatientSummary])
async def list_patients(
    r: redis.Redis = Depends(redis_dep),
) -> list[PatientSummary]:
    raw = await get_active_patients(r)
    return [PatientSummary(**p) for p in raw]


@app.get("/patients/{patient_id}/vitals", response_model=list[VitalRecord])
async def patient_vitals(
    patient_id: str,
    hours: int = Query(default=72, ge=1, le=168),
    r: redis.Redis = Depends(redis_dep),
) -> list[VitalRecord]:
    raw = await get_vitals_history(r, patient_id, hours=hours)
    if not raw:
        return []
    return [VitalRecord(**entry) for entry in raw]


@app.get("/patients/{patient_id}/proba_history", response_model=list[ProbaPoint])
async def patient_proba_history(
    patient_id: str,
    r: redis.Redis = Depends(redis_dep),
) -> list[ProbaPoint]:
    raw = await get_proba_history(r, patient_id)
    if not raw:
        return []
    return [ProbaPoint(**entry) for entry in raw]


# ── Auth ───────────────────────────────────────────────


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@app.post("/auth/register", response_model=UserResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=req.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@app.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(require_auth)):
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@app.get("/auth/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """List all users — admin only."""
    result = await db.execute(select(User).order_by(User.id))
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
        )
        for u in result.scalars().all()
    ]


@app.patch("/auth/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Admin update any user — role, active flag, full_name, password."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.full_name is not None:
        user.full_name = req.full_name
    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        # Prevent admin from disabling their own account
        if user.id == current_user.id and not req.is_active:
            raise HTTPException(status_code=400, detail="Cannot disable your own account")
        user.is_active = req.is_active
    if req.password is not None:
        user.hashed_password = hash_password(req.password)

    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@app.delete("/auth/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Admin delete any user except self."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return None


# ── Alerts CRUD ────────────────────────────────────────


@app.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    patient_id: str | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List persisted alerts, optionally filtered by patient or ack status."""
    q = select(AlertModel).order_by(desc(AlertModel.timestamp))
    if patient_id:
        q = q.where(AlertModel.patient_id == patient_id)
    if acknowledged is not None:
        q = q.where(AlertModel.acknowledged == acknowledged)
    q = q.limit(limit)
    result = await db.execute(q)
    alerts = result.scalars().all()
    return [
        AlertResponse(
            id=a.id,
            patient_id=a.patient_id,
            timestamp=a.timestamp,
            proba=a.proba,
            iculos_hours=a.iculos_hours,
            consecutive_above=a.consecutive_above,
            acknowledged=a.acknowledged,
            acknowledged_by=a.acknowledged_by,
            acknowledged_at=a.acknowledged_at,
        )
        for a in alerts
    ]


@app.put("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    user: User = Depends(require_role("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alert — admin or doctor only (viewer cannot)."""
    result = await db.execute(select(AlertModel).where(AlertModel.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_by = user.username
    alert.acknowledged_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(alert)
    return AlertResponse(
        id=alert.id,
        patient_id=alert.patient_id,
        timestamp=alert.timestamp,
        proba=alert.proba,
        iculos_hours=alert.iculos_hours,
        consecutive_above=alert.consecutive_above,
        acknowledged=alert.acknowledged,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
    )


# ── WebSocket ──────────────────────────────────────────


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
