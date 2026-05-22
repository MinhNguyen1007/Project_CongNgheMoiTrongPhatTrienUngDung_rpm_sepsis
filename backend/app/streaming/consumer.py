"""Kafka consumer thread — đọc patient-vitals → predict → save DB → broadcast WS.

WHY thread thay vì asyncio:
- kafka-python là sync, dùng aiokafka thì phải port nhiều logic.
- Thread + run_coroutine_threadsafe đơn giản và ổn định cho 1 consumer.

WHY 1 thread duy nhất: 1 patient = 1 partition key (key=patient_id) → cùng
patient luôn về cùng partition → KHÔNG được scale ra >1 consumer trong cùng
group nếu vẫn dùng PatientBuffer in-memory. 1 thread đủ cho ~100 patient × 1 msg/s.

Pipeline cho mỗi message:
1. Parse JSON → dict.
2. predict_one() (sync, thread-safe vì model cache có lock).
3. Submit coroutine vào main event loop: upsert patient/vital/prediction + broadcast.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from backend.app.config import settings
from backend.app.db import crud
from backend.app.db.base import AsyncSessionLocal
from backend.app.ml.predictor import predict_one
from backend.app.schemas import WSPredictionEvent
from backend.app.ws_manager import manager

logger = logging.getLogger(__name__)


async def _persist_and_broadcast(
    patient_id: str,
    hour: int,
    vitals: dict[str, Any],
    demographics: dict[str, Any],
    sepsis_label: int | None,
    sepsis_risk: float,
    alert: bool,
    model_version: str,
) -> None:
    """Async side-effect cho mỗi message: write DB + push WS."""
    async with AsyncSessionLocal() as session:
        await crud.upsert_patient(
            session,
            patient_id=patient_id,
            age=demographics.get("Age"),
            gender=int(demographics["Gender"]) if demographics.get("Gender") is not None else None,
            unit1=demographics.get("Unit1"),
            unit2=demographics.get("Unit2"),
            hosp_adm_time=demographics.get("HospAdmTime"),
        )

        # Tách vitals (8 cột) và labs (26 cột) — labs gộp vào JSONB.
        from backend.app.ml.features import LAB_COLS, VITAL_COLS  # local import tránh vòng
        from backend.app.streaming.validation import validate_vitals

        vital_only = {k: vitals.get(k) for k in VITAL_COLS}
        lab_only = {k: vitals.get(k) for k in LAB_COLS}
        is_valid = validate_vitals(vital_only)

        await crud.upsert_vital(
            session,
            patient_id=patient_id,
            hour=hour,
            vitals=vital_only,
            lab_values=lab_only,
            sepsis_label=sepsis_label,
            is_validated=is_valid,
        )
        await crud.upsert_prediction(
            session,
            patient_id=patient_id,
            hour=hour,
            sepsis_risk=sepsis_risk,
            model_version=model_version,
        )
        await session.commit()

    event = WSPredictionEvent(
        patient_id=patient_id,
        hour=hour,
        sepsis_risk=sepsis_risk,
        alert=alert,
        model_version=model_version,
        predicted_at=datetime.now(UTC),
    )
    await manager.broadcast(event.model_dump(mode="json"))


class ConsumerThread(threading.Thread):
    """Background thread: poll Kafka loop, predict, schedule async persist."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(name="kafka-consumer", daemon=True)
        self._loop = loop
        self._stop_event = threading.Event()
        self._consumer: KafkaConsumer | None = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._consumer is not None:
            # WHY close() thay vì wakeup(): kafka-python KafkaConsumer không có
            # wakeup() (chỉ KafkaProducer có). close() khiến iteration `for msg
            # in consumer` raise → break loop. finally block sẽ close lần 2,
            # idempotent.
            try:
                self._consumer.close(autocommit=True)
            except Exception:
                logger.exception("Consumer close during stop failed")

    def _connect(self, retries: int = 30) -> KafkaConsumer:
        for attempt in range(retries):
            try:
                return KafkaConsumer(
                    settings.kafka_topic_vitals,
                    bootstrap_servers=settings.kafka_bootstrap_servers,
                    group_id=settings.kafka_consumer_group,
                    # WHY earliest: dev — không muốn miss message khi backend
                    # start sau producer. Prod nên cân nhắc `latest` để skip backlog.
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    auto_commit_interval_ms=2000,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    key_deserializer=lambda k: k.decode("utf-8") if k else None,
                    # WHY consumer_timeout_ms None: chạy mãi mãi (controlled bởi _stop_event).
                    consumer_timeout_ms=float("inf"),
                )
            except NoBrokersAvailable:
                if self._stop_event.is_set():
                    raise
                logger.warning(
                    "Kafka not ready (attempt %d/%d), retry in 2s...", attempt + 1, retries
                )
                time.sleep(2)
        raise RuntimeError("Cannot connect to Kafka")

    def _process_message(self, msg: Any) -> None:
        """Parse + predict + submit async persist task."""
        try:
            payload = msg.value
            patient_id = payload["patient_id"]
            hour = payload["hour"]
            vitals = payload["vitals"]
            demographics = payload["demographics"]
            sepsis_label = payload.get("sepsis_label")
        except (KeyError, TypeError) as exc:
            logger.error("Bad message schema, skipping: %s | value=%r", exc, msg.value)
            return

        # Predict (sync, ~1ms với 117 features XGBoost).
        result = predict_one(patient_id, vitals, demographics)

        # Submit async I/O task lên main event loop (fire-and-forget).
        # WHY không await: consumer phải poll tiếp, không block. DB + WS chạy async.
        future = asyncio.run_coroutine_threadsafe(
            _persist_and_broadcast(
                patient_id=patient_id,
                hour=hour,
                vitals=vitals,
                demographics=demographics,
                sepsis_label=sepsis_label,
                sepsis_risk=result.sepsis_risk,
                alert=result.alert,
                model_version=result.model_version,
            ),
            self._loop,
        )
        # Attach callback để log lỗi nếu task crash (không block consumer).
        future.add_done_callback(_log_task_exception)

    def run(self) -> None:
        logger.info(
            "Consumer thread starting, topic=%s, group=%s",
            settings.kafka_topic_vitals,
            settings.kafka_consumer_group,
        )
        try:
            self._consumer = self._connect()
        except Exception:
            logger.exception("Consumer failed to connect, thread exiting")
            return

        logger.info("Consumer connected, polling...")
        try:
            for msg in self._consumer:
                if self._stop_event.is_set():
                    break
                self._process_message(msg)
        except Exception:
            logger.exception("Consumer loop crashed")
        finally:
            try:
                self._consumer.close()
            except Exception:
                pass
            logger.info("Consumer thread stopped")


def _log_task_exception(future: Any) -> None:
    """Callback cho run_coroutine_threadsafe — log exception nếu coroutine crash."""
    try:
        future.result(timeout=0)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Async persist/broadcast task failed")
