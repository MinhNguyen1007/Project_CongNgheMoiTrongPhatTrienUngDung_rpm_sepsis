"""Tighten training labels to the utility reward window [-6h, +3h].

PhysioNet sets ``SepsisLabel=1`` from ``t_sepsis - 6`` until the end of the
ICU stay. Any alarm fired after ``t_sepsis + 3`` earns ``U_FN`` (treated as
missed), so training the model to keep predicting positive for hours past
the reward window teaches it to chase probability mass that yields zero
reward at best. Relabeling those late rows to 0 concentrates the model's
positive signal on the window that actually matters.

Only relabel TRAIN and (optionally) VAL. Test labels must remain untouched
so the held-out utility score is directly comparable to the PhysioNet
ground truth.

Usage::

    python ml/src/relabel.py \
        --input-dir data/features \
        --out-dir data/features_relabeled \
        --late-cutoff 3
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

LABEL_COL = "SepsisLabel"
PATIENT_COL = "patient_id"
TIME_COL = "ICULOS"
# PhysioNet offset: first positive row is at t_sepsis - 6.
ONSET_OFFSET = 6


def relabel_split(df: pd.DataFrame, late_cutoff: int = 3) -> pd.DataFrame:
    """Zero out ``SepsisLabel`` for rows past ``t_sepsis + late_cutoff``.

    Non-sepsis patients (no positive rows) are untouched.
    """
    if TIME_COL not in df.columns:
        raise KeyError(
            f"{TIME_COL} column missing — required to compute onset time."
        )

    df = df.sort_values([PATIENT_COL, TIME_COL]).reset_index(drop=True)
    new_label = df[LABEL_COL].to_numpy().copy()

    patients_modified = 0
    rows_flipped = 0

    for pid, group in df.groupby(PATIENT_COL, sort=False):
        if group[LABEL_COL].max() != 1:
            continue

        first_pos_pos = group.index[group[LABEL_COL] == 1][0]
        first_pos_iculos = float(group.loc[first_pos_pos, TIME_COL])
        # t_sepsis = first_pos_iculos + ONSET_OFFSET
        cutoff_iculos = first_pos_iculos + ONSET_OFFSET + late_cutoff

        late_mask = (group[TIME_COL] > cutoff_iculos) & (group[LABEL_COL] == 1)
        late_idx = group.index[late_mask]
        if len(late_idx) > 0:
            new_label[late_idx.to_numpy()] = 0
            patients_modified += 1
            rows_flipped += len(late_idx)

    df = df.copy()
    df[LABEL_COL] = new_label
    logger.info(
        "Relabeled: %d sepsis patients modified, %d rows flipped 1->0 "
        "(kept positive label in [-6h, +%dh] around onset)",
        patients_modified,
        rows_flipped,
        late_cutoff,
    )
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Relabel training features")
    parser.add_argument(
        "--input-dir", type=Path, default=Path("data/features"),
        help="Directory with train/val/test parquet files (from build_features.py).",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("data/features_relabeled"),
        help="Destination directory for relabeled splits.",
    )
    parser.add_argument(
        "--late-cutoff", type=int, default=3,
        help="Hours after onset to keep SepsisLabel=1. Rows beyond are flipped to 0.",
    )
    parser.add_argument(
        "--splits", nargs="+", default=["train"],
        help="Splits to relabel. Never include 'test' — would break utility eval.",
    )
    args = parser.parse_args()

    if "test" in args.splits:
        raise ValueError(
            "Refusing to relabel test split — it would invalidate utility evaluation."
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for split in ["train", "val", "test"]:
        src = args.input_dir / f"{split}.parquet"
        if not src.exists():
            logger.warning("Skipping %s — %s not found", split, src)
            continue
        df = pd.read_parquet(src)
        if split in args.splits:
            logger.info("Relabeling %s split (%d rows)...", split, len(df))
            df = relabel_split(df, args.late_cutoff)
        else:
            logger.info("Copying %s split unchanged (%d rows)", split, len(df))
        dst = args.out_dir / f"{split}.parquet"
        df.to_parquet(dst, index=False)
        logger.info("Saved %s -> %s", split, dst)

    logger.info("Done.")


if __name__ == "__main__":
    main()
