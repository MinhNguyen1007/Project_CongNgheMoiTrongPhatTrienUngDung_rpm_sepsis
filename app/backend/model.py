"""MLflow model loader + prediction + decision params bootstrap.

Loads the registered model once at startup. `best_threshold.json` from the
training run is used as the serving default if not overridden by env.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd

from .config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelBundle:
    model: object
    feature_cols: list[str]
    threshold: float
    min_consecutive: int
    warmup_hours: int
    run_id: str | None


def _apply_minio_creds() -> None:
    s = get_settings()
    os.environ["AWS_ACCESS_KEY_ID"] = s.minio_root_user
    os.environ["AWS_SECRET_ACCESS_KEY"] = s.minio_root_password
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = s.mlflow_s3_endpoint_url


def _resolve_run_id(client: mlflow.MlflowClient, uri: str) -> str | None:
    if uri.startswith("runs:/"):
        return uri.split("/")[1]
    if not uri.startswith("models:/"):
        return None
    _, name, vos = uri.split("/", 2)
    if vos.isdigit():
        return client.get_model_version(name, int(vos)).run_id
    if vos.lower() == "latest":
        versions = client.search_model_versions(f"name='{name}'")
        return max(versions, key=lambda mv: int(mv.version)).run_id if versions else None
    try:
        return client.get_latest_versions(name, stages=[vos])[0].run_id
    except Exception:
        versions = client.search_model_versions(f"name='{name}'")
        return max(versions, key=lambda mv: int(mv.version)).run_id if versions else None


def load_bundle() -> ModelBundle:
    s = get_settings()
    _apply_minio_creds()
    mlflow.set_tracking_uri(s.mlflow_tracking_uri)

    logger.info("Loading model from %s", s.model_uri)
    model = mlflow.lightgbm.load_model(s.model_uri)

    client = mlflow.MlflowClient()
    run_id = _resolve_run_id(client, s.model_uri)

    feature_cols: list[str] = []
    threshold = s.default_threshold
    min_consecutive = s.default_min_consecutive
    warmup_hours = s.default_warmup_hours

    if run_id:
        try:
            p = client.download_artifacts(run_id, "feature_cols.json")
            feature_cols = json.loads(Path(p).read_text())
        except Exception as exc:
            logger.warning("feature_cols.json missing: %s", exc)
        try:
            p = client.download_artifacts(run_id, "best_threshold.json")
            bt = json.loads(Path(p).read_text())
            threshold = float(bt.get("threshold", threshold))
            min_consecutive = int(bt.get("min_consecutive", min_consecutive))
            warmup_hours = int(bt.get("warmup_hours", warmup_hours))
        except Exception as exc:
            logger.warning("best_threshold.json missing: %s — using env defaults", exc)

    if not feature_cols:
        raise RuntimeError(
            "feature_cols.json is missing from the training run — "
            "backend refuses to start with an unknown feature order."
        )

    logger.info(
        "Loaded model: %d features, thr=%.3f k=%d warmup=%dh (run=%s)",
        len(feature_cols), threshold, min_consecutive, warmup_hours, run_id,
    )
    return ModelBundle(
        model=model,
        feature_cols=feature_cols,
        threshold=threshold,
        min_consecutive=min_consecutive,
        warmup_hours=warmup_hours,
        run_id=run_id,
    )


def predict_proba(bundle: ModelBundle, features: dict[str, float]) -> float:
    row = {c: features.get(c, np.nan) for c in bundle.feature_cols}
    df = pd.DataFrame([row], columns=bundle.feature_cols).apply(
        pd.to_numeric, errors="coerce"
    )
    proba = bundle.model.predict(df)
    return float(np.asarray(proba).ravel()[0])
