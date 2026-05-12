"""SQLAlchemy ORM cho 5 bảng theo schema trong root CLAUDE.md.

Quy tắc:
- Patient.id giữ string (vd: 'p000001') từ PhysioNet để dễ trace.
- (patient_id, hour) UNIQUE trên vital + prediction → idempotent khi consumer
  retry message hoặc producer gửi lại.
- lab_values JSONB (Postgres native) thay vì tách 26 cột → giảm schema bloat,
  query lab cụ thể ít, dashboard chỉ cần snapshot.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    age: Mapped[float | None] = mapped_column(Float, nullable=True)
    gender: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=F, 1=M
    unit1: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit2: Mapped[float | None] = mapped_column(Float, nullable=True)
    hosp_adm_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    vitals: Mapped[list[Vital]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Vital(Base):
    __tablename__ = "vital"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("patient.id", ondelete="CASCADE"), nullable=False
    )
    hour: Mapped[int] = mapped_column(Integer, nullable=False)  # ICULOS

    # 8 vital signs đo theo giờ (nullable vì PhysioNet có NaN).
    hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    o2sat: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    sbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    map: Mapped[float | None] = mapped_column(Float, nullable=True)
    dbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    resp: Mapped[float | None] = mapped_column(Float, nullable=True)
    etco2: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 26 lab values gộp JSONB — query ít, schema sạch.
    lab_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    sepsis_label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    patient: Mapped[Patient] = relationship(back_populates="vitals")

    __table_args__ = (
        UniqueConstraint("patient_id", "hour", name="uq_vital_patient_hour"),
        Index("ix_vital_patient_hour", "patient_id", "hour"),
    )


class Prediction(Base):
    __tablename__ = "prediction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("patient.id", ondelete="CASCADE"), nullable=False
    )
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    sepsis_risk: Mapped[float] = mapped_column(Float, nullable=False)
    # Version từ MLflow Registry (vd: '1', '2'). Track để debug regression sau retrain.
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    patient: Mapped[Patient] = relationship(back_populates="predictions")

    __table_args__ = (
        UniqueConstraint("patient_id", "hour", name="uq_prediction_patient_hour"),
        Index("ix_prediction_patient_hour", "patient_id", "hour"),
    )


class ModelVersion(Base):
    """Track lifecycle của model versions.

    Mirror của MLflow Registry — dùng để frontend show history mà không phải
    gọi MLflow API mỗi request (chậm + thêm dependency).
    """
    __tablename__ = "model_version"

    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    mlflow_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    auroc: Mapped[float | None] = mapped_column(Float, nullable=True)
    auprc: Mapped[float | None] = mapped_column(Float, nullable=True)
    utility: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    # status: 'production' | 'staging' | 'archived' (mirror MLflow alias)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="staging")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DriftReport(Base):
    """Output của Evidently drift job (daily).

    `drift_share` = tỷ lệ feature bị flag drifted. > DRIFT_FEATURES_THRESHOLD
    → trigger retrain.
    """
    __tablename__ = "drift_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ref_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    drift_share: Mapped[float] = mapped_column(Float, nullable=False)
    triggered_retrain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
