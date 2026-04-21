# Remote Patient Monitoring — Sepsis Early Warning

> Hệ thống giám sát bệnh nhân ICU + dự đoán sepsis sớm 6 giờ bằng ML. Đồ án môn Emerging Technologies — nhóm 4 người, học kỳ 2 năm 4.

[![CI](https://github.com/MinhNguyen1007/Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis/actions/workflows/ci.yml/badge.svg)](https://github.com/MinhNguyen1007/Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis/actions/workflows/ci.yml)
[![CD](https://github.com/MinhNguyen1007/Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis/actions/workflows/cd.yml/badge.svg)](https://github.com/MinhNguyen1007/Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis/actions/workflows/cd.yml)

## Đọc file này nếu bạn vừa clone về

1. Chạy **[Quick demo](#quick-demo-15-phút)** để thấy hệ thống chạy (15 phút).
2. Đọc **[CLAUDE.md](./CLAUDE.md)** — context chính thức của project, mục 12 ghi trạng thái hiện tại từng module.
3. Đọc **[docs/walkthrough-output.md](./docs/walkthrough-output.md)** — tour 20 output lệnh giải thích luồng dữ liệu end-to-end.
4. Xem phần **[Onboarding theo role](#onboarding-theo-role)** bên dưới để biết bạn nên tập trung thư mục nào.

---

## Hệ thống làm gì

```
Simulator (PhysioNet .psv)
       │ hourly rows
       ▼
  Kinesis (LocalStack)
       │
       ▼
  Consumer  ──► DynamoDB (131 features)
       │    ──► Redis (raw vitals, proba history)
       │    ──► S3 Parquet (cold storage)
       │
       ▼ HTTP POST /predict
  FastAPI + LightGBM (MLflow loaded)
       │
       ├── PostgreSQL (alerts, users)
       └── WebSocket /ws/alerts ─► React Dashboard
```

**Features chính:** 131 features/hour (120 rolling stats + 8 missing indicators + 3 clinical scores), LightGBM AUROC 0.81, hysteresis 6h chống alert fatigue, RBAC 3 role (admin/doctor/viewer), inference p95 < 300ms.

Chi tiết kiến trúc: [CLAUDE.md §2](./CLAUDE.md).

---

## Quick demo (15 phút)

### Yêu cầu

- **Windows 11** với PowerShell 5+ (script dev-up viết cho Windows — macOS/Linux xem [Chạy thủ công](#chạy-thủ-công-macoslinux))
- **Docker Desktop** đang chạy
- **Python 3.11** + **Node.js 20+**
- (Optional) Dataset PhysioNet trong `data/raw/training_setA/` — xem [Tải dataset](#tải-dataset)

### Setup lần đầu

```powershell
# 1. Clone
git clone https://github.com/MinhNguyen1007/Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis.git
cd Project_CongNgheMoiTrongPhatTrienUngDung_rpm_sepsis

# 2. Python venv + dependencies (3 module riêng)
python -m venv .venv
.venv\Scripts\activate
pip install -r data-pipeline/requirements.txt
pip install -r app/backend/requirements.txt
pip install -r ml/requirements.txt
pip install pre-commit pytest

# 3. Frontend dependencies
cd app\frontend
npm ci
cd ..\..

# 4. Pre-commit hooks (chạy tự động trước mỗi commit)
pre-commit install

# 5. Copy env template
copy .env.example .env
```

### Chạy hệ thống

```powershell
# Bật toàn bộ stack (docker-compose + 3 service native)
.\scripts\dev-up.ps1
```

Script này sẽ:

1. `docker-compose up -d` 6 core service (LocalStack, Postgres, Redis, MinIO, MLflow, MinIO init)
2. Verify MLflow reachable
3. Spawn 3 cửa sổ PowerShell: **backend** (uvicorn :8000), **frontend** (vite :5173), **consumer** (Kinesis poll)

Khi tất cả xanh, mở trình duyệt: <http://localhost:5173>.

**Default login:** `admin` / `admin123` (tự seed vào Postgres khi backend khởi động lần đầu).

### Chạy simulator để có dữ liệu

```powershell
# Simulator replay 10 bệnh nhân với tốc độ 1 record/giây
python data-pipeline\simulator\run.py --patients 10 --speed 1s
```

Consumer sẽ tiếp nhận → compute features → gửi `/predict` → dashboard hiện patient card + alert nếu sepsis risk cao.

### Tắt tất cả

```powershell
.\scripts\dev-down.ps1
```

---

## Service URLs

Khi `dev-up.ps1` chạy xong, các cổng local:

| Service                | URL                          | Login / Note                                        |
| ---------------------- | ---------------------------- | --------------------------------------------------- |
| **Dashboard**          | <http://localhost:5173>      | `admin` / `admin123` (hoặc tạo user mới qua /admin) |
| **Backend API + docs** | <http://localhost:8000/docs> | Swagger UI tự động, JWT bearer auth                 |
| **MLflow**             | <http://localhost:5000>      | Experiment + Registry UI                            |
| **MinIO console**      | <http://localhost:9001>      | `minioadmin` / `minioadmin123`                      |
| **Grafana**            | <http://localhost:3000>      | `admin` / `admin` (profile `monitoring`)            |
| **Prometheus**         | <http://localhost:9090>      | profile `monitoring`                                |
| **LocalStack**         | <http://localhost:4566>      | `awslocal` CLI để thao tác Kinesis/DynamoDB/S3      |
| **Postgres**           | `localhost:5432`             | credentials trong `.env`                            |
| **Redis**              | `localhost:6379`             | `patient:<id>:vitals`, `patient:<id>:proba_history` |

Monitoring stack (Grafana + Prometheus) chỉ khởi động với profile:

```powershell
docker-compose --profile monitoring up -d
```

---

## Onboarding theo role

Team có 4 vai trò, mỗi người tập trung 1 module. Tất cả đều chạy chung `dev-up.ps1`.

### Role A — Data & Streaming

**Thư mục chính:** [`data-pipeline/`](./data-pipeline/)

- `simulator/run.py` — replay PhysioNet `.psv` vào Kinesis
- `consumer/handler.py` — Kinesis poll + feature engineering stateful + write DynamoDB/S3/Redis
- `consumer/feature_engineer.py` — 131 features/hour (rolling stats, missing indicators, qSOFA/SIRS)
- `consumer/validator.py` — validate vital signs theo khoảng sinh lý

**Đọc trước:** CLAUDE.md §12.2 "Module A: Data Pipeline" + code comment trong `feature_engineer.py`.

**Test chạy module:**

```powershell
pytest tests\unit\test_feature_engineer.py tests\unit\test_validator.py -v
```

### Role B — ML

**Thư mục chính:** [`ml/`](./ml/)

- `ml/src/preprocess.py` — load 40,336 `.psv` → split 70/15/15 theo patient ID
- `ml/src/build_features.py` — **reuse** `FeatureEngineer` từ `data-pipeline` (tránh training-serving skew — quyết định #14 CLAUDE.md)
- `ml/src/train_lgbm.py` — LightGBM + MLflow logging + tune 2D grid threshold × k_consecutive
- `ml/src/utility_score.py` — PhysioNet Utility Score + hysteresis (k hour consecutive rule)
- `ml/src/evaluate.py` — full eval: AUROC, AUPRC, SHAP, per-patient CM, alert-ahead-time

**Đọc trước:** CLAUDE.md §12.2 "Module B: ML" (model v4 đã lock production), quyết định #15–24.

**Train 1 model mới:**

```powershell
python ml\src\train_lgbm.py --experiment sepsis-lgbm-v5 --register
```

MLflow registry: <http://localhost:5000>.

### Role C — MLOps

**Thư mục chính:** [`mlops/`](./mlops/), [`.github/workflows/`](./.github/workflows/), [`docker-compose.yml`](./docker-compose.yml)

- `mlops/mlflow/` — MLflow Dockerfile (Python 3.11 + boto3 + psycopg2)
- `mlops/drift/check.py` — Evidently `DataDriftPreset` + Slack webhook, HTML report
- `mlops/monitoring/` — Prometheus config + Grafana 7-panel dashboard
- `.github/workflows/` — 4 workflow: `ci.yml`, `integration.yml`, `cd.yml`, `drift.yml` (cron hàng tuần)

**Đọc trước:** CLAUDE.md §12.2 "Module C: MLOps", [`docs/walkthrough-output.md`](./docs/walkthrough-output.md) section Prometheus + CI/CD.

**Trigger drift check manual:**

```powershell
python mlops\drift\check.py --reference data\features\train.parquet --current data\features\val.parquet --sample 10000
```

### Role D — Full-stack

**Thư mục chính:** [`app/backend/`](./app/backend/) + [`app/frontend/`](./app/frontend/)

**Backend (FastAPI):** 13 endpoints — 3 predict/health, 5 patients/alerts, 5 auth. Model load từ MLflow registry qua `MODEL_URI`. Async SQLAlchemy + asyncpg, Redis sync client, JWT bcrypt.

**Frontend (React 19 + Vite 8 + Tailwind 4):** 5 screen — Login, PatientList, PatientDetail, AlertsFeed (dual-tab Live/History), AdminSettings. Zustand auth store + TanStack Query polling + WebSocket alert stream.

**Đọc trước:** CLAUDE.md §12.2 "Module D", quyết định #25–41 (Tailwind 4, Zustand selector pitfall, RBAC pattern).

**Chạy test integration:**

```powershell
# Cần backend đang chạy trên :8000 (dev-up.ps1 đã spawn)
pytest tests\integration\ -v -m integration
```

---

## Quality gate trước khi commit

Trước mỗi PR, chạy:

```powershell
pre-commit run --all-files          # 13 hook: ruff, mypy, bandit, prettier, gitleaks...
pytest tests\unit\ -v               # 26 unit test, ~3s
pytest tests\integration\ -v        # 11 test, ~72s, cần backend chạy
cd app\frontend && npm run lint     # ESLint + TypeScript strict
```

Hoặc gọi slash command trong Claude Code: `/check-quality` — chạy full gate cùng lúc.

---

## Common tasks

### Train & register model mới

```powershell
# Train LightGBM, log MLflow, register vào 'sepsis-lgbm-prod'
python ml\src\train_lgbm.py --experiment sepsis-lgbm-v6 --register

# Evaluate model đã register
python ml\src\evaluate.py --model-uri models:/sepsis-lgbm-prod/latest

# Backend pick up model mới — restart
.\scripts\dev-down.ps1 ; .\scripts\dev-up.ps1
```

### Load test

```powershell
cd tests\load
locust -f locustfile.py --headless -u 20 -r 5 -t 20s --host http://localhost:8000
```

Baseline kỳ vọng: `/predict` p95 < 500 ms ([reports/load/baseline_stats.csv](./reports/load/baseline_stats.csv)).

### Tải dataset

1. Đăng ký PhysioNet: <https://physionet.org/content/challenge-2019/>
2. Tải `training_setA.zip` + `training_setB.zip` (~2 GB)
3. Giải nén vào `data/raw/training_setA/` và `data/raw/training_setB/`
4. Check: `python -c "from pathlib import Path; print(len(list(Path('data/raw').rglob('*.psv'))))"` — mong đợi `40336`

**Không commit dataset.** `.gitignore` đã chặn `*.psv` + `data/raw/`.

### Chạy thủ công (macOS/Linux)

Nếu không dùng Windows, `dev-up.ps1` không chạy được. Thay bằng:

```bash
docker-compose up -d                                          # core services
bash infra/localstack/init-aws.sh                             # tạo Kinesis + DynamoDB + S3
(cd app/backend && uvicorn main:app --reload --port 8000) &   # backend
(cd app/frontend && npm run dev) &                            # frontend
python data-pipeline/consumer/handler.py &                    # consumer
```

---

## Repo structure

```
.
├── .claude/              # skills, agents, commands (commit) + settings.local.json (ignore)
├── .github/workflows/    # 4 workflow: ci, integration, cd, drift
├── app/
│   ├── backend/          # FastAPI 13 endpoints (Role D)
│   └── frontend/         # React 19 + Vite 8 + Tailwind 4 (Role D)
├── data-pipeline/        # Simulator + Consumer + Feature Store (Role A)
├── ml/                   # Preprocess + Train LightGBM + Evaluate (Role B)
├── mlops/                # MLflow Docker + Drift + Prometheus/Grafana (Role C)
├── infra/                # LocalStack init + Terraform (AWS Free Tier, sau)
├── scripts/              # dev-up.ps1, dev-down.ps1
├── tests/                # 26 unit + 11 integration + Locust load
├── docs/                 # report (chương 1-3), UML (8 diagram), walkthrough
├── CLAUDE.md             # context chi tiết (680 dòng) — TRẠNG THÁI HIỆN TẠI mục 12
├── docker-compose.yml    # 10 service, profiles core/monitoring/app
└── pyproject.toml        # ruff, mypy, bandit, pytest config
```

Chi tiết từng thư mục: [CLAUDE.md §4](./CLAUDE.md).

---

## Claude Code workflow

Project dùng Claude Code CLI để tăng tốc. Các convention đã setup:

- **Skills** (`.claude/skills/`) — scaffold UML, endpoint, component, ML experiment, report section
- **Subagents** (`.claude/agents/`) — `data-explorer`, `ml-researcher`, `medical-reviewer`, `vietnamese-report-writer`
- **Slash commands** (`.claude/commands/`) — `/standup`, `/train`, `/deploy-local`, `/review-medical`, `/write-report`, `/eda`, `/check-quality`
- **Hooks** (`.claude/settings.json`) — auto format ruff/prettier sau khi edit `.py`/`.ts`/`.tsx`

### Quy tắc vàng

1. **Đọc CLAUDE.md trước khi bảo Claude làm gì lớn** — đó là context chung.
2. **Mô tả intent, không dictate code.** Ví dụ: _"thêm endpoint acknowledge alert, cần auth"_ tốt hơn _"viết hàm tên `ack_alert`, params `alert_id: int`..."_.
3. **Review diff kỹ.** Claude có thể scaffold sai nếu context thiếu.
4. **Update CLAUDE.md** khi đổi kiến trúc/convention lớn.
5. **Không commit** `.env`, `.claude/mcp.json`, `.claude/settings.local.json`.

MCP setup (optional, dùng GitHub/Postgres tool trong Claude): xem [docs/mcp-setup.md](./docs/mcp-setup.md).

---

## Dataset & License

- Dataset: [PhysioNet Computing in Cardiology Challenge 2019](https://physionet.org/content/challenge-2019/) — 40,336 patient ICU, 41 cột, hourly rows
- Code: MIT
- Dataset: theo license PhysioNet (không commit vào repo)
