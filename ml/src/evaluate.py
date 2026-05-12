"""Metrics cho sepsis early-warning.

3 metric chính:
- AUROC: tổng quan, nhưng misleading khi imbalance (~2% positive).
- AUPRC: tốt hơn cho rare positive class.
- Utility score: official metric của PhysioNet Challenge 2019, thưởng dự đoán
  SỚM trước onset 6h và phạt false alarm/late alarm.

WHY tự implement Utility thay vì dùng sklearn: official challenge metric không
có trong sklearn. Công thức từ paper Reyna et al. 2019 (Crit Care Med):
  - dt_early=-12, dt_optimal=-6, dt_late=3 (giờ tính từ t_sepsis)
  - u_tp=1, u_fn=-2, u_fp=-0.05, u_tn=0
  - Reward tăng tuyến tính trong [-12, -6], giảm tuyến tính trong [-6, 3].
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

# Official PhysioNet 2019 Utility parameters.
DT_EARLY: int = -12
DT_OPTIMAL: int = -6
DT_LATE: int = 3
U_TP: float = 1.0
U_FN: float = -2.0
U_FP: float = -0.05
U_TN: float = 0.0


def compute_auroc_auprc(y_true: np.ndarray, y_score: np.ndarray) -> dict[str, float]:
    """AUROC + AUPRC. y_score là probability (0-1)."""
    return {
        "auroc": float(roc_auc_score(y_true, y_score)),
        "auprc": float(average_precision_score(y_true, y_score)),
    }


def _per_patient_utility(
    labels: np.ndarray,
    predictions: np.ndarray,
    hours: np.ndarray,
) -> tuple[float, float, float]:
    """Tính utility của 1 bệnh nhân theo công thức PhysioNet 2019.

    Args:
        labels: array (T,) — SepsisLabel theo giờ (label=1 nghĩa là sepsis sẽ
            xảy ra trong 6h tới, theo convention của challenge).
        predictions: array (T,) — binary prediction (0/1) đã threshold.
        hours: array (T,) — ICULOS theo giờ.

    Returns:
        (observed, best_possible, worst_possible) — 3 utility raw, dùng để
        normalize ở cấp population.
    """
    T = len(labels)

    # t_sepsis: giờ đầu tiên label=1 cộng 6 (vì label đặt sớm 6h trước onset).
    # Nếu patient không sepsis → t_sepsis = +inf (mọi pred=1 đều là FP).
    is_septic = labels.any()
    if is_septic:
        t_sepsis = int(hours[np.argmax(labels)]) + (-DT_OPTIMAL)  # +6
    else:
        t_sepsis = np.inf

    # Reward per-row: dt = hour - t_sepsis (âm = trước onset, dương = sau).
    u_observed = 0.0
    u_best = 0.0
    u_worst = 0.0
    for t in range(T):
        dt = hours[t] - t_sepsis
        pred = predictions[t]

        # Tính reward cho prediction=1 và prediction=0 tại giờ này.
        if is_septic:
            if dt < DT_EARLY:
                u_pos, u_neg = U_FP, 0.0
            elif DT_EARLY <= dt <= DT_OPTIMAL:
                # Tăng tuyến tính 0 → U_TP khi tiến gần optimal.
                ramp = (dt - DT_EARLY) / (DT_OPTIMAL - DT_EARLY)
                u_pos, u_neg = ramp * U_TP, 0.0
            elif DT_OPTIMAL < dt <= DT_LATE:
                # Giảm tuyến tính U_TP → U_FN sau khi vượt optimal.
                ramp = (dt - DT_OPTIMAL) / (DT_LATE - DT_OPTIMAL)
                u_pos = U_TP + ramp * (U_FN - U_TP)
                u_neg = ramp * U_FN
            else:  # dt > DT_LATE
                u_pos, u_neg = U_FN, U_FN
        else:
            u_pos, u_neg = U_FP, U_TN

        u_observed += u_pos if pred == 1 else u_neg
        u_best += max(u_pos, u_neg)
        u_worst += min(u_pos, u_neg)

    return u_observed, u_best, u_worst


def compute_utility(
    df: pd.DataFrame,
    pred_col: str = "prediction",
    label_col: str = "SepsisLabel",
    patient_col: str = "patient_id",
    hour_col: str = "ICULOS",
) -> float:
    """Normalized PhysioNet Utility (1.0 = perfect, 0.0 = không dự đoán gì).

    Score = (sum_observed - sum_worst) / (sum_best - sum_worst), aggregate
    over toàn bộ population (đúng theo official evaluation script).

    Args:
        df: phải có columns: patient_id, ICULOS, SepsisLabel, <pred_col>.
            `pred_col` là BINARY (0/1), tức đã apply threshold.
    """
    required = {patient_col, hour_col, label_col, pred_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    total_obs = total_best = total_worst = 0.0
    for _, g in df.sort_values([patient_col, hour_col]).groupby(patient_col, sort=False):
        obs, best, worst = _per_patient_utility(
            labels=g[label_col].to_numpy(),
            predictions=g[pred_col].to_numpy().astype(int),
            hours=g[hour_col].to_numpy(),
        )
        total_obs += obs
        total_best += best
        total_worst += worst

    denom = total_best - total_worst
    if denom == 0:
        return 0.0
    return (total_obs - total_worst) / denom


def compute_metrics(
    df: pd.DataFrame,
    y_score: np.ndarray,
    threshold: float = 0.5,
    label_col: str = "SepsisLabel",
    patient_col: str = "patient_id",
    hour_col: str = "ICULOS",
) -> dict[str, float]:
    """One-shot compute AUROC + AUPRC + Utility từ probability scores.

    Args:
        df: DataFrame (chỉ cần columns patient_id, ICULOS, SepsisLabel).
        y_score: probabilities (same length as df).
        threshold: cutoff để convert prob → binary cho Utility.
    """
    y_true = df[label_col].to_numpy()
    metrics = compute_auroc_auprc(y_true, y_score)

    df_eval = df[[patient_col, hour_col, label_col]].copy()
    df_eval["prediction"] = (y_score >= threshold).astype(int)
    metrics["utility"] = compute_utility(
        df_eval, label_col=label_col, patient_col=patient_col, hour_col=hour_col
    )
    metrics["threshold"] = threshold
    metrics["positive_rate"] = float(df_eval["prediction"].mean())
    return metrics
