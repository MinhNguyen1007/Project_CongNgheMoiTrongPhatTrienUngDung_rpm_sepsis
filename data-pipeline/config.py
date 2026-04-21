"""Shared configuration for data pipeline."""

import os

from dotenv import load_dotenv

load_dotenv()

# ── AWS / LocalStack ───────────────────────────────────
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

# ── Kinesis ────────────────────────────────────────────
KINESIS_STREAM_NAME = os.getenv("KINESIS_STREAM_NAME", "vital-signs-stream")

# ── DynamoDB ───────────────────────────────────────────
DYNAMODB_FEATURES_TABLE = "patient_latest_features"
DYNAMODB_PREDICTIONS_TABLE = "patient_recent_predictions"

# ── S3 ─────────────────────────────────────────────────
S3_RAW_BUCKET = "raw-data"
S3_PARQUET_BUCKET = "parquet-data"

# ── Backend inference ──────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_PREDICT_ENABLED = os.getenv("BACKEND_PREDICT_ENABLED", "true").lower() == "true"
BACKEND_PREDICT_TIMEOUT = float(os.getenv("BACKEND_PREDICT_TIMEOUT", "3.0"))

# ── Redis (vitals history for backend serving) ─────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── PhysioNet columns ──────────────────────────────────
VITAL_COLUMNS = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2"]

LAB_COLUMNS = [
    "BaseExcess",
    "HCO3",
    "FiO2",
    "pH",
    "PaCO2",
    "SaO2",
    "AST",
    "BUN",
    "Alkalinephos",
    "Calcium",
    "Chloride",
    "Creatinine",
    "Bilirubin_direct",
    "Glucose",
    "Lactate",
    "Magnesium",
    "Phosphate",
    "Potassium",
    "Bilirubin_total",
    "TroponinI",
    "Hct",
    "Hgb",
    "PTT",
    "WBC",
    "Fibrinogen",
    "Platelets",
]

DEMOGRAPHIC_COLUMNS = ["Age", "Gender", "Unit1", "Unit2", "HospAdmTime"]

ALL_FEATURE_COLUMNS = VITAL_COLUMNS + LAB_COLUMNS + DEMOGRAPHIC_COLUMNS
