"""Retrain orchestrator — pull data DB + training set → train → compare → promote.

Workflow:
1. Load reference data từ training_setA + setB (vẫn dùng baseline data).
2. Pull DB vital trong N ngày qua + sepsis_label (data "online" mới).
3. Concat + feature engineering + split.
4. Train XGBoost với cùng hyperparam baseline.
5. Compare AUROC với production hiện tại (qua MLflow alias `production`).
6. Nếu AUROC mới > production:
   - Log model với MLflow + register version mới.
   - Set alias `production` trỏ sang version mới.
   - Print JSON với new_version, metrics.
   - Caller (scheduler) sẽ POST /api/models/reload để backend swap cache.
7. Nếu không tốt hơn: log message, không promote.

CLI:
    python -m ml.src.retrain --reason manual
    python -m ml.src.retrain --reason drift --hours-from-db 168
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import asyncpg
import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from backend.app.config import settings
from ml.src.preprocess import (
    LAB_COLS,
    TARGET_COL,
    VITAL_COLS,
    feature_engineering,
    load_psv_files,
    split_train_val,
)
from ml.src.train import train_model

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIRS = [
    PROJECT_ROOT / "ml" / "data" / "training_setA",
    PROJECT_ROOT / "ml" / "data" / "training_setB",
]


async def _fetch_db_vitals(hours: int) -> pd.DataFrame:
    """Pull vitals + sepsis_label từ DB trong N giờ qua. Reshape về PhysioNet schema."""
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = await conn.fetch(
            """
            SELECT v.patient_id, v.hour, v.hr, v.o2sat, v.temp, v.sbp, v.map,
                   v.dbp, v.resp, v.etco2, v.lab_values, v.sepsis_label,
                   p.age, p.gender, p.unit1, p.unit2, p.hosp_adm_time
            FROM vital v
            JOIN patient p ON p.id = v.patient_id
            WHERE v.created_at >= $1
            ORDER BY v.patient_id, v.hour
            """,
            cutoff,
        )
    finally:
        await conn.close()

    if not rows:
        return pd.DataFrame()

    data: list[dict[str, Any]] = []
    for r in rows:
        d: dict[str, Any] = {
            "patient_id": r["patient_id"],
            "ICULOS": r["hour"],
            "HR": r["hr"], "O2Sat": r["o2sat"], "Temp": r["temp"], "SBP": r["sbp"],
            "MAP": r["map"], "DBP": r["dbp"], "Resp": r["resp"], "EtCO2": r["etco2"],
            "Age": r["age"], "Gender": r["gender"],
            "Unit1": r["unit1"], "Unit2": r["unit2"], "HospAdmTime": r["hosp_adm_time"],
            TARGET_COL: r["sepsis_label"],
        }
        labs_raw = r["lab_values"]
        if isinstance(labs_raw, str):
            labs = json.loads(labs_raw)
        elif isinstance(labs_raw, dict):
            labs = labs_raw
        else:
            labs = {}
        for lab in LAB_COLS:
            d[lab] = labs.get(lab)
        data.append(d)

    # WHY rename patient_id để khác training data (tránh patient cùng id từ DB
    # và training set bị merge sai). Prefix "db_" cho an toàn.
    df = pd.DataFrame(data)
    df["patient_id"] = "db_" + df["patient_id"].astype(str)
    # Drop rows không có target (chưa label được dùng để train).
    df = df[df[TARGET_COL].notna()].copy()
    df[TARGET_COL] = df[TARGET_COL].astype(int)
    return df


def _get_production_auroc() -> float | None:
    """Lấy AUROC của model production hiện tại từ MLflow run metrics."""
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    try:
        mv = client.get_model_version_by_alias(
            name=settings.model_name, alias=settings.model_alias
        )
    except Exception as exc:
        logger.warning("No production alias yet: %s", exc)
        return None

    run = client.get_run(mv.run_id)
    auroc = run.data.metrics.get("auroc")
    logger.info("Current production: version=%s, auroc=%s", mv.version, auroc)
    return float(auroc) if auroc is not None else None


async def run(reason: str, hours_from_db: int, max_patients: int | None) -> dict[str, Any]:
    """Full retrain pipeline. Return JSON dict."""
    logger.info("Retrain start, reason=%s, hours_from_db=%d", reason, hours_from_db)

    # 1. Load training data baseline.
    base_df = load_psv_files(DEFAULT_DATA_DIRS, max_patients=max_patients)
    logger.info("Baseline data: %d rows, %d patients",
                len(base_df), base_df["patient_id"].nunique())

    # 2. Pull DB data.
    db_df = await _fetch_db_vitals(hours_from_db)
    n_db_rows = len(db_df)
    logger.info("DB data: %d rows, %d patients",
                n_db_rows, db_df["patient_id"].nunique() if n_db_rows else 0)

    # 3. Combine (DB data nối vào sau, không thay thế baseline).
    combined = pd.concat([base_df, db_df], ignore_index=True) if n_db_rows else base_df

    # 4. Feature engineering + split.
    feats = feature_engineering(combined)
    train_df, val_df = split_train_val(feats, val_size=0.2, random_state=42)
    logger.info("Train: %d rows, Val: %d rows", len(train_df), len(val_df))

    # 5. Train + register (đăng ký luôn — sẽ promote alias nếu tốt hơn).
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("sepsis-retrain")

    booster, metrics = train_model(
        train_df=train_df,
        val_df=val_df,
        mlflow_run_name=f"retrain_{reason}_{datetime.utcnow():%Y%m%d_%H%M%S}",
        register_model=True,
    )
    new_auroc = metrics["auroc"]

    # 6. Compare + promote.
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    # Version mới nhất vừa register (newest).
    versions = client.search_model_versions(f"name='{settings.model_name}'")
    new_version = max(versions, key=lambda v: int(v.version))
    new_version_num = new_version.version

    production_auroc = _get_production_auroc()
    promoted = False
    if production_auroc is None or new_auroc > production_auroc:
        client.set_registered_model_alias(
            name=settings.model_name,
            alias=settings.model_alias,
            version=new_version_num,
        )
        promoted = True
        logger.info("Promoted version=%s (auroc %.4f > prod %.4f)",
                    new_version_num, new_auroc, production_auroc or 0)
    else:
        logger.info("New version=%s NOT promoted (auroc %.4f <= prod %.4f)",
                    new_version_num, new_auroc, production_auroc)

    # Free memory trước khi return (model nặng).
    del booster, train_df, val_df, feats, combined, base_df, db_df

    return {
        "reason": reason,
        "new_version": new_version_num,
        "new_run_id": new_version.run_id,
        "new_auroc": float(new_auroc),
        "new_auprc": float(metrics["auprc"]),
        "new_utility": float(metrics["utility"]),
        "new_threshold": float(metrics["threshold"]),
        "production_auroc_before": production_auroc,
        "promoted": promoted,
        "n_db_rows_added": n_db_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sepsis retrain pipeline")
    parser.add_argument("--reason", choices=["manual", "drift", "scheduled"],
                        default="manual")
    parser.add_argument("--hours-from-db", type=int, default=24 * 7,
                        help="Số giờ DB data nối vào training (default: 7 ngày).")
    parser.add_argument("--max-patients", type=int, default=None,
                        help="Limit baseline patient để train nhanh (test). None=full.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    # numpy random seed cho reproducibility của split (kết hợp với fixed random_state).
    np.random.seed(42)

    try:
        result = asyncio.run(run(
            reason=args.reason,
            hours_from_db=args.hours_from_db,
            max_patients=args.max_patients,
        ))
    except Exception:
        logger.exception("Retrain failed")
        sys.exit(1)

    print(json.dumps(result, default=str))
    logger.info("Done. promoted=%s, new_auroc=%.4f", result["promoted"], result["new_auroc"])


if __name__ == "__main__":
    main()
