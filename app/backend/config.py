"""Runtime configuration. Load from env with pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mlflow_tracking_uri: str = "http://localhost:5000"
    model_uri: str = "models:/sepsis-lgbm-prod/4"

    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin123"
    mlflow_s3_endpoint_url: str = "http://localhost:9000"

    redis_url: str = "redis://localhost:6379/0"

    postgres_user: str = "rpm_user"
    postgres_password: str = "change_me_in_real_env"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "rpm"

    aws_endpoint_url: str = "http://localhost:4566"
    aws_region: str = "us-east-1"
    dynamodb_features_table: str = "patient_latest_features"
    dynamodb_predictions_table: str = "patient_recent_predictions"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    default_threshold: float = 0.05
    default_min_consecutive: int = 6
    default_warmup_hours: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
