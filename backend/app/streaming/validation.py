"""Validate vital signs trước khi đánh dấu data hợp lệ cho retrain.

NaN/None pass validation (PhysioNet có missing data là bình thường).
Chỉ fail khi giá trị có nhưng ngoài clinical range.
"""

from __future__ import annotations

import math

VITAL_RANGES: dict[str, tuple[float, float]] = {
    "HR": (20.0, 300.0),
    "O2Sat": (0.0, 100.0),
    "Temp": (25.0, 45.0),
    "SBP": (30.0, 300.0),
    "MAP": (20.0, 250.0),
    "DBP": (10.0, 200.0),
    "Resp": (2.0, 60.0),
    "EtCO2": (0.0, 100.0),
}


def validate_vitals(vitals: dict[str, float | None]) -> bool:
    """Return True nếu tất cả vital signs nằm trong clinical range hoặc missing."""
    for key, (lo, hi) in VITAL_RANGES.items():
        val = vitals.get(key)
        if val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            return False
        if math.isnan(fval):
            continue
        if fval < lo or fval > hi:
            return False
    return True
