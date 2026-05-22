"""Train sepsis model (XGBoost / LightGBM / RandomForest) + log MLflow.

Hai cách gọi:
1. Programmatic (từ notebook): `from ml.src.train import train_model`.
2. Headless (từ CLI/scheduler): `python -m ml.src.train --model-type xgboost`.

WHY multi-model: so sánh boosting vs ensemble → retrain chọn model tốt nhất
dựa trên AUROC trên val set.
"""

from __future__ import annotations

import argparse
import logging
from enum import Enum
from pathlib import Path
from typing import Any

import mlflow
import mlflow.lightgbm
import mlflow.pyfunc
import mlflow.sklearn
import mlflow.xgboost
import numpy as np
import pandas as pd
import xgboost as xgb
from mlflow.models import infer_signature

from ml.src.evaluate import compute_metrics
from ml.src.preprocess import (
    TARGET_COL,
    get_feature_columns,
    load_and_split,
)

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    RANDOM_FOREST = "random_forest"


XGBOOST_PARAMS: dict[str, Any] = {
    "objective": "binary:logistic",
    "eval_metric": ["auc", "aucpr"],
    "tree_method": "hist",
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "seed": 42,
}

LIGHTGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": ["auc", "average_precision"],
    "boosting_type": "gbdt",
    "max_depth": 6,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "num_threads": 1,
    "verbose": -1,
    "seed": 42,
}

RF_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_split": 10,
    "min_samples_leaf": 5,
    "max_features": "sqrt",
    "n_jobs": 1,
    "random_state": 42,
}

DEFAULT_NUM_BOOST_ROUND: int = 500
DEFAULT_EARLY_STOPPING: int = 30
DEFAULT_THRESHOLD: float = 0.5
MODEL_NAME: str = "sepsis-predictor"


def _train_xgboost(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    num_boost_round: int,
    early_stopping_rounds: int,
    scale_pos_weight: float,
) -> tuple[Any, np.ndarray]:
    """Train XGBoost booster. Return (model, y_score on val)."""
    p = {**params, "scale_pos_weight": scale_pos_weight}

    X_train = train_df[feature_cols].to_numpy(dtype=np.float32)
    y_train = train_df[TARGET_COL].to_numpy(dtype=np.int8)
    X_val = val_df[feature_cols].to_numpy(dtype=np.float32)
    y_val = val_df[TARGET_COL].to_numpy(dtype=np.int8)

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_cols)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_cols)

    booster = xgb.train(
        params=p,
        dtrain=dtrain,
        num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=early_stopping_rounds,
        verbose_eval=50,
    )
    y_score = booster.predict(dval, iteration_range=(0, booster.best_iteration + 1))
    return booster, y_score


def _train_lightgbm(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    num_boost_round: int,
    early_stopping_rounds: int,
    scale_pos_weight: float,
) -> tuple[Any, np.ndarray]:
    """Train LightGBM booster. Return (model, y_score on val)."""
    import lightgbm as lgb

    p = {**params, "scale_pos_weight": scale_pos_weight}

    X_train = train_df[feature_cols].to_numpy(dtype=np.float32)
    y_train = train_df[TARGET_COL].to_numpy(dtype=np.int8)
    X_val = val_df[feature_cols].to_numpy(dtype=np.float32)
    y_val = val_df[TARGET_COL].to_numpy(dtype=np.int8)

    ds_train = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    ds_val = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=ds_train)

    booster = lgb.train(
        params=p,
        train_set=ds_train,
        num_boost_round=num_boost_round,
        valid_sets=[ds_val],
        valid_names=["val"],
        callbacks=[lgb.early_stopping(early_stopping_rounds), lgb.log_evaluation(50)],
    )
    y_score = booster.predict(X_val, num_iteration=booster.best_iteration)
    return booster, y_score


def _train_random_forest(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    scale_pos_weight: float,
) -> tuple[Any, np.ndarray]:
    """Train RandomForest via sklearn Pipeline (SimpleImputer + RFC).

    WHY Pipeline: sklearn RF không handle NaN native → cần impute trước.
    Pipeline đảm bảo imputer chạy cả lúc predict.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    X_train = train_df[feature_cols].to_numpy(dtype=np.float32)
    y_train = train_df[TARGET_COL].to_numpy(dtype=np.int8)
    X_val = val_df[feature_cols].to_numpy(dtype=np.float32)

    p = {**params, "class_weight": {0: 1.0, 1: scale_pos_weight}}

    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(**p)),
    ])
    pipeline.fit(X_train, y_train)
    y_score = pipeline.predict_proba(X_val)[:, 1]
    return pipeline, y_score


class _SklearnProbaWrapper(mlflow.pyfunc.PythonModel):
    """Wrap sklearn Pipeline để pyfunc.predict() trả probability thay vì class label."""

    def __init__(self, pipeline: Any) -> None:
        self.pipeline = pipeline

    def predict(self, context: Any, model_input: pd.DataFrame, params: dict | None = None) -> Any:
        return self.pipeline.predict_proba(model_input)[:, 1]


def train_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    model_type: ModelType = ModelType.XGBOOST,
    params: dict[str, Any] | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING,
    threshold: float = DEFAULT_THRESHOLD,
    mlflow_run_name: str | None = None,
    register_model: bool = False,
) -> tuple[Any, dict[str, float]]:
    """Train + eval + log MLflow. Return (model, metrics dict)."""
    feature_cols = get_feature_columns(train_df)
    logger.info(
        "Training %s on %d features, %d train rows, %d val rows",
        model_type.value,
        len(feature_cols),
        len(train_df),
        len(val_df),
    )

    n_pos = int(train_df[TARGET_COL].sum())
    n_neg = len(train_df) - n_pos
    spw = n_neg / max(n_pos, 1)

    with mlflow.start_run(run_name=mlflow_run_name) as run:
        mlflow.set_tag("model_type", model_type.value)
        mlflow.log_param("model_type", model_type.value)
        mlflow.log_param("n_train_rows", len(train_df))
        mlflow.log_param("n_val_rows", len(val_df))
        mlflow.log_param("n_features", len(feature_cols))
        mlflow.log_param("sepsis_rate_train", float(train_df[TARGET_COL].mean()))

        if model_type == ModelType.XGBOOST:
            p = {**XGBOOST_PARAMS, **(params or {})}
            mlflow.log_params({k: v for k, v in p.items() if not isinstance(v, list)})
            model, y_score = _train_xgboost(
                train_df, val_df, feature_cols, p,
                num_boost_round, early_stopping_rounds, spw,
            )
        elif model_type == ModelType.LIGHTGBM:
            p = {**LIGHTGBM_PARAMS, **(params or {})}
            mlflow.log_params({k: v for k, v in p.items() if not isinstance(v, list)})
            model, y_score = _train_lightgbm(
                train_df, val_df, feature_cols, p,
                num_boost_round, early_stopping_rounds, spw,
            )
        elif model_type == ModelType.RANDOM_FOREST:
            p = {**RF_PARAMS, **(params or {})}
            mlflow.log_params(p)
            model, y_score = _train_random_forest(
                train_df, val_df, feature_cols, p, spw,
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")

        y_val = val_df[TARGET_COL].to_numpy(dtype=np.int8)
        metrics = compute_metrics(val_df, y_score, threshold=threshold)
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, int | float)})

        # Signature cho pyfunc feature name extraction trong loader.
        X_val_sample = val_df[feature_cols].head(5)
        signature = infer_signature(X_val_sample, y_score[:5])

        registered_name = MODEL_NAME if register_model else None

        if model_type == ModelType.XGBOOST:
            mlflow.xgboost.log_model(
                model, artifact_path="model",
                registered_model_name=registered_name,
                signature=signature,
            )
        elif model_type == ModelType.LIGHTGBM:
            mlflow.lightgbm.log_model(
                model, artifact_path="model",
                registered_model_name=registered_name,
                signature=signature,
            )
        elif model_type == ModelType.RANDOM_FOREST:
            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=_SklearnProbaWrapper(model),
                registered_model_name=registered_name,
                signature=signature,
            )

        logger.info(
            "MLflow run_id=%s, model_type=%s, metrics=%s",
            run.info.run_id, model_type.value, metrics,
        )

    return model, metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train sepsis model.")
    parser.add_argument(
        "--model-type",
        type=str,
        choices=[mt.value for mt in ModelType],
        default=ModelType.XGBOOST.value,
        help="Model type to train (default: xgboost).",
    )
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

    model_type = ModelType(args.model_type)
    _, metrics = train_model(
        train_df=train_df,
        val_df=val_df,
        model_type=model_type,
        num_boost_round=args.num_rounds,
        early_stopping_rounds=args.early_stopping,
        threshold=args.threshold,
        mlflow_run_name=args.run_name,
        register_model=args.register,
    )
    print(f"Final val metrics ({model_type.value}): {metrics}")


if __name__ == "__main__":
    main()
