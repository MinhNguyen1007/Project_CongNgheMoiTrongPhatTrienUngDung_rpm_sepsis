"""Load PhysioNet .psv files and split by patient ID into train/val/test.

Usage:
    python ml/src/preprocess.py --data-dir data/raw --out-dir data/processed
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SPLIT_RATIOS = (0.70, 0.15, 0.15)  # train / val / test
RANDOM_SEED = 42


def discover_psv_files(data_dir: Path) -> list[Path]:
    """Find all .psv files, checking subdirectories."""
    psv_files = sorted(data_dir.glob("*.psv"))
    if not psv_files:
        psv_files = sorted(data_dir.rglob("*.psv"))
    logger.info("Found %d .psv files in %s", len(psv_files), data_dir)
    return psv_files


def load_single_patient(psv_path: Path) -> pd.DataFrame:
    """Load one .psv file and add patient_id column."""
    df = pd.read_csv(psv_path, sep="|")
    df.insert(0, "patient_id", psv_path.stem)
    return df


def load_all_patients(data_dir: Path, max_patients: int | None = None) -> pd.DataFrame:
    """Load all .psv files into one DataFrame."""
    psv_files = discover_psv_files(data_dir)
    if max_patients:
        psv_files = psv_files[:max_patients]

    frames: list[pd.DataFrame] = []
    for i, path in enumerate(psv_files):
        frames.append(load_single_patient(path))
        if (i + 1) % 5000 == 0:
            logger.info("Loaded %d / %d patients", i + 1, len(psv_files))

    df = pd.concat(frames, ignore_index=True)
    logger.info(
        "Combined: %d rows, %d patients, sepsis prevalence=%.2f%%",
        len(df),
        df["patient_id"].nunique(),
        df["SepsisLabel"].mean() * 100,
    )
    return df


def split_by_patient(
    df: pd.DataFrame, seed: int = RANDOM_SEED
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split into train/val/test by patient ID (no leakage)."""
    patient_ids = df["patient_id"].unique()
    rng = np.random.RandomState(seed)
    rng.shuffle(patient_ids)

    n = len(patient_ids)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])

    train_ids = set(patient_ids[:n_train])
    val_ids = set(patient_ids[n_train : n_train + n_val])
    test_ids = set(patient_ids[n_train + n_val :])

    train_df = df[df["patient_id"].isin(train_ids)].copy()
    val_df = df[df["patient_id"].isin(val_ids)].copy()
    test_df = df[df["patient_id"].isin(test_ids)].copy()

    for name, split_df, ids in [
        ("train", train_df, train_ids),
        ("val", val_df, val_ids),
        ("test", test_df, test_ids),
    ]:
        logger.info(
            "  %s: %d patients, %d rows, sepsis=%.2f%%",
            name,
            len(ids),
            len(split_df),
            split_df["SepsisLabel"].mean() * 100,
        )

    return train_df, val_df, test_df


def save_splits(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    out_dir: Path,
) -> None:
    """Save splits as Parquet files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        path = out_dir / f"{name}.parquet"
        split_df.to_parquet(path, index=False)
        logger.info("Saved %s -> %s (%d rows)", name, path, len(split_df))


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess PhysioNet data")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing .psv files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/processed"),
        help="Output directory for parquet splits",
    )
    parser.add_argument(
        "--max-patients",
        type=int,
        default=None,
        help="Limit number of patients (for quick testing)",
    )
    args = parser.parse_args()

    df = load_all_patients(args.data_dir, args.max_patients)
    train_df, val_df, test_df = split_by_patient(df)
    save_splits(train_df, val_df, test_df, args.out_dir)
    logger.info("Done.")


if __name__ == "__main__":
    main()
