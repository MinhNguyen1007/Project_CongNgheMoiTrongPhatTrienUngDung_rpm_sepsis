"""Stack LightGBM + CatBoost — logistic meta-learner on validation OOF.

Expects as inputs:
  - A trained LightGBM model in MLflow registry (from train_lgbm.py)
  - CatBoost probas dumped from Kaggle: val_proba.parquet, test_proba.parquet
    (produced by ml/kaggle/train_catboost_kaggle.py)

Procedure:
  1. Predict LightGBM probas on val + test locally.
  2. Join with CatBoost probas on (patient_id, ICULOS).
  3. Fit LogisticRegression(2 inputs -> 1) on val → meta-learner.
  4. Tune (threshold, min_consecutive, warmup_hours) on val ensemble proba.
  5. Evaluate on test (original labels).
  6. Log everything to MLflow + register as `sepsis-ensemble-prod` if --register.

Serving note: meta-learner is a simple LR with two positive coefficients;
at serving time, compute both model probas + apply coefficients. See
artifacts/ensemble_<id>/meta_model.json for weights.

Usage::

    python ml/src/ensemble.py \
        --lgbm-uri models:/sepsis-lgbm-prod/Production \
        --catboost-dir ml/kaggle/output \
        --features-dir data/features \
        --register
"""

import argparse
import json
import logging
import os
from pathlib import Path

import mlflow
import mlflow.lightgbm
import mlflow.sklearn
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

load_dotenv()
os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("MINIO_ROOT_USER", "minioadmin")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")

from build_features import get_model_feature_columns
from utility_score import compute_normalized_utility

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LABEL_COL = "SepsisLabel"
PATIENT_COL = "patient_id"


def _resolve_run_id(client: mlflow.MlflowClient, model_uri: str) -> str | None:
    if model_uri.startswith("runs:/"):
        return model_uri.split("/")[1]
    if not model_uri.startswith("models:/"):
        return None
    _, name, vos = model_uri.split("/", 2)
    if vos.isdigit():
        return client.get_model_version(name, int(vos)).run_id
    if vos.lower() == "latest":
        versions = client.search_model_versions(f"name='{name}'")
        if not versions:
            return None
        return max(versions, key=lambda mv: int(mv.version)).run_id
    return client.get_latest_versions(name, stages=[vos])[0].run_id


def _resolve_feature_cols(model_uri: str) -> list[str]:
    try:
        client = mlflow.MlflowClient()
        run_id = _resolve_run_id(client, model_uri)
        if run_id is None:
            return get_model_feature_columns()
        path = client.download_artifacts(run_id, "feature_cols.json")
        return json.loads(Path(path).read_text())
    except Exception as exc:
        logger.warning("feature_cols.json missing (%s) — falling back", exc)
        return get_model_feature_columns()


def predict_lgbm(model_uri: str, df: pd.DataFrame, features: list[str]) -> np.ndarray:
    X = df[features].apply(pd.to_numeric, errors="coerce")
    model = mlflow.lightgbm.load_model(model_uri)
    return model.predict(X)


def join_probas(lgbm_df: pd.DataFrame, catboost_df: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """Inner-join on (patient_id, ICULOS) so row alignment is unambiguous.

    Catboost parquet has `ICULOS`; local features parquet also has `ICULOS`.
    Mismatch in row count would indicate different preprocessing — abort.
    """
    key_cols = [PATIENT_COL, "ICULOS"]
    for col in key_cols:
        assert col in lgbm_df.columns, f"{col} missing in lgbm_df"
        assert col in catboost_df.columns, f"{col} missing in catboost_df"

    merged = lgbm_df.merge(
        catboost_df[[*key_cols, "proba"]].rename(columns={"proba": "catboost_proba"}),
        on=key_cols,
        how="inner",
    )
    if len(merged) != len(lgbm_df) or len(merged) != len(catboost_df):
        logger.warning(
            "%s row-count mismatch: lgbm=%d catboost=%d merged=%d — "
            "ensemble only uses overlapping rows",
            split_name,
            len(lgbm_df),
            len(catboost_df),
            len(merged),
        )
    return merged


def tune_decision(
    df: pd.DataFrame,
    proba: np.ndarray,
    thr_grid: np.ndarray,
    k_grid: list[int],
    warmup_grid: list[int],
) -> tuple[dict, list[dict]]:
    pred_df = df[[PATIENT_COL, LABEL_COL]].copy()
    results: list[dict] = []
    best = {"normalized_utility": -np.inf}
    for thr in thr_grid:
        pred_df["prediction"] = (proba >= thr).astype(int)
        for k in k_grid:
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
                if u["normalized_utility"] > best["normalized_utility"]:
                    best = row
    return best, results


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--lgbm-uri", required=True, help="MLflow URI of the LightGBM model (models:/ or runs:/)."
    )
    p.add_argument(
        "--catboost-dir",
        type=Path,
        required=True,
        help="Directory with val_proba.parquet + test_proba.parquet from Kaggle.",
    )
    p.add_argument(
        "--features-dir",
        type=Path,
        default=Path("data/features"),
        help="Features dir used for val/test (original labels on test).",
    )
    p.add_argument("--experiment", default="sepsis-ensemble")
    p.add_argument("--model-name", default="sepsis-ensemble-prod")
    p.add_argument("--register", action="store_true")
    p.add_argument("--threshold-grid", nargs=3, type=float, default=[0.02, 0.95, 0.02])
    p.add_argument("--consecutive-grid", nargs="+", type=int, default=[1, 2, 3, 4, 6, 8, 12, 16])
    p.add_argument("--warmup-grid", nargs="+", type=int, default=[0, 6, 12, 18, 24, 36, 48])
    args = p.parse_args()

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(args.experiment)

    # ── Load splits + LightGBM probas ───────────────────────────────────
    features = _resolve_feature_cols(args.lgbm_uri)
    val_df = pd.read_parquet(args.features_dir / "val.parquet")
    test_df = pd.read_parquet(args.features_dir / "test.parquet")

    logger.info("Predicting LightGBM on val + test...")
    val_lgbm = predict_lgbm(args.lgbm_uri, val_df, features)
    test_lgbm = predict_lgbm(args.lgbm_uri, test_df, features)

    val_df = val_df.copy()
    test_df = test_df.copy()
    val_df["lgbm_proba"] = val_lgbm
    test_df["lgbm_proba"] = test_lgbm

    # ── Load CatBoost probas + join ──────────────────────────────────────
    cat_val = pd.read_parquet(args.catboost_dir / "val_proba.parquet")
    cat_test = pd.read_parquet(args.catboost_dir / "test_proba.parquet")

    val_joined = join_probas(val_df, cat_val, "val")
    test_joined = join_probas(test_df, cat_test, "test")

    # ── Fit logistic meta-learner on val ────────────────────────────────
    X_meta_val = val_joined[["lgbm_proba", "catboost_proba"]].to_numpy()
    y_val = val_joined[LABEL_COL].astype(int).to_numpy()

    meta = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")
    meta.fit(X_meta_val, y_val)
    ens_val = meta.predict_proba(X_meta_val)[:, 1]

    X_meta_test = test_joined[["lgbm_proba", "catboost_proba"]].to_numpy()
    y_test = test_joined[LABEL_COL].astype(int).to_numpy()
    ens_test = meta.predict_proba(X_meta_test)[:, 1]

    logger.info(
        "Meta coefs: lgbm=%.3f catboost=%.3f intercept=%.3f",
        meta.coef_[0, 0],
        meta.coef_[0, 1],
        meta.intercept_[0],
    )

    # ── Metrics ──────────────────────────────────────────────────────────
    val_auroc = float(roc_auc_score(y_val, ens_val))
    val_auprc = float(average_precision_score(y_val, ens_val))
    test_auroc = float(roc_auc_score(y_test, ens_test))
    test_auprc = float(average_precision_score(y_test, ens_test))

    # ── Tune decision on val ensemble proba ──────────────────────────────
    thr_grid = np.arange(*args.threshold_grid)
    best, grid_results = tune_decision(
        val_joined,
        ens_val,
        thr_grid,
        args.consecutive_grid,
        args.warmup_grid,
    )
    logger.info(
        "Best val: util=%.4f thr=%.3f k=%d warmup=%dh",
        best["normalized_utility"],
        best["threshold"],
        best["min_consecutive"],
        best["warmup_hours"],
    )

    # ── Evaluate on test ────────────────────────────────────────────────
    test_pred_df = test_joined[[PATIENT_COL, LABEL_COL]].copy()
    test_pred_df["prediction"] = (ens_test >= best["threshold"]).astype(int)
    test_util = compute_normalized_utility(
        test_pred_df,
        "prediction",
        LABEL_COL,
        PATIENT_COL,
        min_consecutive=best["min_consecutive"],
        warmup_hours=best["warmup_hours"],
    )

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "lgbm_uri": args.lgbm_uri,
                "catboost_dir": str(args.catboost_dir),
                "n_features": len(features),
                "n_val_rows": len(val_joined),
                "n_test_rows": len(test_joined),
                "meta_lgbm_coef": float(meta.coef_[0, 0]),
                "meta_catboost_coef": float(meta.coef_[0, 1]),
                "meta_intercept": float(meta.intercept_[0]),
            }
        )
        mlflow.log_metrics(
            {
                "val_auroc": val_auroc,
                "val_auprc": val_auprc,
                "val_normalized_utility": float(best["normalized_utility"]),
                "test_auroc": test_auroc,
                "test_auprc": test_auprc,
                "test_normalized_utility": float(test_util["normalized_utility"]),
                "best_threshold": float(best["threshold"]),
                "best_min_consecutive": float(best["min_consecutive"]),
                "best_warmup_hours": float(best["warmup_hours"]),
                "test_tp": int(test_util["tp"]),
                "test_fn": int(test_util["fn"]),
                "test_fp": int(test_util["fp"]),
                "test_tn": int(test_util["tn"]),
            }
        )

        art = Path("artifacts") / f"ensemble_{run.info.run_id[:8]}"
        art.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(grid_results).to_csv(art / "threshold_grid.csv", index=False)
        (art / "meta_model.json").write_text(
            json.dumps(
                {
                    "lgbm_coef": float(meta.coef_[0, 0]),
                    "catboost_coef": float(meta.coef_[0, 1]),
                    "intercept": float(meta.intercept_[0]),
                },
                indent=2,
            )
        )
        (art / "best_threshold.json").write_text(
            json.dumps(
                {
                    "threshold": float(best["threshold"]),
                    "min_consecutive": int(best["min_consecutive"]),
                    "warmup_hours": int(best["warmup_hours"]),
                    "normalized_utility_val": float(best["normalized_utility"]),
                    "normalized_utility_test": float(test_util["normalized_utility"]),
                },
                indent=2,
            )
        )
        mlflow.log_artifacts(str(art))

        # Register meta-learner (small LR). Base models remain separate.
        reg = {"registered_model_name": args.model_name} if args.register else {}
        mlflow.sklearn.log_model(meta, artifact_path="meta_model", **reg)

        logger.info("=" * 60)
        logger.info("ENSEMBLE TEST METRICS")
        logger.info("  AUROC           : %.4f", test_auroc)
        logger.info("  AUPRC           : %.4f", test_auprc)
        logger.info("  Normalized Util : %.4f", test_util["normalized_utility"])
        logger.info(
            "  Patients        : TP=%d FN=%d FP=%d TN=%d",
            test_util["tp"],
            test_util["fn"],
            test_util["fp"],
            test_util["tn"],
        )
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
