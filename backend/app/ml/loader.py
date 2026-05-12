"""Load + cache XGBoost model từ MLflow Registry.

WHY cache in-memory: predict gọi mỗi message Kafka (~1/giây/patient). Load từ
MLflow tracking server mất 200-500ms/lần → không thể load mỗi request.

WHY alias thay vì stage: MLflow 2.9+ deprecate stage (xem `models:/.../@alias`).
Khi retrain job promote version mới, alias `production` trỏ sang version mới
→ gọi `reload_model()` để swap cache.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import mlflow
import mlflow.xgboost
import xgboost as xgb
from mlflow.tracking import MlflowClient

from backend.app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """In-memory model + metadata. Immutable — reload swap whole struct."""
    booster: xgb.Booster
    feature_names: list[str]
    version: str  # MLflow version (vd: '1', '2', '3')
    threshold: float


# Single global cache. Thread-safe via _lock vì consumer thread + scheduler
# thread + FastAPI worker đều có thể đọc/swap.
_model: LoadedModel | None = None
_lock = threading.RLock()


def _load_from_registry() -> LoadedModel:
    """Fetch model từ MLflow Registry theo alias."""
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

    # Resolve alias → version. URI dạng models:/<name>@<alias>.
    mv = client.get_model_version_by_alias(
        name=settings.model_name, alias=settings.model_alias
    )
    model_uri = f"models:/{settings.model_name}@{settings.model_alias}"
    logger.info("Loading model %s (version=%s, run_id=%s)",
                model_uri, mv.version, mv.run_id)

    booster: xgb.Booster = mlflow.xgboost.load_model(model_uri)
    feature_names = list(booster.feature_names or [])
    if not feature_names:
        raise RuntimeError(
            "Loaded XGBoost model has no feature_names. Re-train with feature_names set."
        )

    return LoadedModel(
        booster=booster,
        feature_names=feature_names,
        version=str(mv.version),
        threshold=settings.model_threshold,
    )


def get_model() -> LoadedModel:
    """Trả về cached model. Lazy load lần đầu."""
    global _model
    with _lock:
        if _model is None:
            _model = _load_from_registry()
        return _model


def reload_model() -> LoadedModel:
    """Force re-fetch từ Registry. Gọi sau khi retrain promote alias."""
    global _model
    with _lock:
        new_model = _load_from_registry()
        old_version = _model.version if _model else "None"
        _model = new_model
        logger.info("Model reloaded: %s → %s", old_version, new_model.version)
        return new_model
