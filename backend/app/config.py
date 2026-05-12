"""Pydantic Settings — load config từ .env ở project root.

WHY pydantic-settings thay vì os.environ: validate type + default value + tự
load `.env`. Code khác (consumer, scheduler) import `settings` → 1 nguồn duy nhất.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config. Field names map 1:1 với env vars (uppercase)."""

    # Database
    database_url: str = "postgresql+asyncpg://monitoring:monitoring@localhost:5432/monitoring"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_vitals: str = "patient-vitals"
    kafka_consumer_group: str = "backend-consumer"

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"
    model_name: str = "sepsis-predictor"
    model_alias: str = "production"
    model_threshold: float = 0.70

    # Frontend
    frontend_origin: str = "http://localhost:5173"

    # Drift
    drift_features_threshold: float = 0.3

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Singleton — chỉ parse .env 1 lần per process."""
    return Settings()


settings = get_settings()
