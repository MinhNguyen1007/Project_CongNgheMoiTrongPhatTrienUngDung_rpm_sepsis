"""CRUD helpers — tách logic query khỏi API handler để dễ test + reuse.

Quy tắc: function nhận session, KHÔNG tự commit (caller quyết commit/rollback).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    DriftReport,
    ModelVersion,
    Patient,
    Prediction,
    Vital,
)


async def upsert_patient(
    session: AsyncSession,
    patient_id: str,
    age: float | None = None,
    gender: int | None = None,
    unit1: float | None = None,
    unit2: float | None = None,
    hosp_adm_time: float | None = None,
) -> None:
    """Idempotent insert — consumer thấy patient lần đầu thì create, sau đó skip."""
    stmt = (
        pg_insert(Patient)
        .values(
            id=patient_id,
            age=age,
            gender=gender,
            unit1=unit1,
            unit2=unit2,
            hosp_adm_time=hosp_adm_time,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)


async def upsert_vital(
    session: AsyncSession,
    patient_id: str,
    hour: int,
    vitals: dict[str, float | None],
    lab_values: dict[str, float | None] | None,
    sepsis_label: int | None,
    is_validated: bool = True,
) -> None:
    """Idempotent insert vital. Conflict trên (patient_id, hour) → update.

    WHY upsert thay vì insert thuần: Kafka không guarantee exactly-once, message
    có thể duplicate. Upsert làm consumer idempotent.
    """
    stmt = pg_insert(Vital).values(
        patient_id=patient_id,
        hour=hour,
        hr=vitals.get("HR"),
        o2sat=vitals.get("O2Sat"),
        temp=vitals.get("Temp"),
        sbp=vitals.get("SBP"),
        map=vitals.get("MAP"),
        dbp=vitals.get("DBP"),
        resp=vitals.get("Resp"),
        etco2=vitals.get("EtCO2"),
        lab_values=lab_values,
        sepsis_label=sepsis_label,
        is_validated=is_validated,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["patient_id", "hour"],
        set_={
            "hr": stmt.excluded.hr,
            "o2sat": stmt.excluded.o2sat,
            "temp": stmt.excluded.temp,
            "sbp": stmt.excluded.sbp,
            "map": stmt.excluded.map,
            "dbp": stmt.excluded.dbp,
            "resp": stmt.excluded.resp,
            "etco2": stmt.excluded.etco2,
            "lab_values": stmt.excluded.lab_values,
            "sepsis_label": stmt.excluded.sepsis_label,
            "is_validated": stmt.excluded.is_validated,
        },
    )
    await session.execute(stmt)


async def upsert_prediction(
    session: AsyncSession,
    patient_id: str,
    hour: int,
    sepsis_risk: float,
    model_version: str,
) -> None:
    """Idempotent insert prediction."""
    stmt = pg_insert(Prediction).values(
        patient_id=patient_id,
        hour=hour,
        sepsis_risk=sepsis_risk,
        model_version=model_version,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["patient_id", "hour"],
        set_={
            "sepsis_risk": stmt.excluded.sepsis_risk,
            "model_version": stmt.excluded.model_version,
        },
    )
    await session.execute(stmt)


async def list_active_patients_with_risk(
    session: AsyncSession,
    hours_window: int = 24,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Patients có vital trong N giờ qua + current_risk (prediction mới nhất).

    WHY subquery thay vì JOIN trực tiếp: cần latest prediction PER patient,
    DISTINCT ON (Postgres) là cách clean nhất.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours_window)

    # Latest prediction per patient: DISTINCT ON (patient_id) ORDER BY hour DESC.
    latest_pred = (
        select(
            Prediction.patient_id,
            Prediction.sepsis_risk,
            Prediction.hour,
            Prediction.predicted_at,
        )
        .distinct(Prediction.patient_id)
        .order_by(Prediction.patient_id, Prediction.hour.desc())
        .subquery()
    )

    stmt = (
        select(
            Patient.id,
            Patient.age,
            Patient.gender,
            latest_pred.c.sepsis_risk.label("current_risk"),
            latest_pred.c.predicted_at.label("last_updated"),
        )
        .join(latest_pred, latest_pred.c.patient_id == Patient.id)
        .where(latest_pred.c.predicted_at >= cutoff)
        .order_by(desc("current_risk"))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [dict(r._mapping) for r in result.all()]


async def get_patient_vitals(
    session: AsyncSession,
    patient_id: str,
    limit: int = 24,
) -> list[Vital]:
    """N vital records mới nhất của 1 patient (theo hour DESC)."""
    stmt = (
        select(Vital).where(Vital.patient_id == patient_id).order_by(Vital.hour.desc()).limit(limit)
    )
    result = await session.execute(stmt)
    # Reverse để frontend nhận thứ tự thời gian tăng dần (dễ plot).
    return list(reversed(result.scalars().all()))


async def get_patient_predictions(
    session: AsyncSession,
    patient_id: str,
    limit: int = 100,
) -> list[Prediction]:
    """Predictions của 1 patient, thứ tự thời gian tăng dần."""
    stmt = (
        select(Prediction)
        .where(Prediction.patient_id == patient_id)
        .order_by(Prediction.hour.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(reversed(result.scalars().all()))


async def get_high_risk_alerts(
    session: AsyncSession,
    threshold: float = 0.7,
    hours_window: int = 24,
) -> list[dict[str, Any]]:
    """Patients có latest prediction > threshold trong N giờ qua."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours_window)

    latest_pred = (
        select(Prediction)
        .distinct(Prediction.patient_id)
        .order_by(Prediction.patient_id, Prediction.hour.desc())
        .subquery()
    )

    stmt = (
        select(
            latest_pred.c.patient_id,
            latest_pred.c.hour,
            latest_pred.c.sepsis_risk,
            latest_pred.c.predicted_at,
        )
        .where(latest_pred.c.sepsis_risk >= threshold)
        .where(latest_pred.c.predicted_at >= cutoff)
        .order_by(desc(latest_pred.c.sepsis_risk))
    )
    result = await session.execute(stmt)
    return [dict(r._mapping) for r in result.all()]


async def get_production_model(session: AsyncSession) -> ModelVersion | None:
    """Model đang ở status='production'."""
    stmt = select(ModelVersion).where(ModelVersion.status == "production")
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_model_versions(session: AsyncSession, limit: int = 20) -> list[ModelVersion]:
    stmt = select(ModelVersion).order_by(desc(ModelVersion.created_at)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_drift_reports(session: AsyncSession, limit: int = 10) -> list[DriftReport]:
    stmt = select(DriftReport).order_by(desc(DriftReport.created_at)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_patients(session: AsyncSession) -> int:
    """Debug helper."""
    result = await session.execute(select(func.count()).select_from(Patient))
    return int(result.scalar_one())


# ============================================================================
# Drift + ModelVersion writes (T6)
# ============================================================================
async def create_drift_report(
    session: AsyncSession,
    ref_period_start: datetime,
    ref_period_end: datetime,
    target_period_start: datetime,
    target_period_end: datetime,
    drift_share: float,
    triggered_retrain: bool,
    report_json: dict[str, Any],
) -> DriftReport:
    """Insert drift report mới. Không upsert vì mỗi run = report riêng."""
    report = DriftReport(
        ref_period_start=ref_period_start,
        ref_period_end=ref_period_end,
        target_period_start=target_period_start,
        target_period_end=target_period_end,
        drift_share=drift_share,
        triggered_retrain=triggered_retrain,
        report_json=report_json,
    )
    session.add(report)
    await session.flush()
    return report


async def upsert_model_version(
    session: AsyncSession,
    version: str,
    mlflow_run_id: str,
    auroc: float | None = None,
    auprc: float | None = None,
    utility: float | None = None,
    threshold: float | None = None,
    status: str = "staging",
    model_type: str | None = None,
) -> None:
    """Idempotent — gọi sau khi retrain register version + promote alias.

    Khi promote 1 version mới, caller cần demote production cũ bằng cách gọi
    `demote_production_models()` trước (set status='archived').
    """
    stmt = pg_insert(ModelVersion).values(
        version=version,
        mlflow_run_id=mlflow_run_id,
        auroc=auroc,
        auprc=auprc,
        utility=utility,
        threshold=threshold,
        status=status,
        model_type=model_type,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["version"],
        set_={
            "auroc": stmt.excluded.auroc,
            "auprc": stmt.excluded.auprc,
            "utility": stmt.excluded.utility,
            "threshold": stmt.excluded.threshold,
            "status": stmt.excluded.status,
            "model_type": stmt.excluded.model_type,
        },
    )
    await session.execute(stmt)


async def demote_production_models(session: AsyncSession) -> int:
    """Set status='archived' cho mọi version đang là 'production'.

    Gọi trước upsert_model_version(status='production') để đảm bảo chỉ 1
    version đang active.
    """
    from sqlalchemy import update

    stmt = update(ModelVersion).where(ModelVersion.status == "production").values(status="archived")
    result = await session.execute(stmt)
    return result.rowcount or 0
