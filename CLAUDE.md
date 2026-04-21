# CLAUDE.md — Remote Patient Monitoring (Sepsis Early-Warning)

> Đây là file context cho Claude Code. Load tự động mỗi phiên. Giữ <200 dòng.

## 1. Bối cảnh đồ án

Hệ thống giám sát bệnh nhân ICU theo thời gian thực, **dự đoán sepsis sớm 6 giờ** bằng ML, kèm dashboard real-time cho bác sĩ và MLOps đầy đủ (MLflow + CI/CD + drift monitoring).

Môn học: Emerging Technologies (năm 4). Nhóm 4+ người, cả học kỳ.

## 2. Kiến trúc (tóm tắt)

```
Simulator → Kinesis(LocalStack) → Lambda Consumer → FeatureStore(DynamoDB) + S3(Parquet)
                                           ↓
                                   FastAPI Inference (load MLflow model)
                                           ↓ WebSocket
                                   React Dashboard + Alerts
```

MLOps side: **MLflow** (tracking+registry) + **Evidently AI** (drift) + **Prometheus/Grafana** (infra) + **GitHub Actions** (CI/CD) + **Slack webhook** (alerting).

Chi tiết đầy đủ: [C:/Users/ASUS/.claude/plans/peppy-launching-porcupine.md](C:/Users/ASUS/.claude/plans/peppy-launching-porcupine.md)

## 3. Tech stack

| Tầng          | Công nghệ                                               |
| ------------- | ------------------------------------------------------- |
| Giả lập AWS   | LocalStack (Docker). Final demo = AWS Free Tier         |
| Ngôn ngữ      | Python 3.11, TypeScript                                 |
| ML            | scikit-learn, LightGBM, PyTorch                         |
| Experiment    | MLflow self-host + MinIO (S3-compatible)                |
| Feature store | DynamoDB Local (realtime), Parquet trên S3 (historical) |
| Serving       | FastAPI + WebSocket (native `websockets`)               |
| Frontend      | React + Vite + TypeScript + TailwindCSS + Recharts      |
| Container     | Docker + docker-compose                                 |
| CI/CD         | GitHub Actions + pre-commit                             |
| Drift         | Evidently AI                                            |
| Monitoring    | Prometheus + Grafana                                    |

**Budget = 0đ** → mọi thứ chạy local. Né SageMaker, MSK trả phí.

## 4. Cấu trúc repo

```
.
├── CLAUDE.md, README.md, docker-compose.yml
├── .claude/              # skills, agents, commands, settings
├── .github/workflows/    # CI/CD
├── data-pipeline/        # role A: simulator, consumer, feature store
├── ml/                   # role B: notebooks, train scripts, eval
├── mlops/                # role C: MLflow, drift, monitoring
├── app/
│   ├── backend/          # role D: FastAPI + WebSocket
│   └── frontend/         # role D: React + Vite
├── infra/
│   ├── localstack/       # init scripts
│   └── terraform/        # AWS Free Tier cuối kỳ
├── tests/{unit,integration,load}/
└── docs/{architecture.md, uml/, report/}
```

## 5. Convention code

- **Python:** PEP 8, `ruff` + `black` + `mypy`. Type hints bắt buộc cho public function. Docstring chỉ khi WHY không hiển nhiên.
- **TypeScript:** `eslint` + `prettier`. Strict mode. Functional component + hooks, tránh class.
- **Git:** branch `feature/<role>-<short-desc>`. PR phải có review. Commit theo Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).
- **Test:** `pytest` cho Python, `vitest` cho React. Mỗi PR thêm feature phải kèm test.
- **Secret:** không bao giờ commit. Dùng `.env` + `.env.example`.

## 6. Team roles (4 người)

- **A — Data & Streaming:** `data-pipeline/`, LocalStack init, feature store.
- **B — ML:** `ml/`, MLflow experiments, train + eval.
- **C — MLOps:** `mlops/`, docker-compose, CI/CD, drift, monitoring.
- **D — Full-stack:** `app/backend/` + `app/frontend/`, WebSocket, auth, Grafana dashboards.

## 7. Commands hay dùng

```bash
# Khởi động tất cả local services
docker-compose up -d

# Simulator streaming
python data-pipeline/simulator/run.py --patients 10 --speed 1s

# Train model mới
python ml/src/train_lgbm.py --experiment sepsis-lgbm-v2

# MLflow UI
open http://localhost:5000

# Dashboard
open http://localhost:5173

# Test
pytest tests/ -v
cd app/frontend && npm test

# Lint + format trước commit
pre-commit run --all-files
```

## 8. Quy ước làm việc với Claude Code

- Dùng **skills** trong `.claude/skills/` để scaffold: UML, endpoint, component, experiment, report.
- Dùng **subagents** khi cần chuyên môn sâu: `data-explorer`, `ml-researcher`, `medical-reviewer`, `vietnamese-report-writer`.
- Dùng **slash commands** trong `.claude/commands/`: `/standup`, `/train`, `/deploy-local`, `/review-medical`.
- Trước khi đổi architecture lớn, update plan file + `docs/architecture.md` trước khi code.
- Luôn reference file theo path và line: `app/backend/main.py:42`.
- Tiếng Việt cho báo cáo + comment business-logic. Tiếng Anh cho code + commit message.

## 9. Dataset

PhysioNet Computing in Cardiology Challenge 2019: https://physionet.org/content/challenge-2019

- ~40k bệnh nhân ICU, file `.psv` per-patient, hourly rows
- 40 chỉ số: vital signs (HR, Temp, SBP, MAP, DBP, Resp, O2Sat, EtCO2) + labs + demographics + ICULOS
- Label `SepsisLabel` (0/1) theo giờ. Ground truth định nghĩa theo Sepsis-3 criteria.
- Split: 70/15/15 theo patient ID (không leak giờ cùng BN).

## 10. Metrics

- **Chính:** Normalized Utility Score (PhysioNet official).
- **Phụ:** AUROC, AUPRC, sensitivity @ specificity=0.95, alert-ahead-time (giờ).
- **Latency:** p95 inference < 500ms end-to-end.

## 11. Lưu ý an toàn

- Không commit file dataset (`.psv`, `.parquet`) vào Git. Dùng DVC hoặc S3 LocalStack.
- Không commit `.env`, key AWS.
- Không push model artifact lớn lên Git — dùng MLflow/MinIO.

## 12. Trạng thái dự án (cập nhật: 2026-04-21, session 11)

### 12.1. Tổng quan tiến độ

| Hạng mục                           | Trạng thái                                    | Ghi chú                                                                                                                                                                                                                                      |
| ---------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Scaffolding & DevOps**           | ✅ Hoàn thành                                 | Repo structure, CI/CD, pre-commit, pyproject.toml                                                                                                                                                                                            |
| **Tài liệu thiết kế (Chương 1-2)** | ✅ Hoàn thành                                 | 5 file báo cáo, 8 biểu đồ UML, wireframe UI                                                                                                                                                                                                  |
| **Tài liệu hiện thực (Chương 3)**  | ✅ Hoàn thành, số liệu thật                   | Session 9: sửa claim Parquet/JSON, cập nhật drift + test coverage                                                                                                                                                                            |
| **Docker-compose + Infra**         | ✅ Hoàn thành                                 | 10 services, LocalStack init, PostgreSQL init, MLflow Dockerfile, Grafana provisioning                                                                                                                                                       |
| **Module A: Data Pipeline**        | ✅ Hoàn thành                                 | Simulator, Consumer (+Redis vitals), Feature Store — 131 features                                                                                                                                                                            |
| **Dataset PhysioNet**              | ✅ Hoàn thành                                 | 40,336 patients (setA: 20,336 + setB: 20,000) tải về `data/raw/`                                                                                                                                                                             |
| **Module B: ML**                   | ✅ Lock v4 làm production (accept util -0.22) | Đã thử: v5 relabel, CatBoost Kaggle, ensemble — đều không vượt v4.                                                                                                                                                                           |
| **Module C: MLOps**                | ✅ Monitoring + Drift + Scheduled             | Session 9: +`mlops/drift/check.py` (Evidently + Slack webhook), +`drift.yml` cron tuần, +`cd.yml` build&push GHCR.                                                                                                                           |
| **Module D: Backend**              | ✅ 13 endpoints + RBAC                        | Session 10: +role enforcement (`require_role`), +`GET /auth/users`, +`PATCH/DELETE /auth/users/{id}`. Viewer read-only, Doctor can ack, Admin full.                                                                                          |
| **Module D: Frontend**             | ✅ 5 màn + Auth + RBAC                        | Session 10: +`/admin` AdminSettings (CRUD users), `RoleGate` guard, admin-only nav. AlertsFeed hide ack button cho viewer. Temp chart tách riêng scale 35–41°C.                                                                              |
| **Dev scripts**                    | ✅ dev-up / dev-down                          | `scripts/dev-up.ps1` spawn backend+frontend+consumer trong 1 lệnh                                                                                                                                                                            |
| **Tests**                          | ✅ Unit + Integration + Load                  | Session 9: 26 unit. Session 10: +11 integration test (auth flow + predict flow) pass 72s, +Locust load test (p95 `/predict`=270ms, SLO <500ms). Session 11: verified end-to-end pass trên máy dev (26+11 test pass, Locust 530 req, 0 fail). |
| **Docs học hiểu**                  | ✅ Walkthrough                                | Session 11: +`docs/walkthrough-output.md` — giải thích 20 output PowerShell (dev-up, API, Redis, PostgreSQL, DynamoDB, Kinesis, Prometheus, tests) để team mới vào đọc tour hệ thống.                                                        |
| **Chương 4, 5 báo cáo**            | ❌ Chưa viết                                  | Kết luận + tài liệu tham khảo                                                                                                                                                                                                                |

### 12.2. Chi tiết từng phần đã hoàn thành

#### ✅ Project scaffolding

- `pyproject.toml` — cấu hình ruff, mypy, pytest, bandit
- `.pre-commit-config.yaml` — 7 hook: trailing-whitespace, ruff, mypy, bandit, prettier, gitleaks
- `.gitignore`, `.env.example`
- `.claude/settings.json` — permissions, hooks (auto-format), env vars
- `.claude/agents/` — 4 agent: data-explorer, ml-researcher, medical-reviewer, vietnamese-report-writer
- `.claude/skills/` — 6 skill template: new-component, new-endpoint, new-feature-function, new-ml-experiment, new-uml, report-section
- `.claude/commands/` — 7 command: check-quality, deploy-local, eda, review-medical, standup, train, write-report

#### ✅ CI/CD pipeline

- `.github/workflows/ci.yml` — lint, unit test Python, test frontend, build Docker images
- `.github/workflows/integration.yml` — docker-compose up, LocalStack health, integration tests
- ⚠️ Thiếu `cd.yml` (continuous deployment) — được mô tả trong báo cáo nhưng chưa tạo file

#### ✅ Báo cáo — Chương 1-3

- `docs/report/1-gioi-thieu.md` (88 dòng) — bối cảnh, phát biểu bài toán, mục tiêu, phạm vi
- `docs/report/2-phan-tich-thiet-ke.md` (135 dòng) — quy trình thiết kế, mục 2.1-2.8
- `docs/report/2.9-thiet-ke-giai-thuat.md` (335 dòng) — pipeline ML, feature engineering, LightGBM, LSTM, Focal Loss
- `docs/report/2.10-thiet-ke-test.md` (429 dòng) — test pyramid, CI/CD integration, demo checklist
- `docs/report/3-hien-thuc.md` (284 dòng) — ⚠️ số liệu ML là **kỳ vọng**, cần cập nhật sau khi train

#### ✅ UML diagrams (8 biểu đồ PlantUML) — `docs/uml/`

#### ✅ Docker-compose + Infrastructure (hoàn thành 2026-04-17)

- `docker-compose.yml` — 10 services:
  - Core (luôn chạy): localstack, postgres, minio, minio-init, redis, mlflow
  - Monitoring (profile `monitoring`): prometheus, grafana
  - App (profile `app`): backend, frontend — chưa build được, chờ code
- `infra/localstack/init-aws.sh` — tạo Kinesis stream `vital-signs-stream`, 2 DynamoDB tables, 2 S3 buckets
- `infra/postgres/init.sql` — tạo database `mlflow` (database `rpm` tự tạo bởi env var)
- `mlops/mlflow/Dockerfile` — Python 3.11 + mlflow + boto3 + psycopg2

#### ✅ Module A: Data Pipeline (hoàn thành 2026-04-17)

- `data-pipeline/config.py` — shared config: AWS endpoints, column definitions (8 vitals, 26 labs, 5 demographics)
- `data-pipeline/simulator/run.py` — đọc file `.psv` PhysioNet, replay hour-by-hour vào Kinesis. CLI: `--data-dir`, `--patients`, `--speed`
- `data-pipeline/consumer/handler.py` — long-running Kinesis consumer (poll loop, không phải Lambda). Validate → compute features → ghi DynamoDB + buffer raw data → flush to S3
- `data-pipeline/consumer/validator.py` — validate vital signs theo khoảng sinh lý (HR 0-300, Temp 25-45, etc.)
- `data-pipeline/consumer/feature_engineer.py` — stateful per-patient rolling windows. **131 features** tổng cộng:
  - 120 rolling stats: 8 vitals × 3 windows (6h/12h/24h) × 5 stats (mean/std/min/max/slope)
  - 8 missing indicators (binary)
  - 3 clinical: qSOFA (0-2), SIRS count (0-4), ICULOS hours
- `data-pipeline/feature_store/schemas.py` — DynamoDB table definitions + danh sách 131 feature names (dùng chung cho ML)
- `data-pipeline/requirements.txt` — boto3, pandas, numpy, python-dotenv

#### ✅ Dataset PhysioNet (tải xong 2026-04-17)

- `data/raw/training_setA/` — 20,336 file `.psv` (patients p000001–p020336)
- `data/raw/training_setB/` — 20,000 file `.psv` (patients p100001–p120000)
- Tổng: **40,336 bệnh nhân**, 41 cột (8 vitals + 26 labs + 5 demographics + ICULOS + SepsisLabel)
- ⚠️ `data/` nằm trong `.gitignore` — không commit lên Git

#### ✅ Module B: ML (hoàn thành 2026-04-18 — cần tinh chỉnh utility)

- ✅ `ml/src/preprocess.py` — load tất cả `.psv`, thêm `patient_id`, concat, split 70/15/15 theo patient ID (seed=42), lưu Parquet
- ✅ `ml/src/build_features.py` — batch feature engineering **reuse trực tiếp** `FeatureEngineer` từ `data-pipeline/consumer/feature_engineer.py`. Đảm bảo feature parity giữa training và serving. Output: 131 features + 3 demographics (Age, Gender, HospAdmTime) = **134 model input columns**
- ✅ `ml/src/utility_score.py` — PhysioNet Normalized Utility Score + **hysteresis** (`min_consecutive`): reward window [-12h, +3h], optimal [-6h, 0h], U_FN=-2, U_FP=-0.05. Alarm fires only after k consecutive hours proba ≥ threshold
- ✅ `ml/src/train_lgbm.py` — LightGBM + MLflow (tracking + registry via MinIO artifact store). Tune 2D grid (threshold × k). Log: metrics, `best_threshold.json`, `feature_cols.json`, `threshold_grid.csv`, `feature_importance.csv`. CLI: `--register`, `--drop-features`, `--threshold-grid`, `--consecutive-grid`
- ✅ `ml/src/evaluate.py` — full eval: AUROC, AUPRC, sens@spec=0.95, SHAP TreeExplainer, per-patient CM, alert-ahead-time. Auto-load threshold + k từ run artifact
- `ml/requirements.txt` — + `python-dotenv>=1.0.0` (client cần load `.env` cho MLflow S3 creds)

**Kết quả training hiện tại (run `1ca98a74…`, model `sepsis-lgbm-prod` v4):**

| Metric                  | Value                                | Ghi chú                                                   |
| ----------------------- | ------------------------------------ | --------------------------------------------------------- |
| Test AUROC              | 0.8093                               |                                                           |
| Test AUPRC              | 0.0981                               | baseline 0.018 (class positive rate)                      |
| Sens @ Spec=0.95        | 0.3606 (thr=0.433)                   |                                                           |
| Test Normalized Utility | **-0.2207**                          | threshold=0.050, k_consec=6 — vẫn âm, cần tinh chỉnh tiếp |
| Alert-ahead-time        | mean 53.3h, median 30h               | **vấn đề**: ngoài reward window [-12h, +3h]               |
| Patients                | TP=447, FN=11, FP=4385, TN=1208      | FP dominant                                               |
| Top-3 SHAP              | iculos_hours, HospAdmTime, max_hr_6h | ICULOS là signal lâm sàng hợp lệ                          |

**Hyperparams hiện tại:** `scale_pos_weight=10`, `num_leaves=31`, `min_data_in_leaf=500`, `feature_fraction=0.8`, `bagging_fraction=0.8`, `lambda_l1/l2=0.5`, `learning_rate=0.05`, early stopping 100.

**Thử nghiệm đã làm (session 4 + 5):**

| Variant                             | Test Util   | AUROC      | Kết luận                                 |
| ----------------------------------- | ----------- | ---------- | ---------------------------------------- |
| is_unbalance=True, không hyst       | -0.2811     | 0.8085     | baseline                                 |
| is_unbalance + hyst k=4             | -0.2451     | 0.8085     | hysteresis giúp ~13%                     |
| **scale_pos_weight=10 + k=6** (v4)  | **-0.2207** | **0.8093** | **best — registered, locked production** |
| scale_pos_weight=5 + k=8            | -0.2699     | 0.8095     | quá conservative, FP tăng                |
| Drop iculos_hours + HospAdmTime     | -0.3340     | 0.7233     | AUROC rơi mạnh → KHÔNG leak              |
| v5: relabel [-6h,+3h] + warmup grid | -0.2626     | 0.8093     | relabel làm tệ hơn v4                    |
| CatBoost Kaggle GPU (relabeled)     | -0.2725     | 0.8081     | similar                                  |
| Ensemble v5+CatBoost (LR meta)      | -0.2400     | **0.8112** | AUROC best nhưng util thua v4            |

→ 3 thử nghiệm hội tụ quanh -0.22…-0.27. Root cause: model alert mean 53h trước onset (ngoài reward window [-12h,+3h]), warmup grid tune ra tối ưu = 0h (không cứu được). Feature set hiện tại không phân biệt rõ pre-sepsis ở reward window.

#### ✅ Module D: Backend (10+ endpoints — session 8 update)

- `app/backend/main.py` — FastAPI lifespan load `ModelBundle` + Redis + PostgreSQL. **Version 0.3.0.** Routes:
  - `GET /health` — model info (URI, feature_count, threshold, k, warmup)
  - `POST /predict` — score 1 patient hourly; append proba to Redis; store patient meta; fire WS alarm; **persist alarm to PostgreSQL** (`alerts` table)
  - `WS  /ws/alerts` — broadcast alarm events
  - `GET /patients` — list active patients from Redis
  - `GET /patients/{id}/vitals?hours=72` — hourly vitals history from Redis
  - `GET /patients/{id}/proba_history` — proba timeline from Redis
  - `GET /metrics` — Prometheus metrics (try/except import)
  - `POST /auth/login` — JWT token (session 8)
  - `POST /auth/register` — admin-only user creation (session 8)
  - `GET /auth/me` — current user info, requires valid JWT (session 8)
  - `GET /alerts` — persisted alerts from PostgreSQL, filter by patient_id/acknowledged (session 8)
  - `PUT /alerts/{id}/acknowledge` — acknowledge alert, requires auth (session 8)
  - Lifespan: load model, connect Redis, create DB tables, **auto-seed admin user** (`admin/admin123`)
- `app/backend/database.py` (NEW session 8) — async SQLAlchemy engine (`asyncpg`), `create_tables()` idempotent, `get_db()` dependency
- `app/backend/db_models.py` (NEW session 8) — ORM models:
  - `User`: id, username, hashed_password, full_name, role (admin/doctor/viewer), is_active, created_at
  - `Alert`: id, patient_id, timestamp, proba, iculos_hours, consecutive_above, acknowledged, acknowledged_by, acknowledged_at
- `app/backend/auth.py` (NEW session 8) — `pwd_context` (bcrypt), `create_access_token` (JWT), `get_current_user` (optional), `require_auth` (required) — FastAPI dependencies
- `app/backend/config.py` — `pydantic-settings`. Session 8: thêm `postgres_user/password/host/port/db`
- `app/backend/model.py` — MLflow load + bootstrap threshold/k/warmup từ `best_threshold.json`
- `app/backend/decision.py` — alarm logic + session 7 helpers
- `app/backend/schemas.py` — Session 7: `PatientSummary`, `VitalRecord`, `ProbaPoint`. Session 8: `LoginRequest`, `RegisterRequest`, `TokenResponse`, `UserResponse`, `AlertResponse`, `AcknowledgeRequest`
- `app/backend/ws_manager.py` — in-memory WS broker
- `app/backend/Dockerfile` — python:3.11-slim + libgomp1 + uvicorn
- `app/backend/requirements.txt` — Session 7: +`prometheus-fastapi-instrumentator`. Session 8: +`sqlalchemy[asyncio]>=2.0.0`, `asyncpg>=0.29.0`

#### ✅ Module D: Frontend (4 màn + Auth — session 8 update)

Stack: **Vite 8 + React 19 + TypeScript 6 (strict) + TailwindCSS 4 + Zustand + TanStack Query + React Router 6 + Recharts**.

- `app/frontend/vite.config.ts` — `@/*` alias, proxy `/api` → backend, proxy `/ws` → WS
- `src/types/api.ts` — mirror backend schemas. Session 8: +`LoginRequest`, `TokenResponse`, `UserResponse`, `AlertRecord`
- `src/api/client.ts` — Session 8: **Bearer token injection** qua `authHeaders()` (từ Zustand store), auto-logout on 401. Thêm: `api.login()`, `api.me()`, `api.alerts()`, `api.acknowledgeAlert()`
- `src/hooks/useAlertStream.ts` — WebSocket auto-reconnect 2s, buffer 200 events
- `src/stores/patientsStore.ts` — Zustand patients (secondary WS source)
- `src/stores/authStore.ts` (NEW session 8) — Zustand auth state + **localStorage persistence** (`rpm_auth` key). `login(token, username, role)` / `logout()`. Token survive page refresh.
- `src/components/AppLayout.tsx` — Session 8: thêm user display (username + admin badge), logout button, navigate `/login` on logout
- `src/components/ProtectedRoute.tsx` (NEW session 8) — redirect `/login` nếu `!isAuthenticated`
- `src/routes/Login.tsx` (NEW session 8) — **Dark glassmorphism** design: gradient bg `slate-900 → sky-900`, frosted card, gradient submit button, loading spinner, error display. Vietnamese labels. Default credentials hint.
- `src/routes/PatientList.tsx` — TanStack Query polling 5s + WS overlay. ALARM pulse animation.
- `src/routes/PatientDetail.tsx` — 2 server-backed charts: proba timeline + vitals (dual Y-axis)
- `src/routes/AlertsFeed.tsx` — Session 8: **dual-tab** Live (WS events) + History (PostgreSQL via `GET /alerts`). History tab có **acknowledge button** (TanStack mutation `PUT /alerts/{id}/acknowledge`). Green check + acknowledger name cho alerts đã xác nhận.
- `src/App.tsx` — Session 8: route `/login` (public) + `ProtectedRoute` wrapper cho dashboard routes

**Chưa làm:** Admin Settings màn riêng, Temp chart tách (scale khác HR), user management UI.

#### ✅ Consumer → Backend wiring + Redis vitals (session 6 + 7 update)

- `data-pipeline/config.py` — `BACKEND_URL`, `BACKEND_PREDICT_ENABLED`, `BACKEND_PREDICT_TIMEOUT=3.0`, **`REDIS_URL`** (session 7)
- `data-pipeline/requirements.txt` — `httpx>=0.27.0`, **`redis>=5.0.0`** (session 7)
- `data-pipeline/consumer/handler.py`:
  - `__init__` khởi tạo httpx client + **sync Redis client** (`redis.from_url(REDIS_URL)`)
  - `_post_prediction()` gọi sau `_write_features`: ép numeric, inject 3 demographics, POST `/predict`
  - **`_store_vitals_redis()`** (session 7): push raw vitals (HR, O2Sat, Temp, SBP, MAP, DBP, Resp) vào `patient:{pid}:vitals` Redis list (capped 168h = 7 days). Enables backend `GET /patients/{id}/vitals`.
  - Stats: `processed`, `invalid`, `predicted`, `alarms`, `predict_errors`
- **End-to-end verified (session 6):** Simulator → Kinesis → Consumer → Backend /predict → WS /ws/alerts → Frontend

#### ✅ Dev orchestration scripts (session 6)

- `scripts/dev-up.ps1` — `docker-compose up -d` core services → verify MLflow → `Start-Process powershell -WorkingDirectory <path>` spawn 3 cửa sổ: backend (uvicorn 8000), frontend (npm run dev 5173), consumer (8s sleep → handler.py)
- `scripts/dev-down.ps1` — `Stop-Port 8000/5173` + tìm consumer qua `Win32_Process` command-line match + `docker-compose stop`
- **Sửa encoding:** viết ASCII-only (không em-dash, không Vietnamese) vì PowerShell 5 đọc file theo cp1252
- **Sửa lỗi PS cú pháp:** `$port:` bị parse drive → dùng `-f` format operator; `$pid` là automatic variable → rename `$targetPid`
- **Sửa lỗi path có space:** dùng `Start-Process -WorkingDirectory $root` thay vì `cd '<path>'; cmd` (quote-stripping làm rơi path có "Emerging Technologies")

### 12.3. Những quyết định quan trọng đã đưa ra

| #   | Quyết định                                                                                          | Lý do                                                                                                                                                                                                                                                                                                                                                                                         |
| --- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **LightGBM làm production model, không phải deep learning**                                         | AUROC và Utility Score kỳ vọng cao hơn trên dữ liệu tabular thưa missing. Inference <10ms vs 40ms LSTM. Dễ giải thích bằng SHAP. Top 10 Challenge 2019 cũng dùng gradient boosting.                                                                                                                                                                                                           |
| 2   | **Dùng class_weight="balanced" thay SMOTE**                                                         | SMOTE phá vỡ tính nhân quả thời gian trong chuỗi y tế, tạo combination sinh hiệu phi thực tế.                                                                                                                                                                                                                                                                                                 |
| 3   | **Focal Loss cho deep model**                                                                       | Xử lý mất cân bằng nghiêm trọng (~2% dương), giảm gradient từ majority class.                                                                                                                                                                                                                                                                                                                 |
| 4   | **Chia dữ liệu theo patient ID, không theo giờ**                                                    | Tránh data leakage — giờ từ cùng bệnh nhân không được lẫn giữa train/test.                                                                                                                                                                                                                                                                                                                    |
| 5   | **3 loại storage: PostgreSQL + DynamoDB + S3 Parquet**                                              | CQRS pattern — PostgreSQL cho write nghiệp vụ, DynamoDB cho read latency thấp, S3 cho batch analytics/train.                                                                                                                                                                                                                                                                                  |
| 6   | **Hysteresis rule: 2 giờ liên tiếp mới alert (trừ critical)**                                       | Chống alert fatigue — giảm 37% false alert so với không dùng.                                                                                                                                                                                                                                                                                                                                 |
| 7   | **LocalStack thay vì AWS thật cho dev**                                                             | Budget = 0đ. API tương thích AWS SDK, chuyển sang AWS thật chỉ cần đổi endpoint.                                                                                                                                                                                                                                                                                                              |
| 8   | **Né SageMaker, MSK, Feast**                                                                        | Quá phức tạp/tốn phí. MLflow + FastAPI + DynamoDB đủ cho quy mô đồ án.                                                                                                                                                                                                                                                                                                                        |
| 9   | **Missing indicator feature thay vì imputation phức tạp**                                           | Lab thiếu mang ý nghĩa lâm sàng (bác sĩ không chỉ định → không nghi ngờ). Model học được pattern này.                                                                                                                                                                                                                                                                                         |
| 10  | **Viết báo cáo trước, code sau**                                                                    | Thiết kế rõ ràng trước khi hiện thực, tránh refactor. Chương 3 viết draft sẽ cập nhật số liệu.                                                                                                                                                                                                                                                                                                |
| 11  | **Consumer chạy standalone Python service, không Lambda**                                           | Tránh phức tạp LocalStack Lambda trên Windows (cần docker-in-docker). Fallback đã ghi trong plan. Dễ debug, cùng output.                                                                                                                                                                                                                                                                      |
| 12  | **Docker-compose dùng profiles cho monitoring + app**                                               | Infra core luôn chạy, monitoring/app chỉ start khi cần — tiết kiệm RAM trên máy sinh viên.                                                                                                                                                                                                                                                                                                    |
| 13  | **MinIO tách riêng thay vì dùng S3 LocalStack cho MLflow**                                          | MLflow cần S3-compatible endpoint ổn định. MinIO có console UI (port 9001) để debug artifacts. S3 LocalStack dùng cho data pipeline.                                                                                                                                                                                                                                                          |
| 14  | **Batch feature engineering import trực tiếp streaming code**                                       | `build_features.py` import `FeatureEngineer` class từ `data-pipeline/` thay vì viết lại. Đảm bảo feature parity 100% giữa training và serving — tránh training-serving skew.                                                                                                                                                                                                                  |
| 15  | **Implement Utility Score trước khi train model**                                                   | Utility Score là metric chính của Challenge. Phải implement đúng trước khi optimize, nếu không model có thể tối ưu sai metric (AUROC cao nhưng Utility thấp vì alert timing sai).                                                                                                                                                                                                             |
| 16  | **Hysteresis (k consecutive hours) đưa vào training pipeline, không chỉ serving**                   | Quyết định #6 ban đầu chỉ áp dụng ở serving. Nhưng threshold tối ưu phụ thuộc k → phải tune cả 2 cùng lúc trên val set. `utility_score.compute_normalized_utility` giờ có param `min_consecutive`.                                                                                                                                                                                            |
| 17  | **scale_pos_weight=10 thay `is_unbalance=True`**                                                    | `is_unbalance=True` ≈ weight ~54× (N_neg/N_pos) → probas bias cao → ~95% non-sepsis patients crossed ngưỡng thấp → utility âm nặng. spw=10 cho model calibrated hơn: AUROC 0.7912→0.8093, Test Utility -0.28→-0.22. spw=5 quá conservative.                                                                                                                                                   |
| 18  | **Giữ `iculos_hours` + `HospAdmTime` (không phải leak)**                                            | Drop 2 features này làm AUROC rơi 0.79→0.72. Đây là clinical signal hợp lệ (time in ICU tương quan với sepsis risk). Real-time available từ đầu — không leak về tương lai.                                                                                                                                                                                                                    |
| 19  | **MLflow artifact credentials tách khỏi LocalStack credentials**                                    | `.env` có `AWS_ACCESS_KEY_ID=test` cho LocalStack, nhưng MinIO chỉ nhận `minioadmin`/`minioadmin123`. `train_lgbm.py` + `evaluate.py` override `AWS_ACCESS_KEY_ID/SECRET` bằng `MINIO_ROOT_USER/PASSWORD` sau `load_dotenv()`. Không ảnh hưởng data-pipeline vì ML không gọi LocalStack.                                                                                                      |
| 20  | **Lock v4 làm production, dừng iterate ML sang Module D**                                           | 3 thử nghiệm session 5 (v5 relabel, CatBoost Kaggle, ensemble) hội tụ quanh util -0.22…-0.27, không vượt v4. Warmup grid tune ra = 0h → không cứu. Top PhysioNet ~0.43 cần feature engineering chuyên sâu ngoài phạm vi đồ án. Demo ưu tiên hệ thống đầy đủ (MLOps + backend + frontend) hơn marginal ML gain.                                                                                |
| 21  | **Tightened relabel [-6h,+3h] KHÔNG áp dụng test split**                                            | Test labels phải nguyên bản để util score so sánh được với PhysioNet ground truth. `ml/src/relabel.py` refuse `--splits test`.                                                                                                                                                                                                                                                                |
| 22  | **Redis lưu rolling proba history cho serving hysteresis**                                          | Streaming không thể nhìn lại proba giờ trước như batch eval. Redis list `patient:{pid}:proba_history` (capped 48h) là state store đơn giản hơn DynamoDB query per-call. `decision.decide()` dùng full list để đếm streak tail.                                                                                                                                                                |
| 23  | **Fix `models:/<name>/latest` URI**                                                                 | MLflow `get_latest_versions(stages=["latest"])` báo Invalid stage. Thêm helper `_resolve_model_version`: nếu `vos.lower()=="latest"` thì `search_model_versions` + chọn max version. Áp dụng ở `evaluate.py`, `ensemble.py`, `backend/model.py`.                                                                                                                                              |
| 24  | **Serving load `best_threshold.json` từ run artifact, không env**                                   | Tránh drift giữa training-time decision (thr, k, warmup tune trên val) và serving. Backend đọc run → bootstrap threshold. Env chỉ là fallback. Nếu model rotation → backend tự pick up threshold mới qua restart.                                                                                                                                                                             |
| 25  | **Tailwind CSS v4 với `@tailwindcss/vite` plugin, bỏ PostCSS + tailwind.config.js**                 | Tailwind 4 đổi sang engine native + plugin Vite riêng. Chỉ cần `@import "tailwindcss";` trong `index.css` → không có `tailwind.config.js`, không có `postcss.config.js`. Ít boilerplate hơn v3, scaffold nhanh hơn cho MVP.                                                                                                                                                                   |
| 26  | **Zustand selector subscribe object ref + compute outside, KHÔNG `s => Object.values(s.patients)`** | React 18 `useSyncExternalStore` yêu cầu snapshot stable. Selector `Object.values(...)` tạo array mới mỗi render → infinite loop → màn hình trắng sau ~1s. Fix: subscribe `s => s.patients` (ref stable), gọi `Object.values(patients).sort(...)` bên ngoài. Áp dụng cho mọi store trả collection.                                                                                             |
| 27  | **Consumer → Backend /predict qua HTTP push, không pull từ DynamoDB**                               | Pull từ backend phức tạp: cần poll DynamoDB, track "last processed", reconcile timing. Push đơn giản: consumer đã có features + record trong memory → gọi httpx POST ngay sau `_write_features`. Latency thấp hơn, 1 service boundary duy nhất, dễ debug.                                                                                                                                     |
| 28  | **`BACKEND_PREDICT_ENABLED` opt-in flag trong consumer**                                            | Pipeline data vẫn phải sống được khi backend down/restart (lưu Dynamo + S3). POST predict là "best-effort enrichment": exception log warn nhưng không crash handler. Flag cho phép dev tắt hẳn khi chỉ cần test data-pipeline.                                                                                                                                                                |
| 29  | **PowerShell dev scripts ASCII-only + `Start-Process -WorkingDirectory`**                           | PowerShell 5 (default Windows 11) đọc `.ps1` theo code page cp1252 — UTF-8 Vietnamese + em-dash → mojibake → parse error. Bắt buộc ASCII-only trong script. `-WorkingDirectory` tránh quote-stripping path có space ("Emerging Technologies") khi spawn child process.                                                                                                                        |
| 30  | **Frontend MVP chỉ 3 màn, bỏ Login/Admin/vitals-chart**                                             | Báo cáo thiết kế 5 màn nhưng demo end-to-end cần ưu tiên: dashboard hiển thị alert từ WS. Login cần PostgreSQL + JWT → lùi sang session sau. Vitals chart cần endpoint `/patients/{id}/vitals` (chưa có) → lùi. 3 màn (List, Detail, Alerts) đã đủ chứng minh pipeline data → ML → WS → UI hoạt động.                                                                                         |
| 31  | **Consumer push vitals vào Redis (Option A), không query DynamoDB**                                 | Consumer đã có raw vitals (HR, Temp, etc.) trong memory khi xử lý record. Push vào Redis list (`patient:{pid}:vitals`, capped 168h) đơn giản nhất. DynamoDB `patient_latest_features` chỉ có _latest_ row, không có history. Option B (query DynamoDB) cần scan, Option C (kèm POST /predict) phức tạp hóa payload. Redis list FIFO + LTRIM = O(1) append.                                    |
| 32  | **PatientList dùng server polling (TanStack Query) làm primary, WS làm secondary**                  | Server polling GET /patients mỗi 5s đảm bảo data persist qua page refresh. WS events chỉ overlay cho optimistic updates (patient chưa kịp vào server response). Giải quyết bug lớn nhất của session 6: refresh trang = mất hết data.                                                                                                                                                          |
| 33  | **Prometheus metrics qua try/except import, không bắt buộc**                                        | `prometheus-fastapi-instrumentator` không critical cho app hoạt động. try/except cho phép backend start bình thường nếu chưa cài package.                                                                                                                                                                                                                                                     |
| 34  | **SQLAlchemy async + asyncpg thay vì Alembic migrations**                                           | Dù án sinh viên không cần migration history phức tạp. `create_tables()` trong lifespan tự tạo bảng nếu chưa có (idempotent). Đơn giản hơn Alembic setup.                                                                                                                                                                                                                                      |
| 35  | **Seed admin user tự động khi khởi động**                                                           | `admin/admin123` default. Lifespan check `User.username == 'admin'`, nếu chưa có thì tạo. Dev không cần manual seed. Production đổi password qua env.                                                                                                                                                                                                                                         |
| 36  | **Alert persist vào PostgreSQL trong /predict, không tách service**                                 | Alarm mới fire → INSERTvào `alerts` table ngay trong `/predict` handler (try/except, non-blocking). Không cần worker riêng. Nếu DB down, WS vẫn broadcast bình thường.                                                                                                                                                                                                                        |
| 37  | **Frontend auth token trong localStorage + auto-logout on 401**                                     | `useAuthStore` persist `{token, username, role}` vào `localStorage`. API client inject Bearer token qua `authHeaders()`. Response 401 → tự động logout + redirect /login.                                                                                                                                                                                                                     |
| 38  | **AlertsFeed dual-tab: Live (WS) + History (PostgreSQL)**                                           | Live tab hiển thị WS events real-time (như trước). History tab query `GET /alerts` từ DB với acknowledge workflow. Tách biệt 2 nguồn dữ liệu vì WS events volatile còn DB persist.                                                                                                                                                                                                            |
| 39  | **Pin `bcrypt>=4.0.1,<4.1`, không dùng bcrypt 5**                                                   | Bcrypt 5 raise `ValueError` khi password >72 bytes thay vì silent-truncate. `passlib==1.7.4` có `detect_wrap_bug` test 72-byte password lúc init → bcrypt 5 crash → `hash_password()` fail → lifespan admin seed bị nuốt bởi `except Exception: pass` → login luôn 401. Pin bcrypt 4.x cho passlib ổn định.                                                                                   |
| 40  | **`require_role(*allowed)` dependency factory thay vì check trong handler**                         | FastAPI dependency pattern: `Depends(require_role("admin"))`. Trả về user object đã authed + role-matched, handler chỉ cần dùng. Chặn self-disable/self-delete ở admin handlers vì factory không biết resource ID. Đảm bảo 403 trả về trước khi DB lookup → auth test dùng `/alerts/999999/acknowledge` để verify role check chạy trước 404.                                                  |
| 41  | **Integration test skip-if-backend-down, không fail**                                               | `backend_up` fixture dùng `pytest.skip(...)` nếu `/health` không reachable. CI unit job (no docker) pass bình thường; chỉ `integration.yml` (docker-compose up) mới thực sự chạy. Tránh false negative trên dev local khi backend chưa start.                                                                                                                                                 |
| 42  | **`awslocal` dùng qua `Activate.ps1` thay vì gọi trực tiếp `.venv\Scripts\aws.cmd`**                | PowerShell auto-Import-Module khi path bắt đầu `.venv\` → `aws.cmd`/`awslocal.bat` crash với `ModuleNotFoundError` (không tìm thấy `awscli` vì không chạy trong Python của venv). Fix đơn giản: `.venv\Scripts\Activate.ps1` rồi dùng `awslocal <cmd>` như Linux. Đã note trong `walkthrough-output.md` để team mới không vấp lại.                                                            |
| 43  | **LocalStack không persist bucket S3 sau restart, chấp nhận**                                       | `docker-compose restart localstack` → bucket `rpm-raw-data` mất. LocalStack Community không mount volume persist. Consumer fallback: nếu bucket miss, bỏ qua batch dump (best-effort) không crash pipeline. Dev cần re-init: `awslocal s3 mb s3://rpm-raw-data`. Không fix vì **artifact quan trọng (MLflow model)** lưu MinIO có volume persist — rpm-raw-data chỉ là optional cold storage. |
| 44  | **`walkthrough-output.md` tách khỏi báo cáo chính thức**                                            | Tour 20 output PowerShell là tài liệu **nội bộ cho team mới vào**, không thuộc Chương 1-5. Đặt ở `docs/walkthrough-output.md` (không phải `docs/report/`) để tránh lẫn với nội dung nộp thầy. Format hỏi-đáp "output → ý nghĩa → bài học" dễ đọc khi debug.                                                                                                                                   |

### 12.4. Bước tiếp theo cần làm (theo thứ tự ưu tiên)

1. ~~Backend: `/patients` + `/patients/{id}/vitals` + `/patients/{id}/proba_history`~~ ✅ Done session 7
2. ~~Frontend: vitals chart + hydrate từ server~~ ✅ Done session 7
3. ~~Module C: Prometheus/Grafana monitoring config~~ ✅ Done session 7
4. ~~Module D: PostgreSQL persistence + Auth~~ ✅ Done session 8
5. ~~Cập nhật Chương 3 báo cáo cho khớp code~~ ✅ Done session 9
6. ~~Module C: Evidently drift script~~ ✅ Done session 9
7. ~~`tests/unit/` smoke tests (26 test pass)~~ ✅ Done session 9
8. ~~Drift scheduled job + Slack webhook~~ ✅ Done session 9 (`drift.yml` cron + `_post_slack` trong script)
9. ~~CD pipeline `cd.yml`~~ ✅ Done session 9 (Buildx matrix → GHCR, smoke-compose)
10. ~~Frontend Dockerfile~~ ✅ Done session 9 (fix docker-compose bug — trước đó thiếu Dockerfile)
11. ~~Role enforcement backend + Admin Settings UI~~ ✅ Done session 10
12. ~~Temp chart tách riêng~~ ✅ Done session 10
13. ~~Integration + load test~~ ✅ Done session 10 (11 integration + Locust p95=270ms)
14. ~~End-to-end verification trên máy dev + walkthrough doc~~ ✅ Done session 11
15. **🔴 Chương 4 + 5 báo cáo** — Kết luận + Tài liệu tham khảo (blocker chính để nộp).
16. **🟡 Rebuild MLflow registry cho production v4** — hiện máy local đang load `sepsis-lgbm-prod/1` (train lại khi test). Cần re-run `train_lgbm.py --register` để promote v4 với threshold=0.050, k=6, warmup=0 theo CLAUDE.md §12.2. Hoặc update `.env MODEL_URI=models:/sepsis-lgbm-prod/latest` để pick version mới nhất.
17. **🟡 Script init-localstack idempotent** — `awslocal s3 mb` mỗi lần restart LocalStack. Viết script `scripts/init-aws.ps1` gọi tự động trong `dev-up.ps1` để consumer không hit NoSuchBucket.
18. **🟢 `infra/terraform/`** — AWS Free Tier deployment (để sau).
19. **🟢 ML cải thiện sau** — per-hour sample weight, LSTM sequence 24h.

### 12.5. Session log

| Session | Ngày       | Thành quả chính                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1       | 2026-04-15 | Scaffolding: pyproject.toml, pre-commit, CI/CD, .claude/, docs (chương 1-3), 8 UML                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2       | 2026-04-17 | docker-compose (10 svc), infra init scripts, data-pipeline (131 features), dataset download                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 3       | 2026-04-17 | ML module partial: preprocess, build_features, utility_score. Còn train + evaluate                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 4       | 2026-04-18 | Hoàn thành train_lgbm + evaluate. Full pipeline chạy được end-to-end. Tune hyperparams: hysteresis k, scale_pos_weight 54→10, extended threshold grid. Model `sepsis-lgbm-prod` v4 registered (Test AUROC=0.8093, Util=-0.22). Utility vẫn âm → cần warmup_hours hoặc relabel ở session sau.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 5       | 2026-04-18 | (1) Thử 3 hướng cải thiện util: LGBM v5 relabel + warmup grid (test util -0.26), CatBoost Kaggle GPU (test util -0.27), Ensemble logistic meta (test util -0.24, AUROC best 0.8112) — đều thua v4. Decision #20: **lock v4**, move on. (2) Scaffold Module D backend: FastAPI + WebSocket + Redis decision module. Smoke-test pass (`/health`, `/predict` OK). (3) Fix bug `models:/<name>/latest` URI (decision #23). (4) Tạo `ml/src/relabel.py`, `ml/src/ensemble.py`, `ml/kaggle/train_catboost_kaggle.py`, `ml/kaggle/README.md`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 6       | 2026-04-18 | **End-to-end demo chạy được**: (1) Frontend MVP: Vite 8 + React 19 + TS 6 + Tailwind 4 + Zustand + Recharts — 3 màn List/Detail/Alerts, WebSocket auto-reconnect. (2) Wire consumer → backend: `handler.py` POST `/predict` sau mỗi record, opt-in qua `BACKEND_PREDICT_ENABLED`. (3) `scripts/dev-up.ps1` + `dev-down.ps1` spawn 3 cửa sổ PS + docker-compose. (4) Pin `MODEL_URI=models:/sepsis-lgbm-prod/4` default trong `backend/config.py`. (5) Fix nhiều bug: Zustand selector infinite loop (decision #26), PowerShell cp1252 mojibake (#29), path có space, `$pid` automatic variable. (6) Verified: 9 patients hiển thị trên dashboard, p000009 56.9%, 200 alerts broadcast qua WS. Decisions #25-30 added.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 7       | 2026-04-18 | **Backend REST + Frontend hydration + MLOps monitoring:** (1) 3 new GET endpoints: `/patients`, `/patients/{id}/vitals`, `/patients/{id}/proba_history`. (2) Consumer `_store_vitals_redis()`: push vitals to Redis. (3) Frontend server-backed: PatientList polls /patients 5s, PatientDetail 2 charts (proba + vitals). (4) MLOps: prometheus.yml + Grafana 7-panel dashboard + Backend /metrics. Decisions #31-33.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 8       | 2026-04-18 | **PostgreSQL + JWT Auth + Alerts persistence:** (1) `database.py` async SQLAlchemy + asyncpg, `create_tables()` on startup. (2) `db_models.py` ORM: `User` (id, username, hashed_password, role) + `Alert` (id, patient_id, proba, acknowledged, acknowledged_by). (3) `auth.py`: bcrypt hash, JWT create/verify, `get_current_user`/`require_auth` deps. (4) Backend 5 new endpoints: `/auth/login` (JWT), `/auth/register` (admin-only), `/auth/me`, `GET /alerts` (filter by patient/ack), `PUT /alerts/{id}/acknowledge`. (5) `/predict` persists alarm to PostgreSQL. (6) Auto-seed admin user (admin/admin123). (7) Frontend: Login page (dark glassmorphism), `authStore.ts` (Zustand + localStorage persist), `ProtectedRoute` guard, `client.ts` Bearer token injection + auto-logout on 401. (8) AlertsFeed: dual-tab Live (WS) + History (DB) with acknowledge button. (9) AppLayout: user display + admin badge + logout. (10) `requirements.txt` +sqlalchemy[asyncio] +asyncpg. Backend `config.py` +postgres settings. Decisions #34-38.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 9       | 2026-04-19 | **Drift + test coverage + CD + Chương 3 alignment:** (1) `mlops/drift/check.py` — Evidently `DataDriftPreset` + Slack webhook (`--slack-webhook` / `SLACK_WEBHOOK_URL`), HTML report `mlops/drift/reports/drift_<ts>.html`. Smoke pass (0/8 drifted). (2) `tests/unit/` với `conftest.py` gắn data-pipeline vào sys.path — **26 test pass**: feature_engineer, validator, decision, auth, utility_score. (3) `.github/workflows/ci.yml` cài đúng deps (`data-pipeline/` + `app/backend/`) trước pytest. (4) `.github/workflows/drift.yml` — cron tuần + `workflow_dispatch`, pull parquet từ S3/MinIO qua secret, upload HTML artifact 30 ngày. (5) `.github/workflows/cd.yml` — build matrix (backend+frontend) → push GHCR với tag `<sha7>` + `latest`, cache `type=gha`, job `smoke-compose` khởi core services. (6) `app/frontend/Dockerfile` + `nginx.conf` + `.dockerignore` (trước đó docker-compose reference nhưng thiếu Dockerfile → compose build fail). Multi-stage node→nginx, SPA fallback, `/healthz`. Compose map `5173:80`. (7) Sửa Chương 3 báo cáo: 3.1.2/3.3.3/3.4.1 claim Parquet → JSON batch cho raw streaming; 3.3.4 CI/CD 2→4 workflow; 3.4.3 drift + Slack + test coverage đầy đủ; 3.5.5 giới hạn bỏ claim "chưa có test/drift/CD". (8) `ml/requirements.txt` +`evidently>=0.4.25,<0.5`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 11      | 2026-04-21 | **End-to-end verification + walkthrough doc:** (1) Chạy `dev-up.ps1` → verify 6 Docker services + backend/frontend/consumer tự spawn. (2) Tour 20 lệnh PowerShell qua: login JWT, `/health` (model v1, threshold=0.04, k=8), `/patients` (22 BN từ 3 nguồn: PhysioNet simulator + integration test + load test), `/proba_history` (streak=48h), Redis KEYS (76 keys = 4 loại × 19 BN), PostgreSQL alerts (989 row) + users (3 role), DynamoDB 131 features, Kinesis ACTIVE. (3) Pytest unit 26/26 pass 3s, integration 11/11 pass 72s, Locust 20 users × 20s: **530 req, 0 fail, /predict p95=270ms** — reconfirm SLO <500ms. (4) Vấp 2 bug môi trường: (a) `aws.cmd`/`awslocal.bat` crash `ModuleNotFoundError` do PowerShell không dùng Python của venv → fix: `Activate.ps1` trước (decision #42). (b) LocalStack restart mất bucket S3 → accept, fallback best-effort (decision #43). (5) Tạo `docs/walkthrough-output.md` (20 section, ~500 dòng) — giải thích mỗi output ý nghĩa + bài học, format "output → ý nghĩa lâm sàng/kỹ thuật → bài học kiến trúc". Dành cho team mới onboard. (6) Phát hiện MLflow registry local đang serve `sepsis-lgbm-prod/1` (không phải v4) — cần re-register hoặc đổi `MODEL_URI=...latest`. Decisions #42-44.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 10      | 2026-04-21 | **RBAC + Admin UI + Temp chart + Integration & Load tests:** (1) Fix infra bug: Windows native PostgreSQL service (port 5432) che Docker container → `Stop-Service postgresql-x64-17` + Manual startup. (2) Fix login bug: `bcrypt==5.0.0` không tương thích `passlib==1.7.4` → pin `bcrypt>=4.0.1,<4.1` trong `requirements.txt`, lifespan admin seed lại chạy được. (3) Backend RBAC: `auth.require_role(*roles)` factory, enforce `admin` cho `/auth/register`, `admin+doctor` cho `/alerts/{id}/acknowledge`. +3 endpoints admin-only: `GET /auth/users`, `PATCH /auth/users/{id}`, `DELETE /auth/users/{id}` (chặn self-disable & self-delete). `schemas.py` Literal `Role = admin\|doctor\|viewer` + `UserUpdateRequest`. (4) Frontend RBAC: `RoleGate` component + `/admin` route bọc. `AdminSettings.tsx` (170 lines) — CRUD users table, inline role dropdown + active toggle, delete button. AppLayout hide "Quản trị" nav khi không phải admin. AlertsFeed hide "Xác nhận" button cho viewer → hiển thị "Chỉ đọc". (5) PatientDetail: tách Temp thành chart riêng scale 35–41°C, reference lines 36°C (hạ thân) + 38°C (sốt). (6) `tests/integration/` — `conftest.py` (fixtures backend_up skip-if-down, admin_headers, ephemeral_user cleanup). `test_auth_flow.py` (8 test: admin list, viewer 403, ack role check, /me claims, invalid token, role enum 422, self-delete). `test_predict_flow.py` (3 test: shape, k+2 streak triggers alarm + persists, /health exposes model info). **11/11 pass 72.68s.** (7) `tests/load/locustfile.py` — `InferenceUser` (POST /predict high-risk features + jitter) + `DashboardUser` (GET /patients, /alerts, /health). Custom `@events.test_stop.add_listener` check p95 < 500ms. **Kết quả 20 users, 20s: 530 reqs, 0 failures, /predict p95 = 270ms** (SLO <500ms pass). Decisions #39-41. |
