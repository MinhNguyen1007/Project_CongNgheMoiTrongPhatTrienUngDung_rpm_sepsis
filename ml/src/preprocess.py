"""Load + feature-engineer PhysioNet Challenge 2019 sepsis data.

Public functions (gọi từ notebook hoặc CLI):
- load_psv_files(): đọc tất cả `.psv` thành 1 DataFrame có cột `patient_id`.
- feature_engineering(): thêm rolling stats + missingness flags.
- split_train_val(): split THEO BỆNH NHÂN (không leak giờ của cùng patient).
- load_and_split(): convenience wrapper cho notebook + train.py.

WHY rolling thay vì giá trị đơn lẻ: vital signs đo theo giờ, sepsis phản ánh
qua xu hướng (HR tăng dần, BP tụt dần) hơn là 1 snapshot. Rolling 6h là
trade-off giữa context và độ tươi.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

# Tên 8 vital signs (đo theo giờ, ít NaN). Dùng cho rolling features.
VITAL_COLS: list[str] = [
    "HR",
    "O2Sat",
    "Temp",
    "SBP",
    "MAP",
    "DBP",
    "Resp",
    "EtCO2",
]

# 26 lab values — sampling thưa hơn, nhiều NaN. KHÔNG rolling, chỉ ffill.
LAB_COLS: list[str] = [
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

# 6 cột demographics + admin (không phải feature theo thời gian).
DEMO_COLS: list[str] = ["Age", "Gender", "Unit1", "Unit2", "HospAdmTime", "ICULOS"]

TARGET_COL: str = "SepsisLabel"

# Rolling window mặc định: 6 giờ. Sepsis-3 label nhìn xa 6h, dùng cùng window
# để feature "thấy" được trend trong cùng tầm nhìn của label.
ROLLING_WINDOW: int = 6


def _read_one_psv(path: Path) -> pd.DataFrame:
    """Đọc 1 file .psv và gắn patient_id từ tên file (p000001 → 'p000001')."""
    df = pd.read_csv(path, sep="|")
    df["patient_id"] = path.stem  # e.g. 'p000001'
    return df


def load_psv_files(
    data_dirs: list[Path | str],
    max_patients: int | None = None,
    n_workers: int = 4,
) -> pd.DataFrame:
    """Load nhiều thư mục PhysioNet (setA + setB) thành 1 DataFrame.

    WHY ProcessPoolExecutor: 40k file PSV nhỏ — đọc tuần tự ~3 phút trên SSD,
    parallel 4 worker giảm còn <1 phút. I/O-bound + CSV parse là CPU-light nên
    ProcessPool vẫn lợi nhờ tránh GIL khi pandas parse.

    Args:
        data_dirs: list path thư mục chứa `.psv` (vd: [ml/data/training_setA, setB]).
        max_patients: nếu set, chỉ đọc N file đầu (debug/EDA).
        n_workers: số process song song.

    Returns:
        DataFrame đã concat, có cột `patient_id` thêm vào.
    """
    paths: list[Path] = []
    for d in data_dirs:
        d = Path(d)
        if not d.exists():
            raise FileNotFoundError(f"Data dir not found: {d}")
        paths.extend(sorted(d.glob("p*.psv")))

    if max_patients is not None:
        paths = paths[:max_patients]
    if not paths:
        raise FileNotFoundError(f"No .psv files in {data_dirs}")

    logger.info("Loading %d PSV files from %d dirs", len(paths), len(data_dirs))

    frames: list[pd.DataFrame] = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futures = {ex.submit(_read_one_psv, p): p for p in paths}
        for fut in as_completed(futures):
            frames.append(fut.result())

    df = pd.concat(frames, ignore_index=True)
    logger.info("Loaded shape=%s, patients=%d", df.shape, df["patient_id"].nunique())
    return df


def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """Thêm rolling stats + missingness flags + forward-fill labs.

    Quy tắc: TẤT CẢ phép tính nhóm bệnh nhân để tránh leak giữa patients.

    Features thêm vào:
    - `<vital>_roll_mean_6h`, `<vital>_roll_std_6h`: rolling 6h theo patient.
    - `<vital>_delta`: hiệu giờ hiện tại - giờ trước (rate of change).
    - `<lab>_ffill`: forward-fill labs trong cùng patient.
    - `<lab>_missing_flag`: 1 nếu lab gốc NaN ở giờ này (informative missingness).
    - `n_features_missing`: tổng số feature NaN ở giờ hiện tại.
    """
    df = df.sort_values(["patient_id", "ICULOS"]).reset_index(drop=True)
    g = df.groupby("patient_id", sort=False)

    # Rolling stats cho vitals (window=6h, min_periods=1 để không mất rows đầu)
    for col in VITAL_COLS:
        if col not in df.columns:
            continue
        roll = g[col].rolling(window=ROLLING_WINDOW, min_periods=1)
        df[f"{col}_roll_mean_6h"] = roll.mean().reset_index(level=0, drop=True)
        df[f"{col}_roll_std_6h"] = roll.std().reset_index(level=0, drop=True)
        df[f"{col}_delta"] = g[col].diff()

    # Forward-fill labs trong từng patient (lab đo thưa, giá trị cũ vẫn relevant)
    # Missingness flag PHẢI lấy TRƯỚC ffill — sau ffill thì NaN biến mất.
    for col in LAB_COLS:
        if col not in df.columns:
            continue
        df[f"{col}_missing_flag"] = df[col].isna().astype(np.int8)
        df[f"{col}_ffill"] = g[col].ffill()

    # Tổng số feature gốc bị NaN ở giờ này (informative missingness aggregate)
    df["n_features_missing"] = df[VITAL_COLS + LAB_COLS].isna().sum(axis=1).astype(np.int16)

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Trả về list cột feature để feed vào model (loại id + target)."""
    exclude = {"patient_id", TARGET_COL}
    return [c for c in df.columns if c not in exclude]


def split_train_val(
    df: pd.DataFrame,
    val_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split THEO BỆNH NHÂN để tránh leak giờ của cùng patient sang val set.

    Stratify theo việc patient có sepsis hay không (bất kỳ giờ nào label=1).

    Returns:
        (train_df, val_df) — đã shuffle ở patient level.
    """
    patient_labels = (
        df.groupby("patient_id")[TARGET_COL].max().reset_index()
    )  # patient_id, max_label (0 or 1)

    train_pids, val_pids = train_test_split(
        patient_labels["patient_id"].values,
        test_size=val_size,
        stratify=patient_labels[TARGET_COL].values,
        random_state=random_state,
    )

    train_df = df[df["patient_id"].isin(train_pids)].reset_index(drop=True)
    val_df = df[df["patient_id"].isin(val_pids)].reset_index(drop=True)

    logger.info(
        "Split: train=%d rows (%d patients), val=%d rows (%d patients)",
        len(train_df),
        len(train_pids),
        len(val_df),
        len(val_pids),
    )
    return train_df, val_df


def load_and_split(
    data_dirs: list[Path | str] | None = None,
    max_patients: int | None = None,
    val_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience wrapper: load → feature engineer → split. Dùng từ notebook + train.py."""
    if data_dirs is None:
        # Default: cả 2 hospital (setA + setB) để có domain diversity
        root = Path(__file__).resolve().parents[1] / "data"
        data_dirs = [root / "training_setA", root / "training_setB"]

    raw = load_psv_files(data_dirs, max_patients=max_patients)
    feats = feature_engineering(raw)
    return split_train_val(feats, val_size=val_size, random_state=random_state)


if __name__ == "__main__":
    # Smoke test: load 50 patients, in shape ra cho chắc.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_df, val_df = load_and_split(max_patients=50)
    print(f"train shape: {train_df.shape}")
    print(f"val shape:   {val_df.shape}")
    print(f"features:    {len(get_feature_columns(train_df))}")
    print(f"sepsis rate (train): {train_df[TARGET_COL].mean():.4f}")
