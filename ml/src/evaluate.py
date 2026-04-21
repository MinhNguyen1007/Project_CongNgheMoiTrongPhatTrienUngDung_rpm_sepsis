"""Evaluate a trained LightGBM sepsis model on the held-out test set.

Usage:
    python ml/src/evaluate.py \
        --model-uri runs:/<run_id>/model \
        --threshold 0.35

Logs to MLflow (experiment `sepsis-lgbm-eval` by default):
    - metrics: test_auroc, test_auprc, sensitivity_at_spec_0_95,
               test_normalized_utility, test_alert_ahead_mean_h,
               confusion-matrix cell counts
    - artifacts: summary.json, shap_importance.csv, shap_summary.png,
                 roc_pr_curves.png, per_patient_results.csv
"""

import argparse
import json
import logging
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — no display needed on server
import matplotlib.pyplot as plt
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
import shap
from dotenv import load_dotenv

load_dotenv()  # pick up MLFLOW_S3_ENDPOINT_URL + AWS creds from .env

# MLflow artifact store = MinIO, not LocalStack. Override with MinIO credentials
# so boto3 can authenticate when downloading/uploading to s3://mlflow/.
os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("MINIO_ROOT_USER", "minioadmin")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
from build_features import get_model_feature_columns
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from utility_score import compute_normalized_utility

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LABEL_COL = "SepsisLabel"
PATIENT_COL = "patient_id"
ICULOS_COL = "iculos_hours"  # produced by FeatureEngineer


def _resolve_model_version(client: "mlflow.MlflowClient", name: str, vos: str):
    """Return ModelVersion. Supports numeric, stage name, or 'latest'."""
    if vos.isdigit():
        return client.get_model_version(name, int(vos))
    if vos.lower() == "latest":
        versions = client.search_model_versions(f"name='{name}'")
        if not versions:
            raise ValueError(f"No versions for model {name}")
        return max(versions, key=lambda mv: int(mv.version))
    return client.get_latest_versions(name, stages=[vos])[0]


def _run_id_from_uri(model_uri: str) -> str | None:
    try:
        client = mlflow.MlflowClient()
        if model_uri.startswith("runs:/"):
            return model_uri.split("/")[1]
        if model_uri.startswith("models:/"):
            _, name, vos = model_uri.split("/", 2)
            return _resolve_model_version(client, name, vos).run_id
    except Exception:
        return None
    return None


def _resolve_feature_cols(model_uri: str) -> list[str]:
    """Prefer feature_cols.json from the training run (may exclude dropped ones)."""
    run_id = _run_id_from_uri(model_uri)
    if run_id is None:
        return get_model_feature_columns()
    try:
        client = mlflow.MlflowClient()
        path = client.download_artifacts(run_id, "feature_cols.json")
        return json.loads(Path(path).read_text())
    except Exception as exc:
        logger.warning("feature_cols.json missing (%s) — using default 134", exc)
        return get_model_feature_columns()


def resolve_decision_params(
    model_uri: str,
    cli_threshold: float | None,
    cli_consecutive: int | None,
    cli_warmup: int | None,
) -> tuple[float, int, int]:
    """Load (threshold, min_consecutive, warmup_hours) from the training run.

    Priority per-field:
      1. CLI override
      2. `best_threshold.json` artifact in the run that produced the model
      3. Defaults (0.5, 1, 0)
    """
    threshold = cli_threshold
    consecutive = cli_consecutive
    warmup = cli_warmup

    try:
        client = mlflow.MlflowClient()
        if model_uri.startswith("runs:/"):
            run_id = model_uri.split("/")[1]
        elif model_uri.startswith("models:/"):
            _, name, vos = model_uri.split("/", 2)
            run_id = _resolve_model_version(client, name, vos).run_id
        else:
            logger.warning("Unknown URI scheme: %s — defaulting", model_uri)
            return (
                threshold if threshold is not None else 0.5,
                consecutive if consecutive is not None else 1,
                warmup if warmup is not None else 0,
            )

        path = client.download_artifacts(run_id, "best_threshold.json")
        payload = json.loads(Path(path).read_text())
        if threshold is None:
            threshold = float(payload["threshold"])
        if consecutive is None:
            consecutive = int(payload.get("min_consecutive", 1))
        if warmup is None:
            warmup = int(payload.get("warmup_hours", 0))
        logger.info(
            "Loaded decision params from run %s: thr=%.3f k=%d warmup=%dh",
            run_id,
            threshold,
            consecutive,
            warmup,
        )
    except Exception as exc:
        logger.warning("Could not load decision params (%s)", exc)

    return (
        threshold if threshold is not None else 0.5,
        consecutive if consecutive is not None else 1,
        warmup if warmup is not None else 0,
    )


def sensitivity_at_specificity(
    y_true: np.ndarray, y_proba: np.ndarray, target_spec: float = 0.95
) -> tuple[float, float]:
    """Return (sensitivity, threshold) at the requested specificity."""
    fpr, tpr, thresholds = roc_curve(y_true, y_proba)
    spec = 1.0 - fpr
    mask = spec >= target_spec
    if not mask.any():
        return 0.0, 1.0
    # Pick the highest TPR among thresholds that still meet the spec target.
    valid_tpr = np.where(mask, tpr, -1.0)
    idx = int(np.argmax(valid_tpr))
    return float(tpr[idx]), float(thresholds[idx])


def compute_per_patient_results(
    test_df: pd.DataFrame,
    y_proba: np.ndarray,
    threshold: float,
    min_consecutive: int,
    warmup_hours: int = 0,
) -> pd.DataFrame:
    """One row per patient with label, alarm info, and alert-ahead-time.

    Alarm fires only after `min_consecutive` hours with proba >= threshold,
    and only after the `warmup_hours` grace period.
    """
    from utility_score import _first_consecutive_alarm

    df = test_df[[PATIENT_COL, LABEL_COL]].copy()
    if ICULOS_COL in test_df.columns:
        df[ICULOS_COL] = test_df[ICULOS_COL].values
    else:
        df[ICULOS_COL] = np.arange(len(df))  # fallback: row order
    df["proba"] = y_proba
    df["prediction"] = (y_proba >= threshold).astype(int)

    rows: list[dict] = []
    for pid, group in df.groupby(PATIENT_COL):
        group = group.sort_values(ICULOS_COL)
        labels = group[LABEL_COL].to_numpy().astype(int)
        preds = group["prediction"].to_numpy().astype(int)
        is_sepsis = bool(labels.any())
        t_alarm = _first_consecutive_alarm(preds, min_consecutive, warmup_hours)
        has_alarm = t_alarm is not None

        t_onset = int(np.argmax(labels == 1)) if is_sepsis else None
        ahead_h = (t_onset - t_alarm) if (is_sepsis and has_alarm and t_alarm <= t_onset) else None

        rows.append(
            {
                "patient_id": pid,
                "is_sepsis": is_sepsis,
                "has_alarm": has_alarm,
                "t_onset": t_onset,
                "t_alarm": t_alarm,
                "alert_ahead_h": ahead_h,
                "max_proba": float(group["proba"].max()),
            }
        )

    return pd.DataFrame(rows)


def plot_roc_pr(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    auroc: float,
    auprc: float,
    out_path: Path,
) -> None:
    fpr, tpr, _ = roc_curve(y_true, y_proba)
    prec, rec, _ = precision_recall_curve(y_true, y_proba)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(fpr, tpr, label=f"AUROC = {auroc:.3f}", linewidth=2)
    axes[0].plot([0, 1], [0, 1], "k--", alpha=0.3)
    axes[0].set_xlabel("False Positive Rate")
    axes[0].set_ylabel("True Positive Rate")
    axes[0].set_title("ROC curve")
    axes[0].legend(loc="lower right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(rec, prec, label=f"AUPRC = {auprc:.3f}", linewidth=2)
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-Recall curve")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def compute_shap(
    model, X: pd.DataFrame, feature_cols: list[str], sample_size: int, out_dir: Path
) -> pd.DataFrame:
    """TreeSHAP on a sample, save importance CSV + summary plot."""
    n = min(sample_size, len(X))
    X_sample = X.sample(n=n, random_state=42)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)
    # For binary LightGBM, shap_values can be array or list[neg, pos]
    if isinstance(shap_values, list):
        shap_values = shap_values[1]

    mean_abs = np.abs(shap_values).mean(axis=0)
    importance = pd.DataFrame({"feature": feature_cols, "mean_abs_shap": mean_abs}).sort_values(
        "mean_abs_shap", ascending=False
    )
    importance.to_csv(out_dir / "shap_importance.csv", index=False)

    plt.figure()
    shap.summary_plot(
        shap_values,
        X_sample,
        feature_names=feature_cols,
        show=False,
        max_display=20,
    )
    plt.tight_layout()
    plt.savefig(out_dir / "shap_summary.png", dpi=120, bbox_inches="tight")
    plt.close()

    return importance


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sepsis LightGBM model")
    parser.add_argument("--features-dir", type=Path, default=Path("data/features"))
    parser.add_argument(
        "--model-uri",
        type=str,
        required=True,
        help="MLflow model URI, e.g. runs:/<id>/model or models:/sepsis-lgbm-prod/Staging",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Decision threshold. If omitted, loaded from training run's best_threshold.json.",
    )
    parser.add_argument(
        "--min-consecutive",
        type=int,
        default=None,
        help="Hysteresis k (consecutive hours >= thr). "
        "If omitted, loaded from training run's best_threshold.json.",
    )
    parser.add_argument(
        "--warmup-hours",
        type=int,
        default=None,
        help="Mute alarms in the first N hours of ICU. "
        "If omitted, loaded from training run's best_threshold.json.",
    )
    parser.add_argument("--experiment", type=str, default="sepsis-lgbm-eval")
    parser.add_argument("--shap-samples", type=int, default=5000)
    args = parser.parse_args()

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(args.experiment)

    feature_cols = _resolve_feature_cols(args.model_uri)
    logger.info("Using %d features (loaded from run artifact)", len(feature_cols))
    test_path = args.features_dir / "test.parquet"
    if not test_path.exists():
        raise FileNotFoundError(f"{test_path} not found — run build_features.py first.")

    test_df = pd.read_parquet(test_path)
    logger.info(
        "Test: %d rows | %d patients | %.2f%% positive",
        len(test_df),
        test_df[PATIENT_COL].nunique(),
        test_df[LABEL_COL].mean() * 100,
    )

    X_test = test_df[feature_cols].apply(pd.to_numeric, errors="coerce")
    y_test = test_df[LABEL_COL].astype(int).to_numpy()

    logger.info("Loading model from %s", args.model_uri)
    model = mlflow.lightgbm.load_model(args.model_uri)

    threshold, min_consec, warmup = resolve_decision_params(
        args.model_uri, args.threshold, args.min_consecutive, args.warmup_hours
    )
    logger.info(
        "Using threshold=%.4f  min_consecutive=%d  warmup=%dh",
        threshold,
        min_consec,
        warmup,
    )

    with mlflow.start_run() as run:
        mlflow.log_param("model_uri", args.model_uri)
        mlflow.log_param("threshold", threshold)
        mlflow.log_param("min_consecutive", min_consec)
        mlflow.log_param("warmup_hours", warmup)
        mlflow.log_param("shap_samples", args.shap_samples)

        y_proba = model.predict(X_test)
        y_pred = (y_proba >= threshold).astype(int)

        auroc = float(roc_auc_score(y_test, y_proba))
        auprc = float(average_precision_score(y_test, y_proba))
        sens95, thr_sens95 = sensitivity_at_specificity(y_test, y_proba, 0.95)

        mlflow.log_metric("test_auroc", auroc)
        mlflow.log_metric("test_auprc", auprc)
        mlflow.log_metric("sensitivity_at_spec_0_95", sens95)
        mlflow.log_metric("threshold_at_spec_0_95", thr_sens95)

        pred_df = test_df[[PATIENT_COL, LABEL_COL]].copy()
        pred_df["prediction"] = y_pred
        util = compute_normalized_utility(
            pred_df,
            "prediction",
            LABEL_COL,
            PATIENT_COL,
            min_consecutive=min_consec,
            warmup_hours=warmup,
        )
        for k, v in util.items():
            mlflow.log_metric(f"test_{k}", float(v))

        # Hourly CM — raw threshold, no hysteresis (diagnostic only).
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        mlflow.log_metric("test_cm_tn", int(tn))
        mlflow.log_metric("test_cm_fp", int(fp))
        mlflow.log_metric("test_cm_fn", int(fn))
        mlflow.log_metric("test_cm_tp", int(tp))

        art_dir = Path("artifacts") / f"eval_{run.info.run_id[:8]}"
        art_dir.mkdir(parents=True, exist_ok=True)

        per_patient = compute_per_patient_results(test_df, y_proba, threshold, min_consec, warmup)
        per_patient.to_csv(art_dir / "per_patient_results.csv", index=False)

        ahead = per_patient["alert_ahead_h"].dropna().to_numpy()
        if len(ahead) > 0:
            mlflow.log_metric("test_alert_ahead_mean_h", float(np.mean(ahead)))
            mlflow.log_metric("test_alert_ahead_median_h", float(np.median(ahead)))
            mlflow.log_metric("test_alert_ahead_n_patients", len(ahead))

        plot_roc_pr(y_test, y_proba, auroc, auprc, art_dir / "roc_pr_curves.png")

        logger.info("Computing SHAP (%d samples)...", args.shap_samples)
        shap_imp = compute_shap(model, X_test, feature_cols, args.shap_samples, art_dir)

        summary = {
            "model_uri": args.model_uri,
            "threshold": threshold,
            "min_consecutive": min_consec,
            "warmup_hours": warmup,
            "test_auroc": auroc,
            "test_auprc": auprc,
            "sensitivity_at_spec_0_95": sens95,
            "normalized_utility": float(util["normalized_utility"]),
            "raw_utility": float(util["raw_utility"]),
            "confusion_matrix": {
                "tn": int(tn),
                "fp": int(fp),
                "fn": int(fn),
                "tp": int(tp),
            },
            "patient_counts": {
                "tp": int(util["tp"]),
                "fn": int(util["fn"]),
                "fp": int(util["fp"]),
                "tn": int(util["tn"]),
            },
            "alert_ahead_mean_h": float(np.mean(ahead)) if len(ahead) > 0 else None,
            "alert_ahead_median_h": float(np.median(ahead)) if len(ahead) > 0 else None,
            "top_shap_features": shap_imp.head(10).to_dict(orient="records"),
        }
        (art_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        mlflow.log_artifacts(str(art_dir))

        logger.info("=" * 60)
        logger.info("TEST METRICS")
        logger.info("  AUROC            : %.4f", auroc)
        logger.info("  AUPRC            : %.4f", auprc)
        logger.info("  Sens @ Spec=0.95 : %.4f  (thr=%.3f)", sens95, thr_sens95)
        logger.info(
            "  Normalized Util  : %.4f  (threshold=%.3f, k_consec=%d, warmup=%dh)",
            util["normalized_utility"],
            threshold,
            min_consec,
            warmup,
        )
        if len(ahead) > 0:
            logger.info(
                "  Alert-ahead-time : mean=%.1fh  median=%.1fh  (n=%d)",
                float(np.mean(ahead)),
                float(np.median(ahead)),
                len(ahead),
            )
        logger.info(
            "  Patients         : TP=%d  FN=%d  FP=%d  TN=%d",
            util["tp"],
            util["fn"],
            util["fp"],
            util["tn"],
        )
        logger.info("=" * 60)
        logger.info(
            "Top-10 features by |SHAP|:\n%s",
            shap_imp.head(10).to_string(index=False),
        )
        logger.info("Artifacts saved to %s", art_dir)


if __name__ == "__main__":
    main()
