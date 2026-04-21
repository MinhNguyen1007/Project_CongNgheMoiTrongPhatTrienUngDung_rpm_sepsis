"""PhysioNet 2019 Challenge — Normalized Utility Score.

Implements the official evaluation metric that rewards early sepsis
prediction and penalizes false alarms / missed cases.

Reference: https://physionet.org/content/challenge-2019/
"""

import numpy as np
import pandas as pd

# ── Utility function parameters (from challenge spec) ──
DT_EARLY = -12  # earliest useful prediction (hours before onset)
DT_OPTIMAL = -6  # start of max-reward window
DT_LATE = 3  # latest useful prediction (hours after onset)

U_TP_MAX = 1.0  # max reward for correct early prediction
U_FN = -2.0  # penalty for missing sepsis
U_FP = -0.05  # penalty for false alarm on non-sepsis patient
U_TN = 0.0  # no penalty for correct rejection


def _utility_tp(dt: int) -> float:
    """Compute utility for a true positive prediction at time offset dt.

    dt = t_alarm - t_onset (negative = early prediction, positive = late).
    """
    if dt < DT_EARLY:
        # Too early — no credit
        return 0.0
    elif dt <= DT_OPTIMAL:
        # Linearly increasing reward from 0 to U_TP_MAX
        return U_TP_MAX * (dt - DT_EARLY) / (DT_OPTIMAL - DT_EARLY)
    elif dt <= DT_LATE:
        # Optimal window — max reward
        return U_TP_MAX
    else:
        # Too late — treat as missed
        return U_FN


def _first_consecutive_alarm(preds: np.ndarray, k: int, warmup: int = 0) -> int | None:
    """Return index of first run of `k` consecutive 1s, or None.

    Implements the hysteresis rule (decision #6): alarm only fires after
    `k` consecutive positive predictions — reduces false alarms caused by
    isolated proba spikes on non-sepsis patients.

    `warmup` masks predictions in the first N rows of the patient's ICU
    stay. Rationale: rolling-stat features are not populated in early hours
    (thin history), leading to noisy probas that fire before the reward
    window even opens. Clinically, an alert in the first few hours of ICU
    is also less actionable (admission baseline still stabilizing).
    """
    if warmup > 0:
        preds = preds.copy()
        preds[:warmup] = 0
    if k <= 1:
        return int(np.argmax(preds == 1)) if preds.any() else None
    # Rolling sum of the last k predictions; first index where it hits k
    # is the end of the first k-long run; alarm time = that index - k + 1.
    if len(preds) < k:
        return None
    window = np.convolve(preds, np.ones(k, dtype=int), mode="valid")
    hits = np.where(window >= k)[0]
    return int(hits[0]) if len(hits) else None


def compute_patient_utility(
    predictions: np.ndarray,
    labels: np.ndarray,
    min_consecutive: int = 1,
    warmup_hours: int = 0,
) -> float:
    """Compute utility for a single patient.

    Args:
        predictions: binary array (0/1) per timestep
        labels: SepsisLabel array (0/1) per timestep
        min_consecutive: hysteresis — require this many consecutive 1s
            before the alarm is considered to have fired.
        warmup_hours: suppress alarms in the first N timesteps (rolling
            features not yet warm; early-ICU baseline still stabilizing).

    Returns:
        Utility score for this patient.
    """
    is_sepsis = np.any(labels == 1)
    t_alarm = _first_consecutive_alarm(predictions.astype(int), min_consecutive, warmup_hours)
    has_alarm = t_alarm is not None

    if is_sepsis:
        t_onset = int(np.argmax(labels == 1))
        if has_alarm:
            dt = t_alarm - t_onset
            return _utility_tp(dt)
        else:
            return U_FN
    else:
        if has_alarm:
            return U_FP
        else:
            return U_TN


def compute_normalized_utility(
    df: pd.DataFrame,
    pred_col: str = "prediction",
    label_col: str = "SepsisLabel",
    patient_col: str = "patient_id",
    min_consecutive: int = 1,
    warmup_hours: int = 0,
) -> dict[str, float]:
    """Compute normalized utility score across all patients.

    Returns dict with raw_utility, max_utility, normalized_utility, and
    per-category counts.
    """
    raw_utility = 0.0
    max_utility = 0.0
    counts = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}

    for _pid, group in df.groupby(patient_col):
        preds = group[pred_col].values.astype(int)
        labels = group[label_col].values.astype(int)

        u = compute_patient_utility(
            preds,
            labels,
            min_consecutive=min_consecutive,
            warmup_hours=warmup_hours,
        )
        raw_utility += u

        is_sepsis = np.any(labels == 1)
        has_alarm = _first_consecutive_alarm(preds, min_consecutive, warmup_hours) is not None

        if is_sepsis:
            # Best possible: predict at optimal time
            max_utility += U_TP_MAX
            if has_alarm:
                counts["tp"] += 1
            else:
                counts["fn"] += 1
        else:
            # Best possible: no alarm
            max_utility += U_TN
            if has_alarm:
                counts["fp"] += 1
            else:
                counts["tn"] += 1

    normalized = raw_utility / max_utility if max_utility != 0 else 0.0

    return {
        "normalized_utility": normalized,
        "raw_utility": raw_utility,
        "max_utility": max_utility,
        **counts,
    }
