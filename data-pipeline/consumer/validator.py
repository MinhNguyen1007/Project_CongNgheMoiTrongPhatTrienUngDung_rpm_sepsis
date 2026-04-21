"""Validate vital sign records against physiological ranges."""

# Physiological valid ranges: (min, max)
VALID_RANGES: dict[str, tuple[float, float]] = {
    "HR": (0, 300),       # Heart rate (bpm)
    "O2Sat": (0, 100),    # SpO2 (%)
    "Temp": (25, 45),     # Temperature (Celsius)
    "SBP": (0, 350),      # Systolic BP (mmHg)
    "MAP": (0, 300),      # Mean arterial pressure (mmHg)
    "DBP": (0, 300),      # Diastolic BP (mmHg)
    "Resp": (0, 70),      # Respiratory rate (breaths/min)
    "EtCO2": (0, 100),    # End-tidal CO2 (mmHg)
}

_VITAL_COLUMNS = list(VALID_RANGES.keys())


def validate_record(record: dict) -> tuple[bool, str]:
    """Check that at least one vital sign exists and all are within range.

    Returns (is_valid, reason).
    """
    has_any_vital = False

    for col in _VITAL_COLUMNS:
        val = record.get(col)
        if val is None:
            continue
        has_any_vital = True
        lo, hi = VALID_RANGES[col]
        if not lo <= val <= hi:
            return False, f"{col}={val} out of range [{lo}, {hi}]"

    if not has_any_vital:
        return False, "All vital signs are null"

    return True, ""
