"""Simulator: replay PhysioNet .psv files into Kinesis stream.

Usage:
    python data-pipeline/simulator/run.py --data-dir data/raw --patients 10 --speed 1.0
"""

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path

import boto3
import pandas as pd

# Add data-pipeline/ to path so we can import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_ENDPOINT_URL,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    KINESIS_STREAM_NAME,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def create_kinesis_client() -> boto3.client:
    return boto3.client(
        "kinesis",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def load_patient_data(psv_path: Path) -> pd.DataFrame:
    """Load a single .psv (pipe-separated) file."""
    return pd.read_csv(psv_path, sep="|")


def row_to_record(patient_id: str, row: pd.Series) -> dict:
    """Convert a DataFrame row to a JSON-safe dict (NaN -> None)."""
    record: dict = {"patient_id": patient_id}
    for col, val in row.items():
        if isinstance(val, float) and math.isnan(val):
            record[str(col)] = None
        else:
            record[str(col)] = val
    return record


def discover_patients(data_dir: Path, max_patients: int) -> list[Path]:
    """Find .psv files, checking subdirectories (training_setA/, training_setB/)."""
    psv_files = sorted(data_dir.glob("*.psv"))
    if not psv_files:
        psv_files = sorted(data_dir.rglob("*.psv"))
    if not psv_files:
        logger.error("No .psv files found in %s", data_dir)
        sys.exit(1)
    selected = psv_files[:max_patients]
    logger.info("Found %d .psv files, using %d patients", len(psv_files), len(selected))
    return selected


def run_simulation(data_dir: Path, max_patients: int, speed: float) -> None:
    """Main loop: replay patient data hour-by-hour into Kinesis."""
    client = create_kinesis_client()
    psv_files = discover_patients(data_dir, max_patients)

    # Load all patient data into memory
    patients: dict[str, pd.DataFrame] = {}
    for psv_path in psv_files:
        patient_id = psv_path.stem  # e.g. "p000001"
        patients[patient_id] = load_patient_data(psv_path)
        logger.info("Loaded %s: %d hours", patient_id, len(patients[patient_id]))

    max_hours = max(len(df) for df in patients.values())
    logger.info(
        "Starting simulation: %d patients, %d max hours, %.1fs/hour",
        len(patients),
        max_hours,
        speed,
    )

    records_sent = 0
    for hour in range(max_hours):
        batch_count = 0
        for patient_id, df in patients.items():
            if hour >= len(df):
                continue
            record = row_to_record(patient_id, df.iloc[hour])
            record["_hour"] = hour

            client.put_record(
                StreamName=KINESIS_STREAM_NAME,
                Data=json.dumps(record).encode("utf-8"),
                PartitionKey=patient_id,
            )
            batch_count += 1
            records_sent += 1

        logger.info(
            "Hour %d/%d — sent %d records (total: %d)",
            hour + 1,
            max_hours,
            batch_count,
            records_sent,
        )

        if hour < max_hours - 1:
            time.sleep(speed)

    logger.info("Simulation complete. Total records sent: %d", records_sent)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay PhysioNet data into Kinesis")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing .psv files (default: data/raw)",
    )
    parser.add_argument(
        "--patients",
        type=int,
        default=10,
        help="Number of patients to simulate (default: 10)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Seconds per simulated hour (default: 1.0)",
    )
    args = parser.parse_args()
    run_simulation(args.data_dir, args.patients, args.speed)


if __name__ == "__main__":
    main()
