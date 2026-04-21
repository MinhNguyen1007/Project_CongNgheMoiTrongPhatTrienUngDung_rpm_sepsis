"""CatBoost GPU training on Kaggle — self-contained notebook cell.

Run this as a single cell in a Kaggle notebook (GPU T4 x2 or P100 enabled).
Feature parquet files must be uploaded as a Kaggle Dataset and attached to
the notebook (see ml/kaggle/README.md).

Outputs to /kaggle/working/:
    catboost_model.cbm           — trained model (CatBoost native format)
    val_proba.parquet            — per-row val probabilities (for ensembling)
    test_proba.parquet           — per-row test probabilities
    best_params.json             — tuned {threshold, min_consecutive, warmup_hours}
    test_metrics.json            — AUROC, AUPRC, Normalized Utility on test
    threshold_grid.csv           — full 3D grid sweep on val

Download all five artifacts and commit to MLflow locally for ensemble.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import average_precision_score, roc_auc_score

# ── Paths (edit if your dataset slug differs) ──────────────────────────────
INPUT_DIR = Path("/kaggle/input/sepsis-features-relabeled")  # uploaded dataset
OUT_DIR = Path("/kaggle/working")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LABEL_COL = "SepsisLabel"
PATIENT_COL = "patient_id"
ICULOS_COL = "iculos_hours"  # produced by FeatureEngineer
NON_FEATURE_COLS = {LABEL_COL, PATIENT_COL, "ICULOS"}

# ── Utility score (inlined from ml/src/utility_score.py) ───────────────────
DT_EARLY, DT_OPTIMAL, DT_LATE = -12, -6, 3
U_TP_MAX, U_FN, U_FP, U_TN = 1.0, -2.0, -0.05, 0.0


def _utility_tp(dt: int) -> float:
    if dt < DT_EARLY:
        return 0.0
    if dt <= DT_OPTIMAL:
        return U_TP_MAX * (dt - DT_EARLY) / (DT_OPTIMAL - DT_EARLY)
    if dt <= DT_LATE:
        return U_TP_MAX
    return U_FN


def _first_consecutive_alarm(preds: np.ndarray, k: int, warmup: int = 0):
    if warmup > 0:
        preds = preds.copy()
        preds[:warmup] = 0
    if k <= 1:
        return int(np.argmax(preds == 1)) if preds.any() else None
    if len(preds) < k:
        return None
    window = np.convolve(preds, np.ones(k, dtype=int), mode="valid")
    hits = np.where(window >= k)[0]
    return int(hits[0]) if len(hits) else None


def compute_normalized_utility(df, pred_col, min_consecutive=1, warmup_hours=0):
    raw_u, max_u = 0.0, 0.0
    counts = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    for _, group in df.groupby(PATIENT_COL):
        preds = group[pred_col].to_numpy().astype(int)
        labels = group[LABEL_COL].to_numpy().astype(int)
        is_sepsis = bool(labels.any())
        t_alarm = _first_consecutive_alarm(preds, min_consecutive, warmup_hours)
        has_alarm = t_alarm is not None
        if is_sepsis:
            t_onset = int(np.argmax(labels == 1))
            raw_u += _utility_tp(t_alarm - t_onset) if has_alarm else U_FN
            max_u += U_TP_MAX
            counts["tp" if has_alarm else "fn"] += 1
        else:
            raw_u += U_FP if has_alarm else U_TN
            counts["fp" if has_alarm else "tn"] += 1
    return {
        "normalized_utility": raw_u / max_u if max_u else 0.0,
        "raw_utility": raw_u,
        "max_utility": max_u,
        **counts,
    }


# ── Load data ──────────────────────────────────────────────────────────────
print("Loading splits...")
train_df = pd.read_parquet(INPUT_DIR / "train.parquet")
val_df = pd.read_parquet(INPUT_DIR / "val.parquet")
test_df = pd.read_parquet(INPUT_DIR / "test.parquet")

feature_cols = sorted(
    c for c in train_df.columns if c not in NON_FEATURE_COLS and train_df[c].dtype != object
)
print(f"  features: {len(feature_cols)}")
print(
    f"  train: {len(train_df):,} rows, {train_df[PATIENT_COL].nunique():,} patients,"
    f" pos={train_df[LABEL_COL].mean() * 100:.2f}%"
)
print(
    f"  val  : {len(val_df):,} rows, {val_df[PATIENT_COL].nunique():,} patients,"
    f" pos={val_df[LABEL_COL].mean() * 100:.2f}%"
)
print(
    f"  test : {len(test_df):,} rows, {test_df[PATIENT_COL].nunique():,} patients,"
    f" pos={test_df[LABEL_COL].mean() * 100:.2f}%"
)


def xy(df):
    X = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    y = df[LABEL_COL].astype(int).to_numpy()
    return X, y


X_tr, y_tr = xy(train_df)
X_va, y_va = xy(val_df)
X_te, y_te = xy(test_df)

# ── Train CatBoost on GPU ──────────────────────────────────────────────────
# scale_pos_weight=10 matches the LightGBM run (decision #17) — mild reweight
# so probas stay calibrated. CatBoost handles NaN natively via nan_mode="Min".
params = {
    "iterations": 5000,
    "learning_rate": 0.03,
    "depth": 8,
    "l2_leaf_reg": 3.0,
    "bagging_temperature": 0.5,
    "random_strength": 1.0,
    "border_count": 128,
    "nan_mode": "Min",
    "loss_function": "Logloss",
    "eval_metric": "AUC",
    "scale_pos_weight": 10.0,
    "task_type": "GPU",
    "devices": "0",
    "verbose": 200,
    "early_stopping_rounds": 200,
    "random_seed": 42,
}

print("\nTraining CatBoost (GPU)...")
model = CatBoostClassifier(**params)
model.fit(
    Pool(X_tr, y_tr, feature_names=feature_cols),
    eval_set=Pool(X_va, y_va, feature_names=feature_cols),
    use_best_model=True,
)

val_proba = model.predict_proba(X_va)[:, 1]
test_proba = model.predict_proba(X_te)[:, 1]

val_auroc = float(roc_auc_score(y_va, val_proba))
val_auprc = float(average_precision_score(y_va, val_proba))
test_auroc = float(roc_auc_score(y_te, test_proba))
test_auprc = float(average_precision_score(y_te, test_proba))
print(f"\nVal  AUROC={val_auroc:.4f}  AUPRC={val_auprc:.4f}")
print(f"Test AUROC={test_auroc:.4f}  AUPRC={test_auprc:.4f}")

# ── Tune decision params on val (threshold × k × warmup) ───────────────────
thr_grid = np.arange(0.02, 0.95, 0.02)
k_grid = [1, 2, 3, 4, 6, 8, 12, 16]
warmup_grid = [0, 6, 12, 18, 24, 36, 48]

pred_df = val_df[[PATIENT_COL, LABEL_COL]].copy()
results = []
best = {"normalized_utility": -np.inf}
for thr in thr_grid:
    pred_df["prediction"] = (val_proba >= thr).astype(int)
    for k in k_grid:
        for warmup in warmup_grid:
            u = compute_normalized_utility(pred_df, "prediction", k, warmup)
            row = {
                "threshold": float(thr),
                "min_consecutive": int(k),
                "warmup_hours": int(warmup),
                **u,
            }
            results.append(row)
            if u["normalized_utility"] > best["normalized_utility"]:
                best = row

best_thr = best["threshold"]
best_k = best["min_consecutive"]
best_warmup = best["warmup_hours"]
best_util_val = best["normalized_utility"]
print(f"\nBest val: util={best_util_val:.4f} thr={best_thr:.3f} k={best_k} warmup={best_warmup}h")

# ── Evaluate on test with tuned decision ───────────────────────────────────
test_pred_df = test_df[[PATIENT_COL, LABEL_COL]].copy()
test_pred_df["prediction"] = (test_proba >= best_thr).astype(int)
test_util = compute_normalized_utility(test_pred_df, "prediction", best_k, best_warmup)
print(f"\nTest Normalized Utility = {test_util['normalized_utility']:.4f}")
print(
    f"  patients: TP={test_util['tp']} FN={test_util['fn']}"
    f" FP={test_util['fp']} TN={test_util['tn']}"
)

# ── Save artifacts ─────────────────────────────────────────────────────────
model.save_model(str(OUT_DIR / "catboost_model.cbm"))

pd.DataFrame(
    {
        PATIENT_COL: val_df[PATIENT_COL].values,
        "ICULOS": val_df.get("ICULOS", pd.Series(np.arange(len(val_df)))).values,
        LABEL_COL: y_va,
        "proba": val_proba,
    }
).to_parquet(OUT_DIR / "val_proba.parquet", index=False)

pd.DataFrame(
    {
        PATIENT_COL: test_df[PATIENT_COL].values,
        "ICULOS": test_df.get("ICULOS", pd.Series(np.arange(len(test_df)))).values,
        LABEL_COL: y_te,
        "proba": test_proba,
    }
).to_parquet(OUT_DIR / "test_proba.parquet", index=False)

(OUT_DIR / "best_params.json").write_text(
    json.dumps(
        {
            "threshold": best_thr,
            "min_consecutive": best_k,
            "warmup_hours": best_warmup,
            "val_normalized_utility": best_util_val,
        },
        indent=2,
    )
)

(OUT_DIR / "test_metrics.json").write_text(
    json.dumps(
        {
            "val_auroc": val_auroc,
            "val_auprc": val_auprc,
            "test_auroc": test_auroc,
            "test_auprc": test_auprc,
            "test_normalized_utility": float(test_util["normalized_utility"]),
            "test_raw_utility": float(test_util["raw_utility"]),
            "test_patient_counts": {k: int(test_util[k]) for k in ("tp", "fn", "fp", "tn")},
            "best_iteration": int(model.tree_count_),
            "n_features": len(feature_cols),
        },
        indent=2,
    )
)

pd.DataFrame(results).to_csv(OUT_DIR / "threshold_grid.csv", index=False)

print(f"\nArtifacts saved to {OUT_DIR}:")
for p in sorted(OUT_DIR.iterdir()):
    print(f"  {p.name} ({p.stat().st_size / 1024:.1f} KB)")
