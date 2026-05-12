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
| T6    | 🚧 In progress | `drift_detect.py` (Evidently), `retrain.py` (pull DB + train + promote alias), APScheduler jobs. Hook lifespan + test.  |
| T7    | ⬜ Todo    | Dockerize backend/frontend, GitHub Actions CI/CD, AWS deploy.                                                              |
| CN    | ⬜ Todo    | Polish UI, viết báo cáo, record demo.                                                                                     |

**Baseline AUROC: 0.838, AUPRC: 0.110, Utility: 0.825 @ thr=0.70** (full ~40k patient, MLflow registered alias `production`, version 1).

## Kiến trúc

```
Producer (.psv) → Kafka → Backend (FastAPI + Consumer)
                                 ├─ Predict (XGBoost từ MLflow Registry)
                                 ├─ Save Postgres
                                 └─ WebSocket → Frontend (React)

Scheduler (APScheduler trong backend):
  - Daily 2AM: drift check (Evidently AI)
  - Weekly Sun 3AM: retrain
  - Auto-promote nếu AUROC mới > production
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
│       ├── streaming/consumer.py # Kafka consumer thread
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
│   └── docker-compose.yml        # Postgres 15 + Kafka 3.7 (apache/kafka)
├── venv/                         # 1 venv chung (gitignore)
├── requirements.txt              # ML + Backend + Streaming deps
├── alembic.ini
├── .env.example
└── README.md
```

## Tech stack

* **Streaming:** `apache/kafka:3.7.0` (KRaft mode, no Zookeeper) + `kafka-python`
* **Backend:** FastAPI 0.110+ + SQLAlchemy 2.0 async + asyncpg + Pydantic 2
* **Frontend:** React 18 + Vite 5 + TypeScript + TailwindCSS 3 + Chart.js 4 (`react-chartjs-2`) + TanStack Query 5 + React Router 6
* **ML:** XGBoost 2 + scikit-learn 1.4 + MLflow 2.22 (alias-based registry, **không dùng stage** vì deprecated)
* **Drift:** Evidently AI 0.4+
* **Scheduler:** APScheduler 3 async (chạy trong backend lifespan, không tách service)
* **DB:** PostgreSQL 15-alpine
* **Deploy:** Docker Compose → AWS EC2 t3.micro + RDS free tier

## Key decisions

**XGBoost thay vì DL:** tabular + imbalance → boosting thắng. Train CPU 5-10 phút trên laptop FX506HC. Model ~10MB, inference <10ms.

**Train trên laptop, không cần Kaggle:** Laptop ASUS TUF FX506HC (RTX 3050 4GB, 24GB RAM) dư sức cho XGBoost CPU 5-10 phút. Kaggle (P100/T4x2) chỉ cần khi muốn thử LSTM/Transformer làm baseline so sánh trong báo cáo (optional). Lý do chọn laptop: (1) tiện retrain auto qua APScheduler local, (2) không phụ thuộc Kaggle session timeout, (3) cùng môi trường venv với code production.

**Kafka thay vì Redis:** đề yêu cầu "Streaming" → industry standard. KRaft mode không cần Zookeeper, nhẹ hơn cho free tier.

**1 venv chung:** scope đồ án nhỏ, đỡ phức tạp setup. Tất cả deps (backend + ml + streaming) trong `requirements.txt`. Frontend dùng npm riêng.

**Drift + Schedule retrain:** Drift bắt concept drift sớm, schedule là safety net. Cả 2 log MLflow, chỉ promote khi AUROC tốt hơn.

**Notebook + Script kết hợp:** notebook cho EDA + train baseline lần đầu (dễ debug, visualize, làm báo cáo). Script `src/*.py` chứa logic có thể tái sử dụng + chạy headless cho retrain tự động.

**MLflow alias thay vì stage:** MLflow 2.9+ đã deprecate Stage (None/Staging/Production/Archived) — sẽ remove ở 3.x. Dùng alias `production` (URI `models:/sepsis-predictor@production`). Lợi thế: nhiều alias trên 1 version (canary/champion/challenger), pointer riêng không phá history.

## ML workflow

```
ml/
├── src/                          # Logic chính - import được từ cả notebook + scheduler
│   ├── preprocess.py             # load_psv_files(), feature_engineering(), split_train_val()
│   ├── train.py                  # train_model(train_df, val_df, params) -> (model, metrics)
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
# ml/src/train.py
def train_model(train_df, val_df, params: dict) -> tuple[xgb.Booster, dict]:
    """Train XGBoost + log MLflow. Return (model, metrics)."""
    ...

if __name__ == "__main__":  # Cho phép: python ml/src/train.py
    train_df, val_df = load_and_split()
    train_model(train_df, val_df, DEFAULT_PARAMS)
```

```python
# ml/notebooks/02_train_baseline.ipynb
from ml.src.train import train_model
from ml.src.preprocess import load_and_split

train_df, val_df = load_and_split()
model, metrics = train_model(train_df, val_df, my_params)
# Plot results, thử params khác...
```

## Online retrain workflow (yêu cầu giảng viên)

Đề bài yêu cầu "data online để train lại model". Cách triển khai:

```
Producer giả lập "data online" → Kafka → Backend consumer → Lưu vital + sepsis_label vào Postgres
                                                                    │
                                                                    ▼
                                            Sau N giờ stream, DB có data mới
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
                            1. Pull data mới từ Postgres + data gốc
                            2. Train XGBoost với MLflow tracking
                            3. So sánh AUROC mới vs production hiện tại
                            4. AUROC mới tốt hơn → set alias `production` trỏ version mới
                            5. Scheduler gọi loader.reload_model() → backend swap cache (không cần restart)
```

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

# 7. Train baseline + register vào MLflow
#    - Cách A: chạy notebook ml/notebooks/02_train_baseline.ipynb,
#              uncomment cell cuối với register_model=True.
#    - Cách B: headless:
python -m ml.src.train --register

#    Mở http://localhost:5000 → Models → sepsis-predictor → Version 1 →
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
| **T6** | 🚧 In progress | Evidently drift detect, retrain orchestrator, APScheduler jobs, manual trigger endpoints                                    |
| **T7** | ⬜ Todo         | Dockerize, GitHub Actions, deploy AWS EC2 + RDS                                                                              |
| **CN** | ⬜ Todo         | Polish UI, viết báo cáo, record demo video                                                                                  |

## Database schema

```
patient(id, age, gender, unit1, unit2, hosp_adm_time, created_at)
vital(id, patient_id FK, hour, hr, o2sat, temp, sbp, map, dbp, resp, etco2,
      lab_values JSONB, sepsis_label, created_at)
  UNIQUE(patient_id, hour), INDEX(patient_id, hour)
prediction(id, patient_id FK, hour, sepsis_risk, model_version, predicted_at)
  UNIQUE(patient_id, hour), INDEX(patient_id, hour)
model_version(version PK, mlflow_run_id, auroc, auprc, utility, threshold, status, created_at)
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

* Kafka cần config `KAFKA_HEAP_OPTS=-Xmx256m -Xms256m` (mặc định 1GB sẽ OOM)
* Backend FastAPI: 1 worker, không multi-process
* Tách MLflow server ra ngoài (chạy local máy Hứa) hoặc dùng SQLite + S3 backend cho MLflow

**Deploy steps:**

```bash
# 1. Build và push images lên Docker Hub
docker build -t huu/monitoring-backend:v1 -f infra/Dockerfile.backend .
docker push huu/monitoring-backend:v1
# (tương tự frontend)

# 2. SSH vào EC2
ssh -i key.pem ubuntu@<ec2-ip>

# 3. Pull images + chạy docker-compose
docker-compose -f docker-compose.prod.yml up -d

# 4. Setup RDS endpoint trong .env
# 5. Run migrations: docker exec backend alembic upgrade head
```

## Code conventions

* Python: `from __future__ import annotations`, type hints, docstring ngắn giải thích WHY
* TS/React: functional components + hooks, props có type rõ ràng
* File < 300 dòng, function < 50 dòng
* Notebook: chỉ import + visualize, **logic nằm ở `src/*.py`**
* Commit: `feat(scope): ...`, `fix(scope): ...`

## DO NOT

* ❌ Airflow/Kubeflow (over-engineer)
* ❌ Deep learning (XGBoost đủ và tốt hơn)
* ❌ Hardcode paths/credentials → dùng `.env`
* ❌ Commit `data/`, `mlruns/`, `venv/`, `.env`, `*.pkl`
* ❌ Sync SQLAlchemy trong async endpoint
* ❌ Viết logic chính trong `.ipynb` (khó test, khó gọi từ scheduler)
* ❌ Commit notebook có output nặng → `jupyter nbconvert --clear-output` trước khi commit
* ❌ Dùng MLflow Stage (deprecated) → dùng **alias** `production`
* ❌ Load XGBoost model trong request handler (chậm 200-500ms) → cache in-memory ở `loader.py`
* ❌ Block FastAPI event loop với ML heavy work (drift/train) → scheduler dùng `asyncio.create_subprocess_exec` chạy `python -m ml.src.<job>`
