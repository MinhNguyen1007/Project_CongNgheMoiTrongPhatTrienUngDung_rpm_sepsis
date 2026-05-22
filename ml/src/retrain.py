"""Retrain orchestrator — pull data DB + training set → train 3 models → compare → promote best.

Workflow:
1. Load reference data từ training_setA + setB (vẫn dùng baseline data).
2. Pull DB vital trong N ngày qua (chỉ rows is_validated=TRUE).
3. Concat + feature engineering + split.
4. Train XGBoost + LightGBM + RandomForest tuần tự (tiết kiệm RAM trên EC2).
5. So sánh AUROC 3 model → chọn best.
6. Compare best AUROC vs production hiện tại.
7. Nếu tốt hơn → promote, caller POST /api/models/reload để backend swap cache.

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
from datetime import UTC, datetime, timedelta
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
    feature_engineering,
    load_psv_files,
    split_train_val,
)
from ml.src.s3_sync import ensure_data_dirs
from ml.src.train import ModelType, train_model

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIRS = [
    PROJECT_ROOT / "ml" / "data" / "training_setA",
    PROJECT_ROOT / "ml" / "data" / "training_setB",
]


async def _fetch_db_vitals(hours: int) -> pd.DataFrame:
    """Pull vitals + sepsis_label từ DB trong N giờ qua. Chỉ rows is_validated=TRUE."""
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        rows = await conn.fetch(
            """
            SELECT v.patient_id, v.hour, v.hr, v.o2sat, v.temp, v.sbp, v.map,
                   v.dbp, v.resp, v.etco2, v.lab_values, v.sepsis_label,
                   p.age, p.gender, p.unit1, p.unit2, p.hosp_adm_time
            FROM vital v
            JOIN patient p ON p.id = v.patient_id
            WHERE v.created_at >= $1
              AND v.is_validated = TRUE
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
            "HR": r["hr"],
            "O2Sat": r["o2sat"],
            "Temp": r["temp"],
            "SBP": r["sbp"],
            "MAP": r["map"],
            "DBP": r["dbp"],
            "Resp": r["resp"],
            "EtCO2": r["etco2"],
            "Age": r["age"],
            "Gender": r["gender"],
            "Unit1": r["unit1"],
            "Unit2": r["unit2"],
            "HospAdmTime": r["hosp_adm_time"],
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

    df = pd.DataFrame(data)
    df["patient_id"] = "db_" + df["patient_id"].astype(str)
    df = df[df[TARGET_COL].notna()].copy()
    df[TARGET_COL] = df[TARGET_COL].astype(int)
    return df


def _get_production_auroc() -> float | None:
    """Lấy AUROC của model production hiện tại từ MLflow run metrics."""
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    try:
        mv = client.get_model_version_by_alias(name=settings.model_name, alias=settings.model_alias)
    except Exception as exc:
        logger.warning("No production alias yet: %s", exc)
        return None

    run = client.get_run(mv.run_id)
    auroc = run.data.metrics.get("auroc")
    logger.info("Current production: version=%s, auroc=%s", mv.version, auroc)
    return float(auroc) if auroc is not None else None


async def run(reason: str, hours_from_db: int, max_patients: int | None) -> dict[str, Any]:
    """Full retrain pipeline: train 3 models → promote best."""
    logger.info("Retrain start, reason=%s, hours_from_db=%d", reason, hours_from_db)

    # 1. Load training data baseline.
    ensure_data_dirs(DEFAULT_DATA_DIRS)
    base_df = load_psv_files(DEFAULT_DATA_DIRS, max_patients=max_patients)
    logger.info(
        "Baseline data: %d rows, %d patients", len(base_df), base_df["patient_id"].nunique()
    )

    # 2. Pull DB data (chỉ validated rows).
    db_df = await _fetch_db_vitals(hours_from_db)
    n_db_rows = len(db_df)
    logger.info(
        "DB data (validated only): %d rows, %d patients",
        n_db_rows,
        db_df["patient_id"].nunique() if n_db_rows else 0,
    )

    # 3. Combine + feature engineering + split.
    combined = pd.concat([base_df, db_df], ignore_index=True) if n_db_rows else base_df
    feats = feature_engineering(combined)
    train_df, val_df = split_train_val(feats, val_size=0.2, random_state=42)
    logger.info("Train: %d rows, Val: %d rows", len(train_df), len(val_df))

    # 4. Train all 3 model types, track best.
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("sepsis-retrain")

    best_auroc = -1.0
    best_metrics: dict[str, float] = {}
    best_type: ModelType | None = None
    best_run_id: str | None = None
    results_per_model: dict[str, dict[str, float]] = {}

    for mt in ModelType:
        logger.info("--- Training %s ---", mt.value)
        try:
            model, metrics = train_model(
                train_df=train_df,
                val_df=val_df,
                model_type=mt,
                mlflow_run_name=f"retrain_{reason}_{mt.value}_{datetime.utcnow():%Y%m%d_%H%M%S}",
                register_model=True,
            )
            results_per_model[mt.value] = {
                "auroc": float(metrics["auroc"]),
                "auprc": float(metrics["auprc"]),
            }
            if metrics["auroc"] > best_auroc:
                best_auroc = metrics["auroc"]
                best_metrics = metrics
                best_type = mt
            del model
        except Exception:
            logger.exception("Failed to train %s, skipping", mt.value)
            results_per_model[mt.value] = {"error": "training failed"}

    if best_type is None:
        raise RuntimeError("All model types failed to train")

    # 5. Find the MLflow version for the best model (latest with matching model_type tag).
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    versions = client.search_model_versions(f"name='{settings.model_name}'")

    best_version = None
    for v in sorted(versions, key=lambda x: int(x.version), reverse=True):
        v_run = client.get_run(v.run_id)
        if v_run.data.tags.get("model_type") == best_type.value:
            best_version = v
            best_run_id = v.run_id
            break

    if best_version is None:
        raise RuntimeError(f"Cannot find registered version for {best_type.value}")

    new_version_num = best_version.version

    # 6. Compare + promote.
    production_auroc = _get_production_auroc()
    promoted = False
    if production_auroc is None or best_auroc > production_auroc:
        client.set_registered_model_alias(
            name=settings.model_name,
            alias=settings.model_alias,
            version=new_version_num,
        )
        promoted = True
        logger.info(
            "Promoted %s version=%s (auroc %.4f > prod %.4f)",
            best_type.value,
            new_version_num,
            best_auroc,
            production_auroc or 0,
        )
    else:
        logger.info(
            "Best model %s version=%s NOT promoted (auroc %.4f <= prod %.4f)",
            best_type.value,
            new_version_num,
            best_auroc,
            production_auroc,
        )

    del train_df, val_df, feats, combined, base_df, db_df

    return {
        "reason": reason,
        "best_model_type": best_type.value,
        "new_version": new_version_num,
        "new_run_id": best_run_id,
        "new_auroc": float(best_auroc),
        "new_auprc": float(best_metrics.get("auprc", 0)),
        "new_utility": float(best_metrics.get("utility", 0)),
        "new_threshold": float(best_metrics.get("threshold", 0)),
        "production_auroc_before": production_auroc,
        "promoted": promoted,
        "n_db_rows_added": n_db_rows,
        "results_per_model": results_per_model,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sepsis retrain pipeline (multi-model)")
    parser.add_argument("--reason", choices=["manual", "drift", "scheduled"], default="manual")
    parser.add_argument(
        "--hours-from-db",
        type=int,
        default=24 * 7,
        help="Số giờ DB data nối vào training (default: 7 ngày).",
    )
    parser.add_argument(
        "--max-patients",
        type=int,
        default=None,
        help="Limit baseline patient để train nhanh (test). None=full.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    np.random.seed(42)

    try:
        result = asyncio.run(
            run(
                reason=args.reason,
                hours_from_db=args.hours_from_db,
                max_patients=args.max_patients,
            )
        )
    except Exception:
        logger.exception("Retrain failed")
        sys.exit(1)

    print(json.dumps(result, default=str))
    logger.info(
        "Done. best=%s promoted=%s auroc=%.4f",
        result["best_model_type"],
        result["promoted"],
        result["new_auroc"],
    )


if __name__ == "__main__":
    main()
