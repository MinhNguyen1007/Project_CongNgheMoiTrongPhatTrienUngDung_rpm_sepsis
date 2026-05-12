"""Smoke test cho backend ML pipeline — KHÔNG cần Kafka.

Đọc 1 file PhysioNet PSV → iterate row-by-row → gọi predict_one().
Mục tiêu:
1. Verify schema mapping PSV → predict_one(row, demographics) đúng.
2. Verify PatientBuffer + compute_features ra đủ 117 features.
3. Verify model trả risk hợp lý (0-1, có biến thiên).
4. Optional: so sánh với batch prediction để chắc inference khớp training.

Chạy:
    python -m streaming.dev_predict_smoke
    python -m streaming.dev_predict_smoke --patient p000001 --hours 30
    python -m streaming.dev_predict_smoke --compare-batch
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from backend.app.ml.features import DEMO_COLS, LAB_COLS, VITAL_COLS
from backend.app.ml.predictor import predict_one

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _row_to_kafka_payload(row: pd.Series) -> tuple[dict, dict]:
    """Tách row PSV thành (vitals+labs, demographics) — schema cho predict_one.

    Producer sau này (T4) sẽ build payload giống y vầy rồi push lên Kafka.
    """
    vital_lab = {
        col: (None if pd.isna(row[col]) else float(row[col]))
        for col in VITAL_COLS + LAB_COLS
    }
    demographics = {
        col: (None if pd.isna(row[col]) else float(row[col]))
        for col in DEMO_COLS
    }
    return vital_lab, demographics


def run_streaming_smoke(patient_id: str, n_hours: int) -> pd.DataFrame:
    """Mô phỏng Kafka stream: predict từng giờ theo thứ tự thời gian."""
    psv_path = PROJECT_ROOT / "ml" / "data" / "training_setA" / f"{patient_id}.psv"
    if not psv_path.exists():
        raise FileNotFoundError(f"Patient file not found: {psv_path}")

    df = pd.read_csv(psv_path, sep="|").head(n_hours)
    logger.info("Streaming %d rows for patient %s", len(df), patient_id)

    results: list[dict] = []
    for _, row in df.iterrows():
        vital_lab, demographics = _row_to_kafka_payload(row)
        result = predict_one(patient_id, vital_lab, demographics)
        results.append({
            "hour": int(row["ICULOS"]),
            "sepsis_label": int(row["SepsisLabel"]),
            "risk": round(result.sepsis_risk, 4),
            "alert": result.alert,
        })

    return pd.DataFrame(results)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", default="p000001",
                        help="Patient ID (file phải tồn tại trong training_setA)")
    parser.add_argument("--hours", type=int, default=30,
                        help="Số giờ đầu để stream")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    results = run_streaming_smoke(args.patient, args.hours)
    print(results.to_string(index=False))
    print()
    print(f"Risk range: [{results['risk'].min():.4f}, {results['risk'].max():.4f}]")
    print(f"Alerts:     {results['alert'].sum()}/{len(results)}")
    print(f"True positives in window: {results['sepsis_label'].sum()}")


if __name__ == "__main__":
    main()
