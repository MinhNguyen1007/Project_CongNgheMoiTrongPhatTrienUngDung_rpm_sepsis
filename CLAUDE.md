# CLAUDE.md

## Project

Hệ thống Giám sát Bệnh nhân Từ xa với Streaming + MLOps. Đồ án môn Emerging Technologies.

**Bài toán:** Dự đoán sớm sepsis từ vital signs streaming.
**Dataset:** PhysioNet Challenge 2019 - Early Prediction of Sepsis from Clinical Data. Nguồn: https://physionet.org/content/challenge-2019/1.0.0/

* `training_setA/` (~20k bệnh nhân, hospital A) + `training_setB/` (~20k, hospital B)
* File `.psv` (pipe-separated), mỗi row = 1 giờ đo, 40 features (8 vital signs + 26 lab values + 6 demographics), target `SepsisLabel` (1 = sepsis trong 6h tới)
* **Path gốc:** `D:\S2_Year4\Emerging Technologies\Project\data\{training_setA, training_setB}` → copy vào `ml/data/`

**Vì sao dataset này phù hợp đề tài:**

* "Giám sát bệnh nhân từ xa" → vital signs theo giờ là dữ liệu monitoring chuẩn
* "Streaming" → time-series từng giờ → giả lập Kafka producer đẩy từng row tự nhiên
* "MLOps + retrain" → có label rõ ràng (SepsisLabel) để train/retrain có ý nghĩa
* Đây là dataset chuẩn của PhysioNet/Computing in Cardiology Challenge 2019, được dùng trong rất nhiều paper

## Triết lý

Đơn giản, đúng, đủ. Không over-engineer. Code rõ ràng, comment giải thích  **WHY** . Type hints đầy đủ.

## Trạng thái triển khai (cập nhật theo phase)

| Phase | Trạng thái | Nội dung đã làm                                                                                                           |
| ----- | ---------- | ------------------------------------------------------------------------------------------------------------------------- |
| T2    | ✅ Done    | `preprocess.py`, `evaluate.py` (AUROC/AUPRC/PhysioNet Utility), `train.py` + MLflow. 2 notebook EDA + train baseline.    |
| T3    | ✅ Done    | Postgres + Alembic + FastAPI skeleton (5 routers), SQLAlchemy 2.0 async, ORM cho 5 bảng, MLflow alias-based loader.       |
| T4    | ✅ Done    | Kafka KRaft (`apache/kafka:3.7.0`), producer streaming PSV, consumer thread + WS broadcast.                              |
| T5    | ✅ Done    | React 18 + Vite + Tailwind + TanStack Query. Dashboard, PatientDetail (Chart.js timelines), ModelRegistry, DriftReports.   |
| T6    | ✅ Done    | `drift_detect.py` (Evidently, NaN-safe filter), `retrain.py` (pull DB + train + promote-on-better-AUROC guard), APScheduler hook lifespan, manual triggers `POST /api/drift/check` + `POST /api/models/retrain`, 9 pytest. Subprocess dùng `asyncio.to_thread` (Windows compat). |
| T7.1  | ✅ Done    | Dockerize full stack: 3 Dockerfile (backend slim+alembic+uvicorn, frontend multi-stage Vite→nginx proxy, mlflow SQLite+serve-artifacts), `docker-compose.prod.yml` 5 services + healthcheck + Kafka multi-listener fix, smoke E2E pass local. |
| T7.2  | ✅ Done    | GitHub Actions CI (`.github/workflows/ci.yml`): 4 job lint (ruff+black) / test (9 pytest) / frontend (tsc) / build-push (3 image → `ghcr.io/minhnguyen1007/sepsis-{backend,frontend,mlflow}:{latest,sha}`). `pyproject.toml` ruff+black config line-length 100. |
| T7.3  | ✅ Done    | AWS deploy: EC2 t3.micro `i-0091b979449a1f1a2` Ubuntu 24.04 + swap 4GB + Docker 29, EBS 20GB, Elastic IP `54.254.229.98`. 7 containers healthy: Kafka + MLflow + Backend + Frontend + Postgres + Prometheus + Grafana. RDS PG 16.13 `sepsis-db.c32ay6yiscn7.ap-southeast-1.rds.amazonaws.com`. Model AUROC 0.838 register + alias `production`. Frontend live tại `http://54.254.229.98`. **CD còn thủ công** (SSH → docker compose pull + up) — mai thêm GitHub Actions auto-deploy job. |
| CN    | 🚧 WIP     | ✅ CD auto-deploy (`cd.yml` workflow_run → SSH pull+up EC2). ✅ Full pipeline demo được: stream → predict → alert → retrain → compare AUROC → promote/reject. ✅ Data validation (vital range check + `is_validated` flag), multi-model (XGBoost + LightGBM + RandomForest), scheduler toggle. ✅ Prometheus + Grafana monitoring (code done, deployed EC2: swap 4GB, port 3000 open, 7 containers). Còn: polish UI, viết báo cáo, record demo. **Khi resume:** start EC2 + RDS → chờ ~2 phút → containers tự restart. Set `$env:KAFKA_BOOTSTRAP_SERVERS="54.254.229.98:9092"` trước khi chạy producer. **AWS đang STOPPED (tiết kiệm chi phí) — start lại trước khi làm việc.** |

**Baseline AUROC: 0.838, AUPRC: 0.110, Utility: 0.825 @ thr=0.70** (full ~40k patient, MLflow registered alias `production`, version 1).

**EC2 gotchas (đã fix):**
- `docker-compose.aws.yml` phải dùng `--env-file .env.prod` khi chạy compose (không auto-load)
- Kafka `EXTERNAL` listener phải advertise `54.254.229.98:9092` (không phải `localhost`) để producer từ ngoài kết nối được
- S3 sync giới hạn 2000 files/set (`s3_sync.py max_files=2000`) + retrain `--max-patients 2000` tránh OOM/timeout trên t3.micro
- Port 9092 đã mở trên Security Group `sg-0d8fd628c391c5dd2`
- Prometheus + Grafana: swap tăng lên 4GB, port 3000 mở trên SG, 7 containers (thêm prometheus + grafana). Grafana UI tại `http://54.254.229.98:3000` (admin/admin, anonymous viewer enabled)

## Kiến trúc

```
Producer (.psv) → Kafka → Backend (FastAPI + Consumer)
                                 ├─ Validate vitals (clinical range check)
                                 ├─ Predict (XGBoost/LightGBM/RF via MLflow pyfunc)
                                 ├─ Save Postgres (mark is_validated=True/False)
                                 ├─ /metrics → Prometheus → Grafana (dashboard)
                                 └─ WebSocket → Frontend (React)

Scheduler (APScheduler trong backend, toggle via ENABLE_SCHEDULER env):
  - Daily 2AM: drift check (Evidently AI)
  - Weekly Sun 3AM: retrain 3 model types → promote best AUROC
  - Retrain chỉ dùng data is_validated=TRUE từ DB

Monitoring:
  - Prometheus scrape backend:8000/metrics mỗi 15s
  - Grafana :3000 dashboard auto-provisioned (request rate, latency, errors, in-flight)
```

## Cấu trúc thư mục

```
Project/                          # = project root (cwd)
├── backend/                      # FastAPI - xem backend/CLAUDE.md
│   └── app/
│       ├── main.py               # FastAPI + lifespan (load model + start consumer + scheduler)
│       ├── config.py             # Pydantic Settings (.env)
│       ├── schemas.py            # Pydantic response models
│       ├── ws_manager.py         # WebSocket broadcast singleton
│       ├── api/                  # patients, predictions, models, drift, websocket
│       ├── db/                   # base, models (ORM), crud
│       ├── ml/                   # loader (MLflow alias), features (PatientBuffer), predictor
│       ├── streaming/consumer.py # Kafka consumer thread + vital validation
│       ├── streaming/validation.py # Vital range check (8 vitals clinical range)
│       ├── scheduler/jobs.py     # APScheduler jobs (T6)
│       └── alembic/              # Migrations
├── frontend/                     # React + Vite - xem frontend/CLAUDE.md
│   └── src/
│       ├── api/client.ts         # axios per-endpoint
│       ├── types/api.ts          # match Pydantic schemas
│       ├── hooks/                # useWebSocket, usePatients, useAlerts, useModelInfo
│       ├── context/              # WebSocketContext, AlertsContext
│       ├── components/           # layout, common, patients, alerts, charts, dashboard
│       └── pages/                # Dashboard, PatientDetail, ModelInfo, DriftReports
├── ml/
│   ├── data/training_setA, training_setB   # PhysioNet (gitignore)
│   ├── src/                                 # preprocess, train, evaluate, drift_detect, retrain
│   └── notebooks/                           # 01_eda.ipynb, 02_train_baseline.ipynb
├── streaming/
│   ├── producer.py               # PSV → Kafka, supports interleave + rate limit
│   └── dev_predict_smoke.py      # Smoke test predict pipeline (không cần Kafka)
├── infra/
│   ├── docker-compose.yml        # Dev: Postgres 15 + Kafka 3.7 (apache/kafka)
│   ├── docker-compose.prod.yml   # Prod: 7 services (postgres+kafka+mlflow+backend+frontend+prometheus+grafana)
│   ├── Dockerfile.backend        # python:3.11-slim + alembic + uvicorn
│   ├── Dockerfile.frontend       # multi-stage Vite build → nginx
│   ├── Dockerfile.mlflow         # mlflow 2.22 + SQLite + serve-artifacts
│   ├── nginx.conf                # SPA fallback + reverse-proxy /api/ + /ws/
│   ├── prometheus.yml            # Prometheus scrape config (backend:8000/metrics)
│   ├── grafana/                  # Grafana provisioning + pre-built dashboard
│   │   ├── provisioning/datasources/prometheus.yml
│   │   ├── provisioning/dashboards/dashboards.yml
│   │   └── dashboards/fastapi.json   # 7-panel dashboard (rate, latency, errors, etc.)
│   └── .env.prod.example
├── .github/workflows/ci.yml      # T7.2: lint + pytest + frontend + build-push GHCR
├── venv/                         # 1 venv chung (gitignore)
├── requirements.txt              # ML + Backend + Streaming deps
├── pyproject.toml                # ruff + black config (line-length 100, target py311)
├── alembic.ini
├── .env.example
└── README.md
```

## Tech stack

* **Streaming:** `apache/kafka:3.7.0` (KRaft mode, no Zookeeper) + `kafka-python`
* **Backend:** FastAPI 0.110+ + SQLAlchemy 2.0 async + asyncpg + Pydantic 2
* **Frontend:** React 18 + Vite 5 + TypeScript + TailwindCSS 3 + Chart.js 4 (`react-chartjs-2`) + TanStack Query 5 + React Router 6
* **ML:** XGBoost 2 + LightGBM 4 + scikit-learn 1.4 (RandomForest) + MLflow 2.22 (alias-based registry, pyfunc loader model-agnostic)
* **Drift:** Evidently AI 0.4+
* **Scheduler:** APScheduler 3 async (chạy trong backend lifespan, không tách service)
* **DB:** PostgreSQL 15-alpine
* **Monitoring:** Prometheus + Grafana (auto-provisioned dashboard, `prometheus-fastapi-instrumentator`)
* **Deploy:** Docker Compose → AWS EC2 t3.micro + RDS free tier

## Key decisions

**Multi-model (XGBoost + LightGBM + RandomForest):** tabular + imbalance → boosting/ensemble. Retrain train cả 3 tuần tự → promote model có AUROC cao nhất. XGBoost/LightGBM handle NaN native, RandomForest wrap trong `Pipeline(SimpleImputer + RFC)`. Model load qua `mlflow.pyfunc` (model-agnostic). Train CPU 5-10 phút/model trên laptop FX506HC.

**Train trên laptop, không cần Kaggle:** Laptop ASUS TUF FX506HC (RTX 3050 4GB, 24GB RAM) dư sức cho XGBoost CPU 5-10 phút. Kaggle (P100/T4x2) chỉ cần khi muốn thử LSTM/Transformer làm baseline so sánh trong báo cáo (optional). Lý do chọn laptop: (1) tiện retrain auto qua APScheduler local, (2) không phụ thuộc Kaggle session timeout, (3) cùng môi trường venv với code production.

**Kafka thay vì Redis:** đề yêu cầu "Streaming" → industry standard. KRaft mode không cần Zookeeper, nhẹ hơn cho free tier.

**1 venv chung:** scope đồ án nhỏ, đỡ phức tạp setup. Tất cả deps (backend + ml + streaming) trong `requirements.txt`. Frontend dùng npm riêng.

**Drift + Schedule retrain:** Drift bắt concept drift sớm, schedule là safety net. Cả 2 log MLflow, chỉ promote khi AUROC tốt hơn.

**Notebook + Script kết hợp:** notebook cho EDA + train baseline lần đầu (dễ debug, visualize, làm báo cáo). Script `src/*.py` chứa logic có thể tái sử dụng + chạy headless cho retrain tự động.

**MLflow alias thay vì stage:** MLflow 2.9+ đã deprecate Stage (None/Staging/Production/Archived) — sẽ remove ở 3.x. Dùng alias `production` (URI `models:/sepsis-predictor@production`). Lợi thế: nhiều alias trên 1 version (canary/champion/challenger), pointer riêng không phá history.

**Data validation trước retrain:** Consumer validate vital signs theo clinical range (HR 20-300, Temp 25-45, ...) → lưu `is_validated` flag vào DB. Data vẫn lưu DB (monitoring) + vẫn predict real-time, nhưng retrain chỉ pull rows `is_validated=TRUE`. Ngăn data nhiễu/outlier ảnh hưởng model quality.

**Scheduler toggle:** `ENABLE_SCHEDULER=false` env var tắt APScheduler → retrain chỉ qua manual API. Hữu ích khi debug trên AWS hoặc muốn kiểm soát retrain thủ công.

## ML workflow

```
ml/
├── src/                          # Logic chính - import được từ cả notebook + scheduler
│   ├── preprocess.py             # load_psv_files(), feature_engineering(), split_train_val()
│   ├── train.py                  # train_model(train_df, val_df, model_type) -> (model, metrics)
│   ├── evaluate.py               # compute_metrics() - AUROC, AUPRC, Utility score
│   ├── drift_detect.py           # Evidently report, CLI: --mode daily
│   └── retrain.py                # CLI orchestrator, gọi từ APScheduler
└── notebooks/
    ├── 01_eda.ipynb              # Explore data, plot distributions, check missing
    ├── 02_train_baseline.ipynb   # Import từ src/ → train → MLflow → visualize
    └── 03_drift_analysis.ipynb   # Cho báo cáo: visualize drift reports
```

**Quy tắc:** Logic ở `src/*.py`, notebook chỉ import + visualize. Lý do: scheduler không gọi được `.ipynb` sạch, code trong notebook khó test/diff.

**Ví dụ:**

```python
# ml/src/train.py — hỗ trợ 3 model types
from ml.src.train import ModelType, train_model

model, metrics = train_model(train_df, val_df, model_type=ModelType.XGBOOST)
model, metrics = train_model(train_df, val_df, model_type=ModelType.LIGHTGBM)
model, metrics = train_model(train_df, val_df, model_type=ModelType.RANDOM_FOREST)

# CLI:
# python -m ml.src.train --model-type xgboost --register
# python -m ml.src.train --model-type lightgbm --register
# python -m ml.src.train --model-type random_forest --register
```

## Online retrain workflow (yêu cầu giảng viên)

Đề bài yêu cầu "data online để train lại model". Cách triển khai:

```
Producer giả lập "data online" → Kafka → Backend consumer
                                              ├─ Validate vitals (clinical range)
                                              ├─ Predict (pyfunc model-agnostic)
                                              └─ Lưu vital + is_validated flag vào Postgres
                                                                    │
                                                                    ▼
                                            Sau N giờ stream, DB có data mới (validated + invalid)
                                                                    │
                       ┌────────────────────────────────────────────┤
                       ▼                                            ▼
            (1) Drift check daily 2AM                  (2) Schedule weekly Sun 3AM
            Evidently so sánh:                         Retrain bất kể drift
            - Reference: training_setA gốc            (safety net)
            - Target: 24h vitals mới nhất từ DB
                       │                                            │
                       └────────────────┬───────────────────────────┘
                                        ▼
                            retrain.py:
                            1. Pull data mới từ Postgres (CHỈ is_validated=TRUE) + data gốc
                            2. Train 3 model: XGBoost + LightGBM + RandomForest (tuần tự)
                            3. So sánh AUROC cả 3 → chọn best
                            4. Best AUROC > production → set alias `production` trỏ version mới
                            5. Scheduler gọi loader.reload_model() → backend swap cache (không cần restart)
```

## Data validation & retrain safeguards

```
Kafka message → validate_vitals() → is_validated flag
                    │                      │
                    ├─ HR: 20-300          ├─ TRUE → retrain sẽ dùng row này
                    ├─ O2Sat: 0-100       └─ FALSE → lưu DB (monitoring) nhưng retrain bỏ qua
                    ├─ Temp: 25-45
                    ├─ SBP: 30-300        NaN/None → pass (PhysioNet có missing data)
                    ├─ MAP: 20-250        Giá trị ngoài range → fail → is_validated=FALSE
                    ├─ DBP: 10-200
                    ├─ Resp: 2-60
                    └─ EtCO2: 0-100
```

**Retrain safeguards:**
1. **Data validation gate:** chỉ `is_validated=TRUE` rows vào retrain.
2. **AUROC promotion guard:** model mới phải `auroc > production_auroc` mới promote.
3. **Multi-model comparison:** train 3 model types → chọn best AUROC → so với production.
4. **Early stopping:** XGBoost/LightGBM dừng sau 30 rounds val AUC không cải thiện.
5. **Baseline dilution:** retrain concat baseline 40k patients + DB data → data nhiễu bị pha loãng.
6. **Scheduler toggle:** `ENABLE_SCHEDULER=false` để tắt auto-retrain khi cần kiểm soát thủ công.

**Khi nào retrain:**

* **Drift-based:** `drift_share > 0.3` (env `DRIFT_FEATURES_THRESHOLD`) — Evidently DataDriftPreset.
* **Schedule-based:** Chủ nhật 3AM UTC, đảm bảo model không cũ.
* **Manual:** `python -m ml.src.retrain --reason manual` hoặc `POST /api/models/retrain` (đang xây ở T6).

**Vì sao 2 cơ chế:** drift bắt thay đổi sớm khi distribution thay đổi (ví dụ: bệnh viện mới, mùa dịch), schedule là safety net phòng drift detector bỏ sót.

## Setup

```bash
# 1. Tạo venv chung
python -m venv venv
venv\Scripts\activate              # Windows PowerShell. Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

# 2. Copy data (1 lần)
# Copy training_setA, training_setB từ D:\S2_Year4\...\data vào ml/data/

# 3. Copy .env
cp .env.example .env

# 4. Start Postgres + Kafka
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps   # đợi cả 2 service "healthy"

# 5. Apply DB migration
alembic upgrade head

# 6. Start MLflow tracking server (terminal riêng, giữ chạy)
mlflow ui --backend-store-uri ml/notebooks/mlruns --port 5000

# 7. Train baseline + register vào MLflow (3 model types)
#    - Cách A: chạy notebook ml/notebooks/02_train_baseline.ipynb
#    - Cách B: headless (train từng model type):
python -m ml.src.train --model-type xgboost --register
python -m ml.src.train --model-type lightgbm --register
python -m ml.src.train --model-type random_forest --register

#    Mở http://localhost:5000 → Models → sepsis-predictor → chọn version tốt nhất →
#    bấm "Add alias" → đặt alias = `production` (lowercase).

# 8. Start backend (terminal riêng)
uvicorn backend.app.main:app --reload --port 8000 --ws-ping-interval 25

# 9. Start frontend (terminal riêng)
cd frontend
cp .env.example .env
npm install
npm run dev    # http://localhost:5173

# 10. Stream data giả lập (terminal riêng)
python -m streaming.producer --patients p000001 p000009 p000015 p000022 --rate 20
```

**Smoke test predict pipeline (không cần Kafka):**

```bash
python -m streaming.dev_predict_smoke --patient p000009 --hours 60
```

## Timeline 1 tuần

| Ngày   | Trạng thái      | Việc                                                                                                                        |
| ------ | --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **T2** | ✅ Done         | `01_eda.ipynb`, `src/preprocess.py` + `src/train.py` + `src/evaluate.py`, `02_train_baseline.ipynb` train + register MLflow |
| **T3** | ✅ Done         | Postgres + Alembic, FastAPI skeleton, 5 REST endpoint, MLflow alias-based loader, ML inference (`PatientBuffer`)            |
| **T4** | ✅ Done         | Kafka KRaft local, producer interleave + rate, consumer thread, save DB, WebSocket broadcast                                |
| **T5** | ✅ Done         | React + Vite + Tailwind. Dashboard (list/alerts/stats), PatientDetail (vital + risk charts), ModelInfo, DriftReports        |
| **T6** | ✅ Done         | Evidently drift detect, retrain orchestrator, APScheduler jobs daily/weekly, manual trigger endpoints, 9 pytest, smoke test full chain |
| **T7** | 🚧 2/3 phase   | ✅ Dockerize (3 Dockerfile + compose.prod) · ✅ CI (lint/test/frontend/build-push GHCR) · 🚧 AWS deploy (code prep done, S3 upload training_setA in progress) |
| **CN** | ⬜ Todo         | Polish UI, viết báo cáo, record demo video                                                                                  |

## Database schema

```
patient(id, age, gender, unit1, unit2, hosp_adm_time, created_at)
vital(id, patient_id FK, hour, hr, o2sat, temp, sbp, map, dbp, resp, etco2,
      lab_values JSONB, sepsis_label, is_validated BOOL DEFAULT TRUE, created_at)
  UNIQUE(patient_id, hour), INDEX(patient_id, hour)
  -- is_validated: FALSE nếu vital ngoài clinical range → retrain filter bỏ
prediction(id, patient_id FK, hour, sepsis_risk, model_version, predicted_at)
  UNIQUE(patient_id, hour), INDEX(patient_id, hour)
model_version(version PK, mlflow_run_id, auroc, auprc, utility, threshold,
              model_type VARCHAR(20), status, created_at)
  -- model_type ∈ {xgboost, lightgbm, random_forest}
  -- status ∈ {production, staging, archived} — mirror MLflow alias
drift_report(id, ref_period_start/end, target_period_start/end,
             drift_share, triggered_retrain, report_json JSONB, created_at)
```

**Idempotent inserts:** consumer dùng `INSERT … ON CONFLICT (patient_id, hour) DO UPDATE` cho `vital` và `prediction` — Kafka không guarantee exactly-once, message duplicate vẫn ổn.

## Kafka topics

* `patient-vitals`: producer → backend consumer (raw vitals)
* Message: `{patient_id, hour, vitals: {...}, demographics: {...}, sepsis_label}`

## GitHub workflow

```bash
# .gitignore phải có: venv/, ml/data/, ml/mlruns/, .env, *.pkl, __pycache__/, node_modules/, dist/
# Notebook clear output trước khi commit:
jupyter nbconvert --clear-output --inplace ml/notebooks/*.ipynb
```

**Branches:** `main` (production-ready) + `dev` (work-in-progress). Mỗi feature 1 branch `feat/...` → PR vào `dev`.

**GitHub Actions** (`.github/workflows/ci.yml`):

* Lint Python (`ruff`) + format check (`black --check`)
* Lint TS (`eslint`)
* Run pytest cho `ml/src/` + `backend/`
* Build Docker images (chỉ trên push `main`)

## AWS deploy plan (free tier)

| Service                    | Tier                               | Dùng cho                                        |
| -------------------------- | ---------------------------------- | ------------------------------------------------ |
| EC2 t3.micro (1GB RAM)     | 750h/tháng free                   | Chạy Docker Compose: backend + frontend + Kafka |
| RDS PostgreSQL db.t3.micro | 750h/tháng free (12 tháng đầu) | Database                                         |
| S3 (5GB)                   | Free                               | MLflow artifacts + model files                   |
| Elastic IP                 | Free khi attach EC2                | IP cố định cho domain                         |

**Lưu ý constraint t3.micro 1GB RAM:**

* Kafka đã set `KAFKA_HEAP_OPTS=-Xmx512m -Xms256m` trong `compose.prod.yml`. Nếu OOM, hạ xuống `-Xmx256m`.
* Backend FastAPI: 1 worker, không multi-process
* **KHÔNG build image trên EC2** (xgboost compile sẽ OOM) — pull image đã build sẵn từ GHCR
* MLflow container dùng SQLite local + volume, hoặc nâng cấp lên S3 backend nếu muốn HA

**Deploy steps (image đã có sẵn ở GHCR từ CI):**

```bash
# 1. SSH vào EC2
ssh -i key.pem ubuntu@<ec2-ip>

# 2. Install docker + compose
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin

# 3. Copy compose + .env.prod lên EC2 (scp hoặc clone repo nhưng chỉ cần infra/)
scp -i key.pem infra/docker-compose.prod.yml infra/.env.prod ubuntu@<ec2-ip>:~/

# 4. Pull image từ GHCR (public, không cần login) + override image tag trỏ GHCR
#    Sửa compose.prod để dùng `image: ghcr.io/minhnguyen1007/sepsis-backend:latest`
#    thay vì `build:` block.

# 5. Run
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 6. Bootstrap MLflow alias (1 lần): chạy train từ máy dev push lên EC2 MLflow,
#    hoặc copy mlflow.db từ local lên EC2 volume.

# 7. RDS: thay DATABASE_URL trong .env.prod trỏ RDS endpoint, bỏ service postgres khỏi compose.
```

## Code conventions

* Python: `from __future__ import annotations`, type hints, docstring ngắn giải thích WHY
* TS/React: functional components + hooks, props có type rõ ràng
* File < 300 dòng, function < 50 dòng
* Notebook: chỉ import + visualize, **logic nằm ở `src/*.py`**
* Commit: `feat(scope): ...`, `fix(scope): ...`

## DO NOT

* ❌ Airflow/Kubeflow (over-engineer)
* ❌ Hardcode paths/credentials → dùng `.env`
* ❌ Commit `data/`, `mlruns/`, `venv/`, `.env`, `*.pkl`
* ❌ Sync SQLAlchemy trong async endpoint
* ❌ Viết logic chính trong `.ipynb` (khó test, khó gọi từ scheduler)
* ❌ Commit notebook có output nặng → `jupyter nbconvert --clear-output` trước khi commit
* ❌ Dùng MLflow Stage (deprecated) → dùng **alias** `production`
* ❌ Load XGBoost model trong request handler (chậm 200-500ms) → cache in-memory ở `loader.py`
* ❌ Block FastAPI event loop với ML heavy work (drift/train) → scheduler dùng `asyncio.to_thread(subprocess.run)` chạy `python -m ml.src.<job>`
* ❌ Deep learning (boosting/ensemble đủ và tốt hơn cho tabular data)
* ❌ Load model bằng `mlflow.xgboost.load_model()` → dùng `mlflow.pyfunc.load_model()` (model-agnostic)
* ❌ Đưa data chưa validate vào retrain → consumer validate + mark `is_validated`, retrain filter `WHERE is_validated=TRUE`
