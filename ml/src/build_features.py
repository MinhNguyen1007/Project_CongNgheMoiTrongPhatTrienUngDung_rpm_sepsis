"""Batch feature engineering — reuses streaming logic for train/val/test splits.

For each patient, iterates through hours sequentially and computes rolling
features at each timestep. This ensures exact feature parity between
offline training and online serving.

Usage:
    python ml/src/build_features.py --input-dir data/processed --out-dir data/features
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse the streaming feature engineer for exact parity
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "data-pipeline"))
from consumer.feature_engineer import FeatureEngineer
from feature_store.schemas import FEATURE_NAMES

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def build_features_for_split(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 131 features for every row, respecting temporal order per patient.

    Uses the same FeatureEngineer as the streaming pipeline to guarantee
    that training features match serving features exactly.
    """
    engineer = FeatureEngineer()
    results: list[dict] = []

    patient_ids = df["patient_id"].unique()
    for i, pid in enumerate(patient_ids):
        patient_rows = df[df["patient_id"] == pid].sort_values("ICULOS")
        for _, row in patient_rows.iterrows():
            record = row.to_dict()
            # NaN -> None (FeatureEngineer expects None for missing)
            record = {
                k: (None if isinstance(v, float) and np.isnan(v) else v)
                for k, v in record.items()
            }

            features = engineer.update(pid, record)
            features["patient_id"] = pid
            features["ICULOS"] = record.get("ICULOS", 0)
            features["SepsisLabel"] = record.get("SepsisLabel", 0)
            # Demographics (static per patient, useful for model)
            features["Age"] = record.get("Age")
            features["Gender"] = record.get("Gender")
            features["HospAdmTime"] = record.get("HospAdmTime")
            results.append(features)

        if (i + 1) % 2000 == 0:
            logger.info("  Processed %d / %d patients", i + 1, len(patient_ids))

    result_df = pd.DataFrame(results)
    logger.info(
        "Built features: %d rows, %d columns", len(result_df), len(result_df.columns)
    )
    return result_df


def get_model_feature_columns() -> list[str]:
    """Return the 131 feature names + 3 demographics used as model input."""
    return FEATURE_NAMES + ["Age", "Gender", "HospAdmTime"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch feature engineering")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory with train/val/test parquet files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/features"),
        help="Output directory for feature parquet files",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for split in ["train", "val", "test"]:
        path = args.input_dir / f"{split}.parquet"
        if not path.exists():
            logger.warning("Skipping %s — file not found", path)
            continue
        logger.info("Processing %s split...", split)
        df = pd.read_parquet(path)
        features_df = build_features_for_split(df)
        out_path = args.out_dir / f"{split}.parquet"
        features_df.to_parquet(out_path, index=False)
        logger.info("Saved %s -> %s", split, out_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
