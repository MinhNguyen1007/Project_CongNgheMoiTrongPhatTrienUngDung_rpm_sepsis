"""Feature engineering: rolling statistics and clinical scores.

Maintains per-patient sliding windows (up to 24h) and computes:
- Rolling mean/std/min/max/slope for each vital sign at 6h/12h/24h windows
- Missing indicator features (lab missing = clinically meaningful)
- Clinical scores: qSOFA, SIRS
"""

from collections import defaultdict, deque
from typing import Any

import numpy as np

VITAL_COLUMNS = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2"]
WINDOWS = [6, 12, 24]


class FeatureEngineer:
    """Stateful feature engineer — call update() for each new hourly record."""

    def __init__(self, max_window: int = 24) -> None:
        self.max_window = max_window
        self._history: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=max_window))

    @property
    def patient_count(self) -> int:
        return len(self._history)

    def update(self, patient_id: str, record: dict) -> dict[str, Any]:
        """Append record to patient history and return computed features."""
        self._history[patient_id].append(record)
        history = list(self._history[patient_id])
        return self._compute_features(record, history)

    # ── Private ────────────────────────────────────────

    def _compute_features(self, current: dict, history: list[dict]) -> dict[str, Any]:
        features: dict[str, Any] = {}

        # Rolling stats per vital sign per window
        for col in VITAL_COLUMNS:
            for window in WINDOWS:
                values = [r[col] for r in history[-window:] if r.get(col) is not None]
                suffix = f"{col.lower()}_{window}h"

                if values:
                    arr = np.array(values, dtype=np.float64)
                    features[f"mean_{suffix}"] = float(np.mean(arr))
                    features[f"std_{suffix}"] = float(np.std(arr))
                    features[f"min_{suffix}"] = float(np.min(arr))
                    features[f"max_{suffix}"] = float(np.max(arr))
                    if len(arr) >= 2:
                        x = np.arange(len(arr), dtype=np.float64)
                        features[f"slope_{suffix}"] = float(np.polyfit(x, arr, 1)[0])
                    else:
                        features[f"slope_{suffix}"] = 0.0
                else:
                    for stat in ("mean", "std", "min", "max", "slope"):
                        features[f"{stat}_{suffix}"] = None

            # Missing indicator
            features[f"missing_{col.lower()}"] = 1 if current.get(col) is None else 0

        # Clinical scores
        features["qsofa_score"] = self._qsofa(current)
        features["sirs_count"] = self._sirs(current)
        features["iculos_hours"] = current.get("ICULOS", 0)

        return features

    @staticmethod
    def _qsofa(record: dict) -> int:
        """Quick SOFA (0-2 in this dataset — GCS not available)."""
        score = 0
        sbp = record.get("SBP")
        if sbp is not None and sbp <= 100:
            score += 1
        resp = record.get("Resp")
        if resp is not None and resp >= 22:
            score += 1
        return score

    @staticmethod
    def _sirs(record: dict) -> int:
        """SIRS criteria count (0-4)."""
        count = 0
        temp = record.get("Temp")
        if temp is not None and (temp > 38 or temp < 36):
            count += 1
        hr = record.get("HR")
        if hr is not None and hr > 90:
            count += 1
        resp = record.get("Resp")
        if resp is not None and resp > 20:
            count += 1
        wbc = record.get("WBC")
        if wbc is not None and (wbc > 12 or wbc < 4):
            count += 1
        return count
