# Backend - CLAUDE.md

> Đọc `../CLAUDE.md` trước. File này chỉ chi tiết riêng cho backend.

## Trách nhiệm

1. Kafka consumer (topic `patient-vitals`) → predict → save DB → push WebSocket
2. REST API cho frontend (patients, predictions, models, drift reports)
3. APScheduler: drift check daily, retrain weekly

## Tech

FastAPI + SQLAlchemy 2.0 async + asyncpg + kafka-python + MLflow + APScheduler + Evidently

## Cấu trúc

```
backend/app/
├── main.py              # FastAPI entry, lifespan start consumer + scheduler
├── config.py            # Pydantic Settings từ .env
├── api/
│   ├── patients.py      # GET /patients, /patients/{id}, /patients/{id}/vitals
│   ├── predictions.py   # GET /predictions/{patient_id}, /predictions/alerts
│   ├── models.py        # GET /models (production info, history)
│   ├── drift.py         # GET /drift/reports
│   └── websocket.py     # WS /ws/predictions
├── ml/
│   ├── loader.py        # Load + cache MLflow Production model
│   ├── predictor.py     # predict_one(vitals, demographics) -> risk
│   └── features.py      # Feature engineering (giống ml/preprocess.py)
├── streaming/
│   └── consumer.py      # KafkaConsumer chạy thread riêng (kafka-python sync)
├── db/
│   ├── base.py          # Async engine, session
│   ├── models.py        # SQLAlchemy ORM
│   └── crud.py
├── scheduler/
│   └── jobs.py          # drift_check_job, weekly_retrain_job
└── alembic/             # Migrations
```

## Key flow

**Consumer:** thread riêng (sync kafka-python ổn định hơn aiokafka) → poll message → predict → `asyncio.run(save + broadcast)`

**Model loading:** Load 1 lần ở startup, cache in-memory. `reload_model()` gọi sau khi retrain promote.

**WebSocket:** Set in-memory `_active_connections`. `broadcast_prediction()` push tới tất cả clients sau mỗi prediction.

**Scheduler jobs:**

- `drift_check_job` (daily 2AM): subprocess gọi `ml/src/drift_detect.py` → parse JSON → save `drift_report` → trigger retrain nếu drift_share > 0.3
- `weekly_retrain_job` (Sun 3AM): subprocess gọi `ml/src/retrain.py` → reload model nếu thành công

## Config (`.env`)

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/monitoring
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_VITALS=patient-vitals
MLFLOW_TRACKING_URI=http://localhost:5000
MODEL_NAME=sepsis-predictor
MODEL_STAGE=Production
FRONTEND_ORIGIN=http://localhost:5173
DRIFT_FEATURES_THRESHOLD=0.3
```

## DB models (key fields)

```python
Patient(id, age, gender, unit1, unit2, hosp_adm_time)
Vital(id, patient_id, hour, hr, o2sat, temp, sbp, map, dbp, resp, etco2,
      lab_values JSON, sepsis_label, created_at)
Prediction(id, patient_id, hour, sepsis_risk, model_version, predicted_at)
ModelVersion(version, mlflow_run_id, auroc, auprc, status)
DriftReport(id, ref_period_*, target_period_*, drift_share, triggered_retrain)
```

Index: `(patient_id, hour)` trên `vital` và `prediction`.

## API endpoints

| Method | Path                                 | Mô tả                                                   |
| ------ | ------------------------------------ | ------------------------------------------------------- |
| GET    | `/api/patients`                      | List patients active 24h qua, sort by current_risk DESC |
| GET    | `/api/patients/{id}/vitals?limit=24` | Vitals history                                          |
| GET    | `/api/predictions/{patient_id}`      | Predictions theo patient                                |
| GET    | `/api/predictions/alerts`            | Patients risk > 0.7                                     |
| GET    | `/api/models`                        | Production model info                                   |
| GET    | `/api/drift/reports?limit=10`        | Drift reports recent                                    |
| WS     | `/ws/predictions`                    | Real-time stream                                        |

## Test priorities

- `predict_one()`: output trong [0, 1], handle NaN
- `_process_message()`: parse đúng Kafka schema
- `save_vital_and_prediction()`: idempotent (unique patient_id + hour)
- Drift threshold logic

## Common issues

- **Kafka không nhận message:** check `auto_offset_reset="earliest"`, unique `group_id`
- **WebSocket disconnect ngay:** uvicorn cần `--ws-ping-interval 25`
- **Async/sync mix:** dùng `asyncio.run()` trong thread consumer để gọi async functions
- **Postgres pool exhausted:** `pool_size=10, max_overflow=20`

## DO NOT

- ❌ Load model trong request handler
- ❌ Sync SQLAlchemy session trong async endpoint
- ❌ Log patient PII ở level INFO
- ❌ Catch `Exception` chung chung
