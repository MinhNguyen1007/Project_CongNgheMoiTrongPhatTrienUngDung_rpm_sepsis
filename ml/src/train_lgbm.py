"""Train LightGBM sepsis early-warning model with MLflow tracking.

Pipeline prerequisites (run in order):
    python ml/src/preprocess.py       # -> data/processed/{train,val,test}.parquet
    python ml/src/build_features.py   # -> data/features/{train,val,test}.parquet

Then:
    python ml/src/train_lgbm.py --experiment sepsis-lgbm --register

Outputs (logged to MLflow):
    - params: LightGBM hyperparameters + num_boost_round
    - metrics: val_auroc, val_auprc, val_normalized_utility, best_threshold
    - artifacts: best_threshold.json, threshold_grid.csv, feature_importance.csv
    - model: registered as `MODEL_NAME` (default sepsis-lgbm-prod) if --register
"""

import argparse
import json
import logging
import os
from pathlib import Path

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from mlflow.models import infer_signature

load_dotenv()  # pick up MLFLOW_S3_ENDPOINT_URL + AWS creds from .env

# MLflow artifact store = MinIO, not LocalStack. Override with MinIO credentials
# so boto3 can authenticate when uploading to s3://mlflow/.
os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("MINIO_ROOT_USER", "minioadmin")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
from build_features import get_model_feature_columns
from sklearn.metrics import average_precision_score, roc_auc_score
from utility_score import compute_normalized_utility

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LABEL_COL = "SepsisLabel"
PATIENT_COL = "patient_id"

# LightGBM defaults tuned for imbalanced tabular data (sepsis ~2% positive).
# `is_unbalance=True` is the LightGBM equivalent of class_weight="balanced"
# (decision #2 in CLAUDE.md — no SMOTE to preserve temporal causality).
DEFAULT_PARAMS: dict = {
    "objective": "binary",
    "metric": ["auc", "average_precision"],
    "learning_rate": 0.05,
    "num_leaves": 31,
    "max_depth": -1,
    "min_data_in_leaf": 500,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "lambda_l1": 0.5,
    "lambda_l2": 0.5,
    # `scale_pos_weight=10` instead of `is_unbalance=True` (~54x): LightGBM's
    # built-in re-weighting biases probabilities so high that every non-sepsis
    # patient eventually crosses any reasonable threshold. A milder weight
    # keeps recall usable while dramatically reducing FP rate.
    "scale_pos_weight": 10.0,
    "verbosity": -1,
    "num_threads": -1,
}


def load_split(features_dir: Path, split: str) -> pd.DataFrame:
    path = features_dir / f"{split}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run preprocess.py and build_features.py first.")
    return pd.read_parquet(path)


def prepare_xy(df: pd.DataFrame, feature_cols: list[str]) -> tuple[pd.DataFrame, np.ndarray]:
    """Coerce feature columns to numeric (None -> NaN — LightGBM handles NaN)."""
    X = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    y = df[LABEL_COL].astype(int).to_numpy()
    return X, y


def tune_threshold(
    val_df: pd.DataFrame,
    val_pred_proba: np.ndarray,
    grid: np.ndarray,
    consecutive_grid: list[int],
    warmup_grid: list[int],
) -> tuple[float, int, int, float, list[dict]]:
    """Grid-search (threshold, k, warmup) that maximizes normalized utility.

    Three decision knobs are optimized jointly on the validation set:
      - ``threshold``: proba cutoff
      - ``min_consecutive`` (k): hysteresis — k consecutive hours ≥ thr
        before alarm fires (decision #6). Suppresses isolated spikes.
      - ``warmup_hours``: mute alarms in the first N hours of ICU. Rolling
        features are not yet warm; early alarms typically fall outside
        the reward window [-12h, +3h] (decision to add after session 4).
    """
    pred_df = val_df[[PATIENT_COL, LABEL_COL]].copy()
    results: list[dict] = []
    best_thr = 0.5
    best_k = 1
    best_warmup = 0
    best_util = -np.inf

    for thr in grid:
        pred_df["prediction"] = (val_pred_proba >= thr).astype(int)
        for k in consecutive_grid:
            for warmup in warmup_grid:
                u = compute_normalized_utility(
                    pred_df,
                    "prediction",
                    LABEL_COL,
                    PATIENT_COL,
                    min_consecutive=k,
                    warmup_hours=warmup,
                )
                row = {
                    "threshold": float(thr),
                    "min_consecutive": int(k),
                    "warmup_hours": int(warmup),
                    **u,
                }
                results.append(row)
                if u["normalized_utility"] > best_util:
                    best_util = float(u["normalized_utility"])
                    best_thr = float(thr)
                    best_k = int(k)
                    best_warmup = int(warmup)

    return best_thr, best_k, best_warmup, best_util, results


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LightGBM sepsis model")
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=Path("data/features"),
        help="Directory with train/val/test parquet files (output of build_features.py)",
    )
    parser.add_argument("--experiment", type=str, default="sepsis-lgbm")
    parser.add_argument(
        "--model-name",
        type=str,
        default=os.environ.get("MODEL_NAME", "sepsis-lgbm-prod"),
    )
    parser.add_argument("--num-boost-round", type=int, default=2000)
    parser.add_argument("--early-stopping", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register the trained model to MLflow Model Registry",
    )
    parser.add_argument(
        "--threshold-grid",
        type=float,
        nargs=3,
        metavar=("START", "STOP", "STEP"),
        default=[0.02, 0.95, 0.02],
        help="np.arange(start, stop, step) for threshold search",
    )
    parser.add_argument(
        "--consecutive-grid",
        type=int,
        nargs="+",
        default=[1, 2, 3, 4, 6, 8, 12, 16],
        help="Hysteresis values to search (k consecutive hours >= thr).",
    )
    parser.add_argument(
        "--warmup-grid",
        type=int,
        nargs="+",
        default=[0, 6, 12, 18, 24, 36, 48],
        help="Warmup-hours grid. Alarms in the first N hours are muted.",
    )
    parser.add_argument(
        "--drop-features",
        type=str,
        nargs="*",
        default=[],
        help="Feature names to exclude (e.g. iculos_hours HospAdmTime). "
        "Useful to prevent the model from over-relying on time-in-ICU.",
    )
    args = parser.parse_args()

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(args.experiment)
    logger.info("MLflow tracking: %s | experiment: %s", tracking_uri, args.experiment)

    feature_cols = get_model_feature_columns()
    if args.drop_features:
        dropped = [f for f in args.drop_features if f in feature_cols]
        feature_cols = [f for f in feature_cols if f not in args.drop_features]
        logger.info("Dropped features: %s", dropped)
    logger.info("Model input: %d features", len(feature_cols))

    train_df = load_split(args.features_dir, "train")
    val_df = load_split(args.features_dir, "val")
    logger.info(
        "Train: %d rows (%d patients, %.2f%% positive)",
        len(train_df),
        train_df[PATIENT_COL].nunique(),
        train_df[LABEL_COL].mean() * 100,
    )
    logger.info(
        "Val  : %d rows (%d patients, %.2f%% positive)",
        len(val_df),
        val_df[PATIENT_COL].nunique(),
        val_df[LABEL_COL].mean() * 100,
    )

    X_train, y_train = prepare_xy(train_df, feature_cols)
    X_val, y_val = prepare_xy(val_df, feature_cols)

    train_ds = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_ds = lgb.Dataset(X_val, label=y_val, reference=train_ds, feature_name=feature_cols)

    params = {**DEFAULT_PARAMS, "seed": args.seed}

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                **params,
                "num_boost_round": args.num_boost_round,
                "early_stopping": args.early_stopping,
                "n_features": len(feature_cols),
                "n_train_rows": len(train_df),
                "n_val_rows": len(val_df),
                "dropped_features": ",".join(args.drop_features) or "none",
            }
        )

        booster = lgb.train(
            params,
            train_ds,
            num_boost_round=args.num_boost_round,
            valid_sets=[train_ds, val_ds],
            valid_names=["train", "val"],
            callbacks=[
                lgb.early_stopping(args.early_stopping, verbose=True),
                lgb.log_evaluation(100),
            ],
        )

        val_pred_proba = booster.predict(X_val, num_iteration=booster.best_iteration)

        auroc = float(roc_auc_score(y_val, val_pred_proba))
        auprc = float(average_precision_score(y_val, val_pred_proba))
        mlflow.log_metric("val_auroc", auroc)
        mlflow.log_metric("val_auprc", auprc)
        mlflow.log_metric("best_iteration", int(booster.best_iteration))

        thr_grid = np.arange(*args.threshold_grid)
        best_thr, best_k, best_warmup, best_util, grid_results = tune_threshold(
            val_df,
            val_pred_proba,
            thr_grid,
            args.consecutive_grid,
            args.warmup_grid,
        )
        mlflow.log_metric("val_normalized_utility", best_util)
        mlflow.log_metric("best_threshold", best_thr)
        mlflow.log_metric("best_min_consecutive", best_k)
        mlflow.log_metric("best_warmup_hours", best_warmup)

        art_dir = Path("artifacts") / f"train_{run.info.run_id[:8]}"
        art_dir.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(grid_results).to_csv(art_dir / "threshold_grid.csv", index=False)
        (art_dir / "best_threshold.json").write_text(
            json.dumps(
                {
                    "threshold": best_thr,
                    "min_consecutive": best_k,
                    "warmup_hours": best_warmup,
                    "normalized_utility": best_util,
                },
                indent=2,
            )
        )
        (art_dir / "feature_cols.json").write_text(json.dumps(feature_cols, indent=2))

        importance = pd.DataFrame(
            {
                "feature": feature_cols,
                "gain": booster.feature_importance(importance_type="gain"),
                "split": booster.feature_importance(importance_type="split"),
            }
        ).sort_values("gain", ascending=False)
        importance.to_csv(art_dir / "feature_importance.csv", index=False)

        mlflow.log_artifacts(str(art_dir))

        signature = infer_signature(X_val.iloc[:100], val_pred_proba[:100])
        register_kwargs: dict = {}
        if args.register:
            register_kwargs["registered_model_name"] = args.model_name
        mlflow.lightgbm.log_model(
            booster,
            artifact_path="model",
            signature=signature,
            **register_kwargs,
        )

        logger.info("=" * 60)
        logger.info("Run ID      : %s", run.info.run_id)
        logger.info("Val AUROC   : %.4f", auroc)
        logger.info("Val AUPRC   : %.4f", auprc)
        logger.info(
            "Val Utility : %.4f  (threshold = %.3f, k_consec = %d, warmup = %dh)",
            best_util,
            best_thr,
            best_k,
            best_warmup,
        )
        logger.info("Top-5 features by gain:\n%s", importance.head(5).to_string(index=False))
        logger.info("=" * 60)
        logger.info(
            "To evaluate: python ml/src/evaluate.py "
            "--model-uri runs:/%s/model --threshold %.3f "
            "--min-consecutive %d --warmup-hours %d",
            run.info.run_id,
            best_thr,
            best_k,
            best_warmup,
        )


if __name__ == "__main__":
    main()
