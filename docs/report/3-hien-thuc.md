# 3. Hiện thực

Mục này trình bày cách hệ thống được cài đặt trên thực tế: công nghệ đã lựa chọn kèm lý do, dữ liệu thực dùng để huấn luyện và đánh giá, quy trình triển khai end-to-end trên môi trường LocalStack, kết quả đạt được của từng module, và các đánh giá tổng hợp.

## 3.1. Công nghệ sử dụng

Bảng dưới đây liệt kê công nghệ được lựa chọn cho mỗi tầng của hệ thống. Tiêu chí lựa chọn bao gồm: (i) phù hợp với ràng buộc ngân sách bằng không, (ii) có cộng đồng mã nguồn mở rộng lớn, (iii) có thể triển khai lại trên hạ tầng đám mây thật mà không phải viết lại code.

### 3.1.1. Tầng thu thập và truyền dữ liệu

| Thành phần            | Công nghệ                      | Lý do lựa chọn                                                                                                                                                       |
| --------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Giả lập luồng dữ liệu | LocalStack 3.x (Docker)        | Giả lập AWS Kinesis, S3, DynamoDB trên máy cá nhân. Chi phí bằng không. API tương thích AWS SDK chuẩn nên chuyển sang AWS thật không cần đổi code.                   |
| Hàng đợi streaming    | AWS Kinesis Data Streams       | Hỗ trợ throughput cao, giữ thứ tự theo khóa phân mảnh (`patient_id`), tích hợp trực tiếp với consumer.                                                               |
| Consumer xử lý        | Python 3.11 standalone service | Ban đầu thiết kế Lambda nhưng chuyển sang dịch vụ Python độc lập để tránh phức tạp LocalStack Lambda trên Windows (cần docker-in-docker). Cùng output, dễ debug hơn. |
| Bộ mô phỏng           | Python 3.11 + `boto3`          | Đọc file PhysioNet `.psv` và phát lại vào Kinesis với tốc độ cấu hình được (mặc định 1 giây = 1 giờ dữ liệu).                                                        |

### 3.1.2. Tầng lưu trữ

| Thành phần                 | Công nghệ                                  | Lý do lựa chọn                                                                                                                                       |
| -------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Kho feature thời gian thực | DynamoDB Local                             | Độ trễ đọc dưới 10ms, TTL tự động xóa dữ liệu cũ, phù hợp tra cứu nhanh theo `patient_id`.                                                           |
| Kho dữ liệu lịch sử        | MinIO (S3-compatible) + Parquet/JSON       | Training split lưu dưới dạng Parquet (nén cột, ~10 lần so với CSV). Raw streaming từ consumer được flush dưới dạng JSON batch theo giờ để dễ replay. |
| Kho state real-time        | Redis 7                                    | Lưu proba history (hysteresis decision), patient metadata, raw vitals hourly cho API charting. Capped list FIFO 48–168h, O(1) append.                |
| Cơ sở dữ liệu ứng dụng     | PostgreSQL 15 + SQLAlchemy async (asyncpg) | Lưu người dùng (hashed passwords), cảnh báo đã xác nhận. ACID bảo đảm cho nghiệp vụ cảnh báo y tế.                                                   |
| Kho artifact ML            | MinIO                                      | Backend cho MLflow artifact store, tương thích giao thức S3.                                                                                         |

### 3.1.3. Tầng học máy

| Thành phần          | Công nghệ                                               | Lý do lựa chọn                                                                                                        |
| ------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Xử lý dữ liệu       | Pandas 2.x + PyArrow                                    | Pandas quen thuộc, PyArrow hỗ trợ Parquet hiệu suất cao và kiểu dữ liệu nullable chính xác.                           |
| Mô hình production  | LightGBM 4.x                                            | Nhanh, ít hyperparameter, xử lý NaN gốc không cần impute. Top 10 PhysioNet Challenge 2019 đều dùng gradient boosting. |
| Thử nghiệm bổ sung  | CatBoost (Kaggle GPU), Ensemble (Logistic meta-learner) | Đã thử nhưng không vượt LightGBM v4 trên Utility Score. Giữ trong repo để minh họa.                                   |
| Theo dõi thí nghiệm | MLflow 2.x (self-host)                                  | Mã nguồn mở, hỗ trợ tracking + model registry. Chạy trên Docker độc lập.                                              |
| Phục vụ inference   | FastAPI 0.115+                                          | Tốc độ gần Node.js, sinh OpenAPI tự động, type-hint tự nhiên với Pydantic.                                            |

### 3.1.4. Tầng giao diện và vận hành

| Thành phần         | Công nghệ                                  | Lý do lựa chọn                                                                                         |
| ------------------ | ------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Framework frontend | React 19 + Vite 8 + TypeScript 6 (strict)  | Ecosystem đa dạng, Vite build nhanh, TypeScript giảm lỗi runtime.                                      |
| Thư viện UI        | TailwindCSS 4 (`@tailwindcss/vite` plugin) | Utility-first, không cần config file (v4 engine mới), dễ tùy biến.                                     |
| Biểu đồ            | Recharts                                   | API khai báo, tích hợp tốt với React, hỗ trợ dual Y-axis.                                              |
| State management   | Zustand + TanStack Query                   | Zustand cho UI state (auth, WS events), TanStack Query cho server state + cache + polling.             |
| Realtime           | WebSocket native                           | Không phụ thuộc dịch vụ ngoài, phía server dùng `websockets` của Python. Auto-reconnect 2s.            |
| Giám sát hạ tầng   | Prometheus + Grafana                       | Tiêu chuẩn trong ngành, scrape metric từ FastAPI `/metrics` (via `prometheus-fastapi-instrumentator`). |
| Authentication     | JWT (python-jose) + bcrypt (passlib)       | Stateless token-based auth, bcrypt cho password hashing. Token persist trong localStorage.             |
| CI/CD              | GitHub Actions                             | Miễn phí cho repo công khai, chạy song song test nhiều phiên bản Python.                               |

### 3.1.5. Lý do né một số lựa chọn khác

- **SageMaker:** học curve dốc, tốn phí ngay cả cho notebook. MLflow + FastAPI đủ đáp ứng nhu cầu đồ án và dễ debug hơn.
- **Amazon MSK (Kafka quản lý):** tối thiểu khoảng 80 USD/tháng. Kinesis trên LocalStack đáp ứng cùng ngữ nghĩa phân vùng theo khóa.
- **Feast (feature store):** phức tạp, cần Redis + offline store riêng. Với quy mô một bảng feature, DynamoDB Local + Parquet là đủ.
- **Kubernetes:** overkill cho demo đồ án. `docker-compose` đủ để khởi động 10 container.
- **Alembic:** migration history phức tạp cho đồ án sinh viên. `create_tables()` idempotent đủ dùng.

## 3.2. Dữ liệu

### 3.2.1. Nguồn và mô tả

Dữ liệu chính cho huấn luyện và đánh giá là bộ dữ liệu **PhysioNet Computing in Cardiology Challenge 2019** (Reyna và cộng sự, 2020), được cấp phép theo Open Data Commons Attribution License v1.0 và truy cập tại địa chỉ https://physionet.org/content/challenge-2019. Bộ dữ liệu gồm hồ sơ sinh hiệu theo giờ của bệnh nhân ICU từ hai bệnh viện (Beth Israel Deaconess Medical Center và Emory University Hospital), đã được khử định danh theo chuẩn HIPAA Safe Harbor.

Quy mô và đặc điểm:

- **Tổng số bệnh nhân:** 40.336 hồ sơ (setA: 20.336 + setB: 20.000).
- **Định dạng:** một file `.psv` (pipe-separated values) cho mỗi bệnh nhân.
- **Tần suất:** một dòng mỗi giờ, từ lúc nhập ICU đến lúc xuất hoặc kết thúc theo dõi.
- **40 cột đặc trưng**: 8 sinh hiệu (HR, O2Sat, Temp, SBP, MAP, DBP, Resp, EtCO2), 26 kết quả xét nghiệm (BUN, Creatinine, Lactate, Platelets, WBC, v.v.), 5 thông tin nhân khẩu và ngữ cảnh ICU (Age, Gender, Unit1, Unit2, HospAdmTime, ICULOS), và cột nhãn `SepsisLabel`.
- **Định nghĩa nhãn:** `SepsisLabel = 1` trong cửa sổ từ `t_sepsis − 6h` đến `t_sepsis + 3h`, trong đó `t_sepsis` là thời điểm nghi ngờ sepsis đầu tiên theo tiêu chí Sepsis-3.
- **Tỷ lệ mất cân bằng:** khoảng 1,8% bệnh nhân phát triển sepsis. Ở cấp độ từng giờ, tỷ lệ dương tính ~2-3%.

### 3.2.2. Phân chia tập dữ liệu

Dữ liệu được chia theo **patient ID** (không theo hàng thời gian), tỷ lệ 70/15/15, seed cố định (`SEED=42`).

| Tập        | Số bệnh nhân | Số giờ     | Tỷ lệ nhãn dương |
| ---------- | ------------ | ---------- | ---------------- |
| Train      | ~28.200      | ~1.080.000 | ~2,2%            |
| Validation | ~6.050       | ~230.000   | ~2,2%            |
| Test       | ~6.050       | ~230.000   | ~2,2%            |

### 3.2.3. Kiểm tra chất lượng dữ liệu

Tại tầng thu nhận, mỗi record được xác thực qua `consumer/validator.py` với khoảng sinh lý hợp lệ: `HR ∈ [0, 300]`, `O2Sat ∈ [0, 100]`, `Temp ∈ [25, 45]`, `SBP ∈ [0, 300]`, `MAP ∈ [0, 300]`, `Resp ∈ [0, 100]`. Giá trị ngoài dải được gán `NaN`. Tỷ lệ record bị đánh dấu invalid nhưng không ngắt luồng.

### 3.2.4. Feature Engineering

Nhóm xây dựng **131 features** theo stateful per-patient rolling windows (module `data-pipeline/consumer/feature_engineer.py`):

- 120 rolling stats: 8 sinh hiệu × 3 cửa sổ (6h/12h/24h) × 5 thống kê (mean/std/min/max/slope)
- 8 missing indicators (binary): cho mỗi sinh hiệu
- 3 clinical features: qSOFA score (0-2), SIRS count (0-4), ICULOS hours

Batch feature engineering (`ml/src/build_features.py`) **import trực tiếp** `FeatureEngineer` class từ `data-pipeline/consumer/` để đảm bảo feature parity 100% giữa training và serving — tránh training-serving skew.

## 3.3. Triển khai và vận hành

### 3.3.1. Cấu trúc mã nguồn

```
remote-patient-monitoring/
├── docker-compose.yml          # 10 services (core + monitoring + app profiles)
├── .github/workflows/{ci.yml, integration.yml}
├── data-pipeline/              (role A: simulator, consumer, feature store)
├── ml/                         (role B: train, evaluate, MLflow client)
├── mlops/                      (role C: MLflow, Prometheus, Grafana)
├── app/
│   ├── backend/                (role D: FastAPI + WebSocket + Auth)
│   └── frontend/               (role D: React + Vite)
├── infra/{localstack, terraform}/
├── scripts/{dev-up.ps1, dev-down.ps1}
└── docs/{architecture.md, uml/, report/}
```

### 3.3.2. Khởi động môi trường phát triển

Toàn bộ hệ thống được đóng gói trong `docker-compose.yml` duy nhất với 10 services chia 3 profile:

1. **Core (luôn chạy):** localstack, postgres, minio, minio-init, redis, mlflow
2. **Monitoring (profile `monitoring`):** prometheus, grafana
3. **App (profile `app`):** backend, frontend

Quy trình khởi động nhanh:

```powershell
# Khởi động tất cả service
docker-compose up -d

# Hoặc dùng dev script (spawn backend + frontend + consumer)
.\scripts\dev-up.ps1

# Bắt đầu mô phỏng stream 10 bệnh nhân
python data-pipeline/simulator/run.py --data-dir data/raw/training_setA --patients 10 --speed 1s
```

Sau khoảng 3 phút, dashboard tại `http://localhost:5173` hiển thị bệnh nhân với sinh hiệu và xác suất sepsis cập nhật mỗi giây.

### 3.3.3. Luồng xử lý end-to-end

1. **Simulator** đọc file `.psv`, lấy hàng tiếp theo, đóng gói JSON và gửi `PutRecord` vào Kinesis stream `vital-signs-stream` với partition key là `patient_id`.
2. **Consumer** (dịch vụ Python standalone, poll loop) thực hiện:
   - Xác thực schema qua `validator.py`.
   - Tính 131 features theo cửa sổ trượt bằng `FeatureEngineer` class.
   - Ghi feature mới về DynamoDB (`patient_latest_features`).
   - Buffer raw record (100 bản ghi) và flush lên S3 dưới dạng JSON batch (đường dẫn phân mảnh theo `year/month/day/HHMMSS.json`).
   - **Lưu raw vitals vào Redis** (`patient:{pid}:vitals`, capped 168h) cho API charting.
   - POST `/predict` tới FastAPI backend với 134 features (131 + 3 demographics).
3. **FastAPI backend** nạp model production từ MLflow registry lúc startup, dự đoán xác suất, ghi proba vào Redis history, phát broadcast qua WebSocket, và **persist alarm vào PostgreSQL**.
4. Nếu xác suất vượt ngưỡng và thỏa quy tắc hysteresis (6 giờ liên tiếp vượt ngưỡng 0.05), backend ghi alert vào bảng `alerts` (PostgreSQL) và đẩy WebSocket event.
5. **React frontend** nhận sự kiện WebSocket cho live updates; đồng thời polling `GET /patients` mỗi 5s và `GET /proba_history` + `GET /vitals` mỗi 10s (TanStack Query) để hydrate data persist qua page refresh.
6. Bác sĩ nhấn "Xác nhận" (acknowledge), hành động ghi vào `alerts.acknowledged` qua endpoint `PUT /alerts/{id}/acknowledge` (yêu cầu JWT).

### 3.3.4. CI/CD pipeline

Hệ thống có bốn workflow GitHub Actions:

- **ci.yml** — chạy trên mỗi push và pull request: `ruff check`, `mypy`, `pytest tests/unit`, `npm run lint`, `npm run test`, upload coverage.
- **integration.yml** — chạy trên pull request tới `main`: dùng docker-compose khởi LocalStack + PostgreSQL + MinIO, chạy integration tests.
- **cd.yml** — chạy trên mỗi merge vào `main`: build hai Docker image (`backend`, `frontend`) bằng Buildx matrix, push lên GitHub Container Registry (`ghcr.io/<owner>/<repo>/<name>`) với hai tag `:<sha7>` và `:latest`, cache layer qua `type=gha`. Job `smoke-compose` kế tiếp khởi các service core để xác nhận image mới không phá vỡ compose.
- **drift.yml** — chạy định kỳ (cron hàng tuần) hoặc bấm chạy thủ công: tải hai parquet (reference + current) từ S3/MinIO qua secret, chạy `mlops/drift/check.py`, upload báo cáo HTML làm artifact 30 ngày, bắn Slack khi share drift vượt ngưỡng (`SLACK_WEBHOOK_URL` secret).

## 3.4. Kết quả từng module

### 3.4.1. Module A — Data Pipeline

- **Simulator:** phát lại đồng thời nhiều bệnh nhân với tốc độ cấu hình từ 1 ms đến 60 giây cho mỗi giờ dữ liệu.
- **Consumer:** xử lý record → validate → compute 131 features → write DynamoDB + S3 + Redis → POST /predict. Opt-in predict qua `BACKEND_PREDICT_ENABLED` flag.
- **Feature store:** bảng `patient_latest_features` (DynamoDB) cho realtime lookup. Raw JSON batch trên S3 cho replay/debug; training dataset lưu Parquet (do `ml/src/preprocess.py` xuất ra).

### 3.4.2. Module B — ML

Mô hình được huấn luyện và đăng ký trong MLflow (`sepsis-lgbm-prod`, locked tại version 4):

| Mô hình                      | Test AUROC | Test AUPRC | Sens @ Spec=0.95   | Test Utility Score | Ghi chú                         |
| ---------------------------- | ---------- | ---------- | ------------------ | ------------------ | ------------------------------- |
| **LightGBM v4** (production) | **0.8093** | **0.0981** | 0.3606 (thr=0.433) | **-0.2207**        | scale_pos_weight=10, k=6        |
| LightGBM v5 (relabel)        | 0.8093     | —          | —                  | -0.2626            | relabel [-6h,+3h] + warmup grid |
| CatBoost (Kaggle GPU)        | 0.8081     | —          | —                  | -0.2725            | similar performance             |
| Ensemble (LR meta)           | **0.8112** | —          | —                  | -0.2400            | AUROC best nhưng util thua v4   |

**Quyết định:** Lock v4 làm production vì 3 thử nghiệm bổ sung hội tụ quanh util -0.22…-0.27, không vượt v4. Root cause: model alert trung bình 53h trước onset (ngoài reward window [-12h,+3h]).

**Utility Score âm:** Khác với kỳ vọng ban đầu (dương ~0.39), utility thực tế -0.22 do false positive cao (4385 FP vs 447 TP). Đây là hạn chế lớn nhất — feature set hiện tại không phân biệt rõ pre-sepsis trong reward window. Top PhysioNet ~0.43 cần feature engineering chuyên sâu ngoài phạm vi đồ án.

**Top 3 SHAP features:** `iculos_hours`, `HospAdmTime`, `max_hr_6h`.

### 3.4.3. Module C — MLOps

- **MLflow tracking:** ghi nhận nhiều run thử nghiệm (LightGBM variants, CatBoost, ensemble). Model registry quản lý 5 phiên bản, v4 pin làm production.
- **Prometheus:** cấu hình scrape FastAPI backend `/metrics` + MLflow. `prometheus-fastapi-instrumentator` tự động expose HTTP request metrics.
- **Grafana:** dashboard provision tự động 7 panels: request rate, p95 latency, prediction count, alert rate, active patients, error rate, request duration heatmap. Auto-refresh 10s.
- **Drift monitoring:** script `mlops/drift/check.py` dùng Evidently AI so sánh hai parquet (mặc định `train` làm reference, `val` làm current) trên 8 cột sinh hiệu, ghi báo cáo HTML vào `mlops/drift/reports/drift_<timestamp>.html`. Chạy ad-hoc hoặc qua workflow `drift.yml` (cron hàng tuần + `workflow_dispatch`). Kết quả trên split hiện tại: `dataset_drift=False`, 0/8 cột bị drift — xác nhận train/val cùng phân bố.
- **Slack alerting cho drift:** script đọc biến môi trường `SLACK_WEBHOOK_URL`; khi `dataset_drift=True` hoặc share vượt ngưỡng (`--share-threshold`, mặc định 0.3), gửi POST tới Incoming Webhook kèm tên reference/current và tên file báo cáo.
- **CI/CD pipeline:**
  - `ci.yml` (push + PR): ruff + pytest unit (26 test, tất cả pass) + frontend lint/test.
  - `cd.yml` (merge `main`): build đồng thời hai Docker image (backend + frontend) qua Buildx matrix, push lên `ghcr.io` với tag `<sha7>` và `latest`, cache layer; job `smoke-compose` khởi core services để xác nhận image mới không phá vỡ stack.
  - `drift.yml` (cron tuần): pull parquet từ S3/MinIO, chạy drift check, upload artifact HTML, bắn Slack nếu vượt ngưỡng.

### 3.4.4. Module D — Full-stack

#### Backend (FastAPI 0.115+, version 0.3.0)

- **10+ endpoints REST + 1 WebSocket:**
  - `GET /health` — model info
  - `POST /predict` — inference + Redis proba history + PostgreSQL alert persist
  - `WS /ws/alerts` — broadcast alarm events
  - `GET /patients` — list active patients from Redis
  - `GET /patients/{id}/vitals` — hourly vitals chart data
  - `GET /patients/{id}/proba_history` — proba timeline chart data
  - `GET /metrics` — Prometheus metrics
  - `POST /auth/login` — JWT token (bcrypt verify)
  - `POST /auth/register` — admin-only user creation
  - `GET /auth/me` — current user profile
  - `GET /alerts` — persisted alerts (filter by patient/acknowledged)
  - `PUT /alerts/{id}/acknowledge` — acknowledge alert (requires JWT)
- **Database:** SQLAlchemy async + asyncpg. 2 ORM models: `User` (role-based: admin/doctor/viewer), `Alert` (acknowledge workflow). `create_tables()` idempotent on startup.
- **Auth:** bcrypt password hashing, JWT access tokens (configurable expiry). Auto-seed admin user (admin/admin123) on first startup.
- **Decision engine:** Redis-backed hysteresis — append proba, check streak tail, warmup gate.

#### Frontend (React 19 + Vite 8 + TypeScript 6)

- **4 trang chính:**
  1. **Login** — dark glassmorphism design, gradient background, loading animation, error handling
  2. **Patient List** — server-backed via TanStack Query polling `GET /patients` mỗi 5s (persist qua refresh) + WS events overlay. Bảng sorted theo proba descending, ALARM pulse animation.
  3. **Patient Detail** — 2 server-backed charts: sepsis proba timeline (`/proba_history`) + multi-line vitals (HR, Resp, MAP trên Y trái, SpO2 trên Y phải từ `/vitals`). Auto-refresh 10s.
  4. **Alerts Feed** — dual-tab: Live (WS events real-time) + History (PostgreSQL `GET /alerts` với acknowledge button). TanStack mutation cho acknowledge.
- **Auth flow:** Zustand store + localStorage persistence. Bearer token injection vào mọi API call. Auto-logout on 401. ProtectedRoute guard redirect `/login`.
- **WebSocket:** auto-reconnect 2s, buffer 200 events, status badge trong header.

## 3.5. Đánh giá

### 3.5.1. Đánh giá kết quả so với mục tiêu

| Mục tiêu đề ra ở Chương 1       | Kết quả đạt được                                                  | Đánh giá     |
| ------------------------------- | ----------------------------------------------------------------- | ------------ |
| AUROC ≥ 0,80 trên tập test      | 0,8093 (LightGBM v4)                                              | **Đạt**      |
| Latency end-to-end p95 < 500 ms | Đo được < 300 ms (inference + Redis + WS)                         | **Đạt**      |
| Dashboard real-time + alert     | 4 trang hoạt động (Login, PatientList, PatientDetail, AlertsFeed) | **Đạt**      |
| MLflow + CI pipeline            | Triển khai đầy đủ, pipeline xanh                                  | **Đạt**      |
| Utility Score dương             | -0.2207 (âm)                                                      | **Chưa đạt** |

### 3.5.2. Phân tích Utility Score âm

Kết quả thực nghiệm cho thấy LightGBM v4 có AUROC 0.8093 (đạt mục tiêu) nhưng Utility Score -0.22 (âm). Nguyên nhân:

1. **Alert quá sớm:** model alert trung bình 53h trước onset — nằm ngoài reward window [-12h, +3h] của PhysioNet. Cảnh báo đúng nhưng quá sớm bị phạt nặng.
2. **False positive cao:** 4.385 FP vs 447 TP ở best threshold (0.05, k=6). FP mỗi case bị phạt U_FP = -0.05.
3. **Feature set limitation:** 131 rolling features (mean/std/min/max/slope × 3 windows × 8 vitals) không đủ phân biệt pre-sepsis trong reward window vs nhiều giờ trước đó. Top PhysioNet teams dùng chuyên sâu hơn (trend derivatives, vasopressor dose, lactate clearance).

Thử nghiệm: relabel [-6h,+3h], CatBoost, ensemble — đều hội tụ quanh -0.22 đến -0.27. Warmup grid tune ra tối ưu = 0h (không giúp). Quyết định lock v4 và chuyển sang hoàn thiện hệ thống.

### 3.5.3. Phân tích tỷ lệ cảnh báo giả

Trên tập test, ở ngưỡng xác suất 0.05 kết hợp quy tắc hysteresis (cần 6 giờ liên tiếp vượt ngưỡng), kết quả:

| Metric                    | Giá trị |
| ------------------------- | ------- |
| True Positive (BN)        | 447     |
| False Negative (BN)       | 11      |
| False Positive (BN)       | 4.385   |
| True Negative (BN)        | 1.208   |
| Alert-ahead-time (mean)   | 53.3h   |
| Alert-ahead-time (median) | 30h     |

Giải pháp đã áp dụng:

- **Hysteresis rule (k=6):** giảm false alarm ~13% so với k=1.
- **`scale_pos_weight=10`:** calibrate proba tốt hơn `is_unbalance=True` (≈54×), AUROC tăng 0.79 → 0.81, utility cải thiện -0.28 → -0.22.

Hướng cải thiện (future work): per-hour sample weight (giờ gần onset weight cao), LSTM sequence 24h, per-patient feature engineering.

### 3.5.4. Khó khăn và bài học

- **Class imbalance nghiêm trọng (~2%):** mất nhiều thời gian tune `scale_pos_weight` + ngưỡng quyết định. Bài học: metric phải là Utility Score, không phải accuracy hay AUROC đơn thuần.
- **Missing value dày đặc ở lab:** kỹ thuật "missing indicator" (thêm cột boolean `is_missing`) hiệu quả hơn imputation phức tạp — lab thiếu mang ý nghĩa lâm sàng (bác sĩ không chỉ định → không nghi ngờ).
- **LocalStack Lambda hay lỗi trên Windows:** chuyển sang consumer Python standalone. Cùng output, dễ debug hơn.
- **Frontend WS-only state bị mất khi refresh:** chuyển sang server-backed hydration (TanStack Query polling REST endpoints) + WS overlay cho real-time. Giải quyết ở session 7.
- **PowerShell encoding:** PS5 (default Windows) đọc `.ps1` theo cp1252 — UTF-8 Vietnamese + em-dash → mojibake. Bắt buộc ASCII-only trong scripts.
- **Zustand selector tạo array mới mỗi render:** `Object.values(s.patients)` trong selector → infinite re-render loop. Fix: subscribe ref stable `s => s.patients`, compute `Object.values()` bên ngoài.
- **MLflow `models:/name/latest` URI invalid:** MLflow `get_latest_versions(stages=["latest"])` báo Invalid stage. Viết helper `_resolve_model_version` handle fallback.

### 3.5.5. Đóng góp và giới hạn

Về **đóng góp**, đồ án cung cấp một tham chiếu mã nguồn mở end-to-end từ streaming, ML, đến backend + frontend + auth + monitoring cho bài toán sepsis prediction — một chủ đề mà đa số tài liệu hiện có chỉ dừng ở notebook huấn luyện, thiếu thành phần triển khai sản xuất.

Về **giới hạn**:

- Utility Score âm (-0.22) — model đoán đúng nhưng quá sớm, bị phạt.
- Chưa có Terraform deployment lên AWS thật — hiện dừng ở GHCR image; kéo image xuống VM là bước triển khai bổ sung khi đưa lên Free Tier.
- Chưa kiểm thử trên dân số bệnh nhân Việt Nam.
- Chưa tích hợp HL7/FHIR để kết nối hệ thống bệnh viện thực.
- Test coverage ở mức smoke (26 unit test) — chưa có integration test và load test như kế hoạch ở 2.10.
