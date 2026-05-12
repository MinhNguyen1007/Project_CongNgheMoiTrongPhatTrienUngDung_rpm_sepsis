"""Train XGBoost cho sepsis early-warning + log MLflow.

Hai cách gọi:
1. Programmatic (từ notebook): `from ml.src.train import train_model`.
2. Headless (từ CLI/scheduler): `python -m ml.src.train --max-patients 1000`.

WHY XGBoost thay vì DL: tabular + class imbalance ~2% → boosting + scale_pos_weight
hoạt động ổn định, train CPU <10 phút trên laptop. Model ~10MB, inference <10ms,
phù hợp realtime streaming.

WHY log MLflow ngay từ baseline: scheduler (weekly retrain) sẽ so sánh AUROC
của model mới với Production hiện tại — không có MLflow registry thì không
auto-promote được.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import xgboost as xgb

from ml.src.evaluate import compute_metrics
from ml.src.preprocess import (
    TARGET_COL,
    get_feature_columns,
    load_and_split,
)

logger = logging.getLogger(__name__)

# WHY scale_pos_weight: dataset có ~2% positive → XGBoost mặc định bias mạnh
# về class 0. scale_pos_weight = neg/pos cân lại gradient. Tính động trong train.
DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "binary:logistic",
    "eval_metric": ["auc", "aucpr"],
    "tree_method": "hist",  # nhanh trên CPU, chính xác tương đương exact
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "seed": 42,
}

DEFAULT_NUM_BOOST_ROUND: int = 500
DEFAULT_EARLY_STOPPING: int = 30
DEFAULT_THRESHOLD: float = 0.5
MODEL_NAME: str = "sepsis-predictor"


def _build_dmatrix(df: pd.DataFrame, feature_cols: list[str]) -> tuple[xgb.DMatrix, np.ndarray]:
    """Convert DataFrame → xgb.DMatrix. XGBoost xử lý NaN native, không cần impute."""
    X = df[feature_cols].to_numpy(dtype=np.float32)
    y = df[TARGET_COL].to_numpy(dtype=np.int8)
    return xgb.DMatrix(X, label=y, feature_names=feature_cols), y


def train_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    params: dict[str, Any] | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING,
    threshold: float = DEFAULT_THRESHOLD,
    mlflow_run_name: str | None = None,
    register_model: bool = False,
) -> tuple[xgb.Booster, dict[str, float]]:
    """Train + eval + log MLflow. Return (booster, metrics dict).

    Args:
        train_df, val_df: output của `preprocess.split_train_val()`.
        params: override DEFAULT_PARAMS (merge dict).
        register_model: True → register vào MLflow Model Registry với name
            `sepsis-predictor`. Dùng cho retrain pipeline để auto-promote.

    Returns:
        booster: XGBoost model đã train (có best_iteration).
        metrics: dict AUROC, AUPRC, Utility trên val set.
    """
    feature_cols = get_feature_columns(train_df)
    logger.info(
        "Training XGBoost on %d features, %d train rows, %d val rows",
        len(feature_cols),
        len(train_df),
        len(val_df),
    )

    # scale_pos_weight = neg/pos để cân class imbalance.
    n_pos = int(train_df[TARGET_COL].sum())
    n_neg = len(train_df) - n_pos
    spw = n_neg / max(n_pos, 1)

    p = {**DEFAULT_PARAMS, **(params or {}), "scale_pos_weight": spw}

    dtrain, _ = _build_dmatrix(train_df, feature_cols)
    dval, y_val = _build_dmatrix(val_df, feature_cols)

    with mlflow.start_run(run_name=mlflow_run_name) as run:
        mlflow.log_params(p)
        mlflow.log_param("num_boost_round", num_boost_round)
        mlflow.log_param("early_stopping_rounds", early_stopping_rounds)
        mlflow.log_param("n_train_rows", len(train_df))
        mlflow.log_param("n_val_rows", len(val_df))
        mlflow.log_param("n_features", len(feature_cols))
        mlflow.log_param("sepsis_rate_train", float(train_df[TARGET_COL].mean()))

        booster = xgb.train(
            params=p,
            dtrain=dtrain,
            num_boost_round=num_boost_round,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=50,
        )

        # Score val + compute full metrics (AUROC, AUPRC, PhysioNet Utility).
        y_score = booster.predict(dval, iteration_range=(0, booster.best_iteration + 1))
        metrics = compute_metrics(val_df, y_score, threshold=threshold)
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, int | float)})

        # Feature importance — hữu ích cho EDA + báo cáo + drift analysis.
        importance = booster.get_score(importance_type="gain")
        top10 = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
        logger.info("Top 10 features by gain: %s", top10)

        registered_name = MODEL_NAME if register_model else None
        mlflow.xgboost.log_model(
            booster,
            artifact_path="model",
            registered_model_name=registered_name,
        )
        logger.info(
            "MLflow run_id=%s, best_iter=%d, metrics=%s",
            run.info.run_id,
            booster.best_iteration,
            metrics,
        )

    return booster, metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train sepsis XGBoost baseline.")
    parser.add_argument(
        "--max-patients",
        type=int,
        default=None,
        help="Limit số patient để debug. None = full ~40k.",
    )
    parser.add_argument("--val-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--num-rounds", type=int, default=DEFAULT_NUM_BOOST_ROUND)
    parser.add_argument("--early-stopping", type=int, default=DEFAULT_EARLY_STOPPING)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--register", action="store_true", help="Register model vào MLflow Registry."
    )
    parser.add_argument(
        "--mlflow-uri",
        type=str,
        default=None,
        help="Override MLFLOW_TRACKING_URI env (vd: http://localhost:5000).",
    )
    parser.add_argument("--run-name", type=str, default=None)
    parser.add_argument(
        "--data-dirs",
        type=str,
        nargs="*",
        default=None,
        help="Override data dirs (default: ml/data/training_setA + setB).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.mlflow_uri:
        mlflow.set_tracking_uri(args.mlflow_uri)
    mlflow.set_experiment("sepsis-baseline")

    data_dirs = [Path(d) for d in args.data_dirs] if args.data_dirs else None
    train_df, val_df = load_and_split(
        data_dirs=data_dirs,
        max_patients=args.max_patients,
        val_size=args.val_size,
        random_state=args.random_state,
    )

    _, metrics = train_model(
        train_df=train_df,
        val_df=val_df,
        num_boost_round=args.num_rounds,
        early_stopping_rounds=args.early_stopping,
        threshold=args.threshold,
        mlflow_run_name=args.run_name,
        register_model=args.register,
    )
    print(f"Final val metrics: {metrics}")


if __name__ == "__main__":
    main()
