"""Feature engineering tại inference time — MIRROR `ml/src/preprocess.py`.

WHY tách thay vì import: `ml/src/preprocess.py` xử lý batch (DataFrame nhiều
patient), inference xử lý streaming (1 row tại 1 thời điểm). Tách giúp:
- Tránh dependency vòng (ml → backend hoặc ngược lại).
- Inference nhanh hơn (numpy thuần, không pandas groupby).

WHY PatientBuffer: rolling features cần 6h history. Buffer in-memory giữ
12h gần nhất per patient → đủ cho rolling 6h + delta. TTL 6h từ giờ cuối cùng
nhận message để tránh memory leak khi patient discharge.
"""

from __future__ import annotations

import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

import numpy as np

# Phải match với constants trong ml/src/preprocess.py — nếu sửa preprocess
# phải sửa cả đây. Đây là cái giá phải trả của việc tách module.
VITAL_COLS: list[str] = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2"]
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
DEMO_COLS: list[str] = ["Age", "Gender", "Unit1", "Unit2", "HospAdmTime", "ICULOS"]

ROLLING_WINDOW: int = 6
BUFFER_MAX_LEN: int = 12  # giữ 12h cho rolling 6h + delta + lookback
BUFFER_TTL_SECONDS: int = 24 * 3600  # discharge buffer sau 24h không activity


@dataclass
class _PatientState:
    """In-memory state cho 1 patient. Mutable, single-thread (consumer)."""

    # deque(maxlen=12): rows gần nhất, mỗi row = dict[col -> float|None].
    history: deque[dict[str, float | None]] = field(
        default_factory=lambda: deque(maxlen=BUFFER_MAX_LEN)
    )
    # Last-seen lab values cho ffill (1 lab có thể vắng nhiều giờ).
    last_labs: dict[str, float] = field(default_factory=dict)
    last_seen_ts: float = field(default_factory=time.time)


class PatientBuffer:
    """Thread-safe registry: patient_id → _PatientState."""

    def __init__(self) -> None:
        self._states: dict[str, _PatientState] = {}
        self._lock = Lock()

    def update(self, patient_id: str, row: dict[str, float | None]) -> _PatientState:
        """Append row mới, return state hiện tại (đã update)."""
        with self._lock:
            state = self._states.get(patient_id)
            if state is None:
                state = _PatientState()
                self._states[patient_id] = state
            state.history.append(row)
            state.last_seen_ts = time.time()

            # Cập nhật ffill cache cho labs có giá trị mới.
            for lab in LAB_COLS:
                v = row.get(lab)
                if v is not None and not _is_nan(v):
                    state.last_labs[lab] = float(v)
            return state

    def gc_stale(self) -> int:
        """Xóa patient không activity > TTL. Trả về số patient bị xóa."""
        cutoff = time.time() - BUFFER_TTL_SECONDS
        with self._lock:
            stale = [pid for pid, s in self._states.items() if s.last_seen_ts < cutoff]
            for pid in stale:
                del self._states[pid]
            return len(stale)

    def size(self) -> int:
        with self._lock:
            return len(self._states)


def _is_nan(x: float | None) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x))


def _safe_float(x: float | None) -> float:
    """None / NaN → np.nan. XGBoost handle NaN native."""
    if x is None:
        return float("nan")
    return float(x)


def compute_features(
    state: _PatientState,
    current_row: dict[str, float | None],
    demographics: dict[str, float | None],
) -> dict[str, float]:
    """Tính 117 features cho 1 giờ — match preprocess.feature_engineering().

    Args:
        state: PatientState với history đã update bao gồm current_row.
        current_row: row hiện tại (8 vitals + 26 labs + SepsisLabel — ignore label).
        demographics: 6 demo fields (Age, Gender, Unit1, Unit2, HospAdmTime, ICULOS).

    Returns:
        dict[feature_name -> float]. NaN cho missing — XGBoost tự xử.
    """
    feats: dict[str, float] = {}

    # Raw vitals
    for col in VITAL_COLS:
        feats[col] = _safe_float(current_row.get(col))

    # Rolling stats (window=6h). Lấy từ history deque.
    hist_list = list(state.history)
    window = hist_list[-ROLLING_WINDOW:]  # tối đa 6 row cuối, có thể ít hơn
    for col in VITAL_COLS:
        values = np.array([_safe_float(r.get(col)) for r in window], dtype=np.float64)
        # nanmean/std bỏ qua NaN; nếu toàn NaN → trả NaN. Suppress cosmetic
        # "Mean of empty slice" / "Degrees of freedom <= 0" — đây là behavior
        # mong muốn, không phải lỗi.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            feats[f"{col}_roll_mean_6h"] = (
                float(np.nanmean(values)) if values.size else float("nan")
            )
            feats[f"{col}_roll_std_6h"] = (
                float(np.nanstd(values, ddof=1)) if values.size > 1 else float("nan")
            )

        # Delta: current - previous (lùi 1 giờ).
        if len(hist_list) >= 2:
            prev = _safe_float(hist_list[-2].get(col))
            curr = _safe_float(current_row.get(col))
            feats[f"{col}_delta"] = curr - prev
        else:
            feats[f"{col}_delta"] = float("nan")

    # Labs raw + ffill + missing flag
    n_missing = 0
    for col in VITAL_COLS:
        if _is_nan(current_row.get(col)):
            n_missing += 1

    for col in LAB_COLS:
        raw = current_row.get(col)
        feats[col] = _safe_float(raw)
        feats[f"{col}_missing_flag"] = 1.0 if _is_nan(raw) else 0.0
        if _is_nan(raw):
            n_missing += 1
            feats[f"{col}_ffill"] = state.last_labs.get(col, float("nan"))
        else:
            feats[f"{col}_ffill"] = float(raw)

    # Demographics (raw, không transform)
    for col in DEMO_COLS:
        feats[col] = _safe_float(demographics.get(col))

    feats["n_features_missing"] = float(n_missing)
    return feats


def features_to_array(features: dict[str, float], feature_names: list[str]) -> np.ndarray:
    """Project dict → 1D array theo đúng thứ tự model expect.

    Missing key → NaN (forward-compat: nếu model cần feature mới mà features
    dict không có, gán NaN thay vì crash).
    """
    return np.array(
        [features.get(name, float("nan")) for name in feature_names],
        dtype=np.float32,
    )
