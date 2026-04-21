---
name: new-feature-function
description: Thêm một feature engineering function mới trong ml/src/features.py cho bài toán sepsis. Hỗ trợ rolling stats, clinical scores (SIRS, qSOFA, SOFA), trend features.
---

# Skill: New Feature Engineering Function

Thêm hàm feature mới vào `ml/src/features.py`. Feature phải: pure function, có unit test, document rõ ý nghĩa lâm sàng.

## Quy trình

1. Hỏi user (nếu chưa rõ):
   - Tên feature (snake_case, vd `rolling_hr_std_6h`, `qsofa_score`)
   - Loại: rolling stat / clinical score / trend / interaction / missingness indicator
   - Input columns cần thiết
2. Thêm hàm vào `ml/src/features.py` với type hints + docstring ngắn giải thích lâm sàng.
3. Thêm vào registry `FEATURE_REGISTRY` để dễ chọn qua config.
4. Viết test trong `tests/unit/ml/test_features.py` (ít nhất 2 case: normal + edge case missing).
5. Chạy `pytest tests/unit/ml/test_features.py -v`.

## Template rolling stat

```python
def rolling_std(df: pd.DataFrame, col: str, window_hours: int) -> pd.Series:
    """Độ lệch chuẩn rolling theo từng BN.

    Ý nghĩa lâm sàng: biến động cao của HR/BP trong cửa sổ ngắn
    là dấu hiệu sớm của instability, liên quan đến sepsis.

    Args:
        df: DataFrame có cột patient_id, hour, và `col`.
        col: tên cột số (HR, SpO2, Temp, ...).
        window_hours: kích thước cửa sổ theo giờ.

    Returns:
        Series cùng index với df.
    """
    return (
        df.groupby("patient_id")[col]
        .rolling(window=window_hours, min_periods=2)
        .std()
        .reset_index(level=0, drop=True)
    )
```

## Template clinical score (qSOFA)

```python
def qsofa_score(df: pd.DataFrame) -> pd.Series:
    """quick SOFA - thang điểm sàng lọc sepsis nhanh (0-3).

    Ba tiêu chí (mỗi tiêu chí = 1 điểm):
    - Respiratory rate >= 22/min
    - Altered mental status (GCS < 15) - ta xấp xỉ bằng SBP drop
    - Systolic blood pressure <= 100 mmHg

    Điểm >= 2 nghi ngờ sepsis (Singer et al., 2016).
    """
    score = pd.Series(0, index=df.index)
    score += (df["Resp"] >= 22).fillna(False).astype(int)
    score += (df["SBP"] <= 100).fillna(False).astype(int)
    # GCS không có trong PhysioNet, dùng proxy MAP < 65
    score += (df["MAP"] < 65).fillna(False).astype(int)
    return score
```

## Template registry

```python
from collections.abc import Callable
from functools import partial

FEATURE_REGISTRY: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "hr_mean_6h": partial(rolling_mean, col="HR", window_hours=6),
    "hr_std_6h": partial(rolling_std, col="HR", window_hours=6),
    "spo2_min_6h": partial(rolling_min, col="O2Sat", window_hours=6),
    "qsofa": qsofa_score,
    # ...
}


def build_features(df: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    """Build feature matrix theo tên feature set đã đăng ký."""
    names = FEATURE_SETS[feature_set]
    return pd.DataFrame(
        {name: FEATURE_REGISTRY[name](df) for name in names},
        index=df.index,
    )
```

## Template test

```python
import pandas as pd
import pytest
from ml.src.features import rolling_std, qsofa_score


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "patient_id": ["P1"] * 6 + ["P2"] * 4,
        "hour": [0,1,2,3,4,5, 0,1,2,3],
        "HR": [80, 85, 90, 95, 100, 110,  70, 72, 74, 76],
        "Resp": [18, 20, 22, 24, 26, 28,  16, 18, 20, 22],
        "SBP": [120, 115, 110, 105, 100, 95, 130, 125, 120, 115],
        "MAP": [80, 78, 75, 70, 65, 60, 90, 85, 80, 75],
    })


def test_rolling_std_basic(sample_df):
    result = rolling_std(sample_df, "HR", window_hours=3)
    # BN P1 trong 3 giờ đầu (80,85,90) → std > 0
    assert result.iloc[2] == pytest.approx(5.0, rel=0.01)


def test_qsofa_score_high_risk(sample_df):
    result = qsofa_score(sample_df)
    # Row cuối BN P1: Resp=28>=22, SBP=95<=100, MAP=60<65 → 3 điểm
    assert result.iloc[5] == 3
```

## Lưu ý

- Feature phải không leak data tương lai: chỉ dùng giá trị tại hoặc trước thời điểm hiện tại.
- Missing handling: mặc định `fillna(False)` cho binary flag, giữ `NaN` cho số (model tự xử).
- Nếu feature dùng lookup table/coefficient, lưu vào `ml/configs/clinical_constants.yaml`.
- Benchmark tốc độ nếu feature phức tạp (>10s cho 1M rows = cần tối ưu).
