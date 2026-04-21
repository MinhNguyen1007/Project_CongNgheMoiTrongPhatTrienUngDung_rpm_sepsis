---
name: new-ml-experiment
description: Scaffold một script training ML mới với MLflow logging đầy đủ (params, metrics, artifacts, model registry). Dùng cho role ML khi thử model/feature mới cho bài toán sepsis.
---

# Skill: New ML Experiment

Tạo script training Python mới trong `ml/src/` với MLflow tracking đầy đủ. Luôn log đủ: params, metrics (AUROC, AUPRC, utility score), model artifact, feature importance.

## Quy trình

1. Hỏi user (nếu chưa rõ):
   - Tên experiment (vd `sepsis-lgbm-v3`, `sepsis-lstm-focal`)
   - Loại model: LightGBM / XGBoost / LSTM / Transformer / khác
   - Feature set: handcrafted / sequence / mixed
2. Tạo file `ml/src/train_<model>.py`.
3. Cấu trúc bắt buộc:
   - Load config từ `ml/configs/<exp>.yaml`
   - Load data (split theo patient ID, không leak)
   - Feature engineering (gọi `ml/src/features.py`)
   - Train + validate
   - Log MLflow: params, metrics, model, feature importance plot, confusion matrix
   - Đăng ký model vào registry nếu beat baseline
4. Tạo luôn file config YAML tương ứng.
5. Chạy thử command để verify: `python ml/src/train_<model>.py --config ml/configs/<exp>.yaml --dry-run`.

## Template script (LightGBM)

```python
"""Train LightGBM baseline cho sepsis prediction."""
from __future__ import annotations

import argparse
from pathlib import Path

import mlflow
import mlflow.lightgbm
import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import roc_auc_score, average_precision_score

from ml.src.features import build_features
from ml.src.data import load_split
from ml.src.metrics import normalized_utility_score


def main(config_path: Path, dry_run: bool = False) -> None:
    with config_path.open() as f:
        cfg = yaml.safe_load(f)

    mlflow.set_experiment(cfg["experiment_name"])

    with mlflow.start_run(run_name=cfg["run_name"]):
        mlflow.log_params(cfg["params"])
        mlflow.log_param("feature_set", cfg["feature_set"])

        X_train, y_train = load_split("train", cfg["data_version"])
        X_val, y_val = load_split("val", cfg["data_version"])

        X_train = build_features(X_train, cfg["feature_set"])
        X_val = build_features(X_val, cfg["feature_set"])

        if dry_run:
            print(f"Shapes: train={X_train.shape}, val={X_val.shape}")
            return

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        model = lgb.train(
            cfg["params"],
            train_data,
            num_boost_round=cfg["num_rounds"],
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
        )

        y_pred = model.predict(X_val)
        auroc = roc_auc_score(y_val, y_pred)
        auprc = average_precision_score(y_val, y_pred)
        utility = normalized_utility_score(y_val, y_pred)

        mlflow.log_metrics({
            "auroc": auroc,
            "auprc": auprc,
            "utility_score": utility,
        })
        mlflow.lightgbm.log_model(model, "model", registered_model_name=cfg["registered_name"])
        print(f"AUROC={auroc:.4f}, AUPRC={auprc:.4f}, Utility={utility:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(args.config, args.dry_run)
```

## Template config

```yaml
experiment_name: sepsis-lgbm
run_name: v3-handcrafted-featurev2
data_version: v1
feature_set: handcrafted_v2
registered_name: sepsis-lgbm-prod
num_rounds: 1000
params:
  objective: binary
  metric: auc
  learning_rate: 0.05
  num_leaves: 63
  feature_fraction: 0.8
  bagging_fraction: 0.8
  bagging_freq: 5
  is_unbalance: true
  verbose: -1
```

## Lưu ý

- Split phải theo patient ID (dùng `GroupKFold` hoặc split theo `patient_id % N`).
- Metric chính = `normalized_utility_score` (hàm từ PhysioNet), không chỉ AUROC.
- Log confusion matrix + PR curve làm artifact.
- Nếu model vượt baseline hiện tại trong registry, promote lên `Staging`.
