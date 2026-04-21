---
description: Kickoff một training run ML với MLflow tracking
argument-hint: "<config-file> [--dry-run]"
allowed-tools: Bash(python:*), Bash(ls:*), Read, Glob
---

# Train Model

Chạy training script với config `$ARGUMENTS`.

## Quy trình

1. Verify MLflow đang chạy: `curl -sf http://localhost:5000 || echo "MLflow DOWN — run: docker-compose up -d mlflow"`.
2. Verify LocalStack đang chạy (nếu script load data từ S3): `curl -sf http://localhost:4566/_localstack/health`.
3. Identify script theo config:
   - Config chứa `lgbm` → `ml/src/train_lgbm.py`
   - Config chứa `lstm` → `ml/src/train_lstm.py`
   - Config chứa `transformer` → `ml/src/train_transformer.py`
4. Chạy: `python ml/src/train_<model>.py --config <config-file>` (thêm `--dry-run` nếu arg có).
5. Sau khi xong, in link MLflow run: `http://localhost:5000/#/experiments/<exp_id>/runs/<run_id>`.
6. Gợi ý next step: so sánh với baseline hiện tại trong registry.

## Lưu ý

- Nếu config không tồn tại, suggest tạo mới qua skill `new-ml-experiment`.
- Training dài >5 phút → nhắc user dùng `&` hoặc tmux để không chặn session.
- Sau training, log vào `docs/experiments.md` dòng mới: ngày, config, metric chính.
