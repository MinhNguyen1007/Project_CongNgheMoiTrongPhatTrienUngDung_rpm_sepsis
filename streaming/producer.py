"""Kafka producer — giả lập "data online" theo yêu cầu của giảng viên.

Đọc PSV file của 1 hoặc nhiều bệnh nhân, push từng hàng (= 1 giờ đo) lên Kafka
topic `patient-vitals`. Thứ tự = thứ tự thời gian (ICULOS tăng).

WHY interleave nhiều patient: trong ICU thật, vital của nhiều patient đến gần
như đồng thời. Round-robin giả lập điều này → consumer phải buffer per-patient
đúng (test thực tế PatientBuffer).

Schema message:
{
    "patient_id": "p000001",
    "hour": 1,
    "vitals": {"HR": 97.0, "O2Sat": 95.0, ...},      # 8 vitals + 26 labs (NaN → null)
    "demographics": {"Age": 83.14, "Gender": 0, ...},
    "sepsis_label": 0
}
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import time
from pathlib import Path

import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from backend.app.config import settings
from backend.app.ml.features import DEMO_COLS, LAB_COLS, VITAL_COLS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _clean_nan(x: float) -> float | None:
    """JSON không support NaN → null. Postgres column nullable đã handle."""
    if x is None:
        return None
    try:
        if math.isnan(float(x)):
            return None
    except (TypeError, ValueError):
        return None
    return float(x)


def _row_to_message(patient_id: str, row: pd.Series) -> dict:
    """Build Kafka message từ 1 row PhysioNet PSV."""
    return {
        "patient_id": patient_id,
        "hour": int(row["ICULOS"]),
        "vitals": {col: _clean_nan(row[col]) for col in VITAL_COLS + LAB_COLS},
        "demographics": {col: _clean_nan(row[col]) for col in DEMO_COLS},
        "sepsis_label": int(row["SepsisLabel"]) if not pd.isna(row["SepsisLabel"]) else None,
    }


def _connect_producer(bootstrap: str, retries: int = 30) -> KafkaProducer:
    """Retry connect — Kafka broker mất ~10-30s để ready sau docker-compose up."""
    for attempt in range(retries):
        try:
            return KafkaProducer(
                bootstrap_servers=bootstrap,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                # acks=1: leader ack đủ (1 broker dev, không có replica).
                acks=1,
                # Compress để giảm network ~3x với JSON payload.
                compression_type="gzip",
                linger_ms=10,
            )
        except NoBrokersAvailable:
            logger.warning("Kafka not ready (attempt %d/%d), retry in 2s...", attempt + 1, retries)
            time.sleep(2)
    raise RuntimeError(f"Cannot connect to Kafka at {bootstrap} after {retries} retries")


def _load_patient_files(
    data_dir: Path, patients: list[str] | None, max_patients: int | None
) -> list[Path]:
    """Resolve list file PSV theo arg."""
    if patients:
        files = [data_dir / f"{pid}.psv" for pid in patients]
        missing = [f for f in files if not f.exists()]
        if missing:
            raise FileNotFoundError(f"Patient files not found: {missing}")
        return files

    files = sorted(data_dir.glob("p*.psv"))
    if max_patients:
        files = files[:max_patients]
    return files


def stream_psv_files(
    files: list[Path],
    bootstrap: str,
    topic: str,
    rate_hz: float,
    interleave: bool,
    shuffle: bool = False,
) -> None:
    """Publish rows từ list PSV file lên Kafka.

    Args:
        files: list file .psv để stream.
        rate_hz: số message/giây ACROSS all patients (vd 10 = 10 msg/s tổng).
        interleave: True → round-robin giữa các patient (giống ICU thật).
                    False → push xong patient này mới sang patient kế.
        shuffle: True → trộn ngẫu nhiên thứ tự patient (chỉ áp dụng khi interleave=True).
    """
    producer = _connect_producer(bootstrap)
    logger.info("Connected to Kafka %s, topic=%s, rate=%.1f Hz", bootstrap, topic, rate_hz)

    # Load tất cả file vào memory (40k file × ~40 row ~ vài trăm MB max, OK cho demo).
    streams: list[tuple[str, pd.DataFrame]] = []
    for f in files:
        df = pd.read_csv(f, sep="|").sort_values("ICULOS").reset_index(drop=True)
        streams.append((f.stem, df))

    if shuffle:
        random.shuffle(streams)

    sleep_per_msg = 1.0 / rate_hz if rate_hz > 0 else 0.0
    total_sent = 0

    if interleave:
        # Round-robin: iter[i] = next row của patient i. Khi 1 patient hết thì
        # vẫn xoay vòng giữa các patient còn lại.
        iters = [(pid, iter(df.iterrows())) for pid, df in streams]
        while iters:
            still_alive: list[tuple[str, object]] = []
            for pid, it in iters:
                try:
                    _, row = next(it)
                except StopIteration:
                    continue
                msg = _row_to_message(pid, row)
                producer.send(topic, key=pid, value=msg)
                total_sent += 1
                if total_sent % 100 == 0:
                    logger.info("Sent %d messages", total_sent)
                still_alive.append((pid, it))
                if sleep_per_msg:
                    time.sleep(sleep_per_msg)
            iters = still_alive
    else:
        for pid, df in streams:
            for _, row in df.iterrows():
                msg = _row_to_message(pid, row)
                producer.send(topic, key=pid, value=msg)
                total_sent += 1
                if total_sent % 100 == 0:
                    logger.info("Sent %d messages", total_sent)
                if sleep_per_msg:
                    time.sleep(sleep_per_msg)

    producer.flush()
    producer.close()
    logger.info("Done. Total sent: %d messages", total_sent)


def main() -> None:
    parser = argparse.ArgumentParser(description="PhysioNet → Kafka producer")
    parser.add_argument(
        "--patients",
        nargs="*",
        default=None,
        help="Patient IDs cụ thể (vd: p000009 p000015). Mặc định: dùng --max-patients.",
    )
    parser.add_argument(
        "--max-patients",
        type=int,
        default=10,
        help="Số patient đầu để stream (nếu không truyền --patients).",
    )
    parser.add_argument(
        "--rate", type=float, default=10.0, help="Messages/giây tổng (across all patients)."
    )
    parser.add_argument(
        "--no-interleave",
        action="store_true",
        help="Stream tuần tự từng patient thay vì round-robin.",
    )
    parser.add_argument("--shuffle", action="store_true", help="Trộn ngẫu nhiên thứ tự patient.")
    parser.add_argument(
        "--data-dir", type=Path, default=PROJECT_ROOT / "ml" / "data" / "training_setA"
    )
    parser.add_argument("--bootstrap", type=str, default=settings.kafka_bootstrap_servers)
    parser.add_argument("--topic", type=str, default=settings.kafka_topic_vitals)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    files = _load_patient_files(args.data_dir, args.patients, args.max_patients)
    logger.info("Will stream %d patient files from %s", len(files), args.data_dir)

    stream_psv_files(
        files=files,
        bootstrap=args.bootstrap,
        topic=args.topic,
        rate_hz=args.rate,
        interleave=not args.no_interleave,
        shuffle=args.shuffle,
    )


if __name__ == "__main__":
    main()
