"""Load + cache model từ MLflow Registry (model-agnostic via pyfunc).

WHY pyfunc thay vì mlflow.xgboost: hỗ trợ XGBoost, LightGBM, RandomForest
qua cùng interface. predict() trả probability cho mọi model type.

WHY cache in-memory: predict gọi mỗi message Kafka (~1/giây/patient). Load từ
MLflow tracking server mất 200-500ms/lần → không thể load mỗi request.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import mlflow
import mlflow.pyfunc
from mlflow.tracking import MlflowClient

from backend.app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """In-memory model + metadata. Immutable — reload swap whole struct."""

    model: mlflow.pyfunc.PyFuncModel
    feature_names: list[str]
    version: str
    threshold: float
    model_type: str


_model: LoadedModel | None = None
_lock = threading.RLock()


def _extract_feature_names_from_model(model: mlflow.pyfunc.PyFuncModel) -> list[str]:
    """Lấy feature names từ underlying model khi không có MLflow signature."""
    try:
        impl = model._model_impl  # noqa: SLF001
        if hasattr(impl, "xgb_model"):
            return impl.xgb_model.get_booster().feature_names
        if hasattr(impl, "lgb_model"):
            return impl.lgb_model.feature_name()
        if hasattr(impl, "sk_model"):
            return list(impl.sk_model.feature_names_in_)
    except Exception as exc:
        logger.warning("Cannot extract feature names from model object: %s", exc)

    from backend.app.ml.features import _PatientState, compute_features

    dummy = compute_features(_PatientState(), {}, {})
    logger.warning("Final fallback: using compute_features() key order (%d features)", len(dummy))
    return list(dummy.keys())


def _load_from_registry() -> LoadedModel:
    """Fetch model từ MLflow Registry theo alias (model-agnostic)."""
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

    mv = client.get_model_version_by_alias(name=settings.model_name, alias=settings.model_alias)
    model_uri = f"models:/{settings.model_name}@{settings.model_alias}"
    logger.info("Loading model %s (version=%s, run_id=%s)", model_uri, mv.version, mv.run_id)

    model = mlflow.pyfunc.load_model(model_uri)

    sig = model.metadata.signature
    if sig and sig.inputs:
        feature_names = [inp.name for inp in sig.inputs.inputs]
    else:
        # Model cũ (v1) không có signature. Lấy feature names từ model object
        # thay vì compute_features() vì thứ tự features phải khớp training.
        feature_names = _extract_feature_names_from_model(model)
        logger.warning(
            "Model has no signature — extracted %d feature names from underlying model",
            len(feature_names),
        )

    # Model type từ MLflow run tag.
    run = client.get_run(mv.run_id)
    model_type = run.data.tags.get("model_type", "xgboost")

    return LoadedModel(
        model=model,
        feature_names=feature_names,
        version=str(mv.version),
        threshold=settings.model_threshold,
        model_type=model_type,
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
        logger.info(
            "Model reloaded: %s → %s (%s)", old_version, new_model.version, new_model.model_type
        )
        return new_model
