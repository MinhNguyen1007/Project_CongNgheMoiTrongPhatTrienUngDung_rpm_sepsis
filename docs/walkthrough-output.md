# Giải thích từng output PowerShell — Tour tìm hiểu project

> File này giải thích **ý nghĩa** và **bài học** từ mỗi output khi chạy các lệnh tour hệ thống Sepsis Early-Warning. Đọc theo thứ tự để hiểu luồng dữ liệu end-to-end.

---

## 1. `scripts\dev-up.ps1` — Khởi động toàn bộ hệ thống

```
== Sepsis RPM dev-up ==
[1/4] docker-compose core services...
 ✔ Container project-localstack-1  Running
 ✔ Container project-redis-1       Running
 ✔ Container project-postgres-1    Healthy
 ✔ Container project-minio-1       Healthy
 ✔ Container project-mlflow-1      Running

[2/4] verify MLflow...   MLflow OK: OK
[3/4] spawning backend (port 8000)...
[3/4] spawning frontend (port 5173)...
[4/4] spawning consumer (waits 8s for backend)...
```

### Ý nghĩa
- Script chạy 4 bước: **Docker core → verify MLflow → spawn backend/frontend/consumer**.
- Tất cả container `healthy` = passed healthcheck (Postgres, MinIO) hoặc `Running` = đang chạy chưa có healthcheck (LocalStack, Redis, MLflow).
- `minio-init` **Exited 0** là bình thường — nó là init-container chỉ tạo bucket rồi tắt.
- Backend/Frontend/Consumer chạy **3 cửa sổ PowerShell mới** (không phải Docker) → tiện debug, reload code nhanh.

### Bài học
- **Profile-based compose:** core services luôn chạy, monitoring (Grafana/Prometheus) chỉ bật khi cần → tiết kiệm RAM.
- **Native dev server** thay vì dockerized backend → hot-reload `--reload` của uvicorn hoạt động.

---

## 2. Login + lưu JWT token

```powershell
$T = (curl.exe -s -X POST http://localhost:8000/auth/login `
    -d '{\"username\":\"admin\",\"password\":\"admin123\"}' | ConvertFrom-Json).access_token
```

### Ý nghĩa
- Backend tự seed user `admin/admin123` khi lifespan khởi động lần đầu.
- Response trả JSON `{"access_token": "eyJhbGci...", "token_type": "bearer"}`.
- `ConvertFrom-Json` parse JSON → object PowerShell, lấy `.access_token` lưu vào biến `$T`.
- Mọi request sau gắn header `Authorization: Bearer $T`.

### Bài học
- **JWT pattern:** stateless auth. Server không lưu session, chỉ sign token bằng secret key.
- Token chứa claim `{sub, role, exp}` — backend verify chữ ký + role mỗi request.

---

## 3. `GET /health` — Thông tin model đang chạy

```
status          : ok
model_uri       : models:/sepsis-lgbm-prod/1
feature_count   : 134
threshold       : 0.04
min_consecutive : 8
warmup_hours    : 0
```

### Ý nghĩa
- Backend load model từ MLflow Registry: `sepsis-lgbm-prod` **version 1** (trong .env `MODEL_URI=models:/sepsis-lgbm-prod/1`).
- `feature_count=134` = 131 rolling/clinical features + 3 demographics (Age, Gender, HospAdmTime).
- `threshold=0.04` = ngưỡng xác suất → nếu proba ≥ 0.04 tính là "above".
- `min_consecutive=8` = phải 8 giờ liên tiếp above threshold mới fire alarm (**hysteresis** chống false alarm).
- `warmup_hours=0` = không cần chờ warmup từ đầu ICU.

### Bài học
- Backend **tự bootstrap threshold + k từ MLflow run artifact** (`best_threshold.json`) — không hardcode → model nào dùng threshold đó, tránh training/serving skew.
- CLAUDE.md §12 ghi v4 là `models:/sepsis-lgbm-prod/4` nhưng ở đây v1 vì registry local mới tạo → **chỉ số khác** với production registry.

---

## 4. `GET /patients` — Danh sách bệnh nhân đang giám sát

```
patient_id   : p000001
latest_proba : 0.371654977306376
latest_alarm : True
last_update  : 2026-04-21T09:33:53+00:00
iculos_hours : 54
```

### Ý nghĩa
Có nhiều nhóm patient_id:
- `p000001–p000010` — 10 bệnh nhân PhysioNet thật (simulator replay file .psv)
- `itest-*` — patient ảo do **integration test** tạo
- `itest-streak-*` — test high-risk streak → alarm
- `load-*` — patient ảo do **Locust load test** tạo (mỗi user ảo = 1 patient)

Sắp xếp theo proba giảm dần. Patient có `iculos_hours=155` (`load-d3a13f`) = mô phỏng đã nằm ICU 6.5 ngày.

### Bài học
- **Redis lưu rolling state** cho mỗi patient: `meta` (iculos, last_update), `vitals` (history), `proba_history` (hysteresis).
- Backend query từ Redis keys pattern `patient:*:meta` → tổng hợp list cho frontend.
- Data còn sót từ session trước = **Redis volume persist** (`rpm_redis_data`).

---

## 5. `GET /patients/p000001/proba_history` — Timeline xác suất sepsis

```
timestamp                         proba    alarm  streak
09:33:37.842  0.0757  True  48
09:33:39.352  0.1113  True  48
...
09:33:53.737  0.3716  True  48
```

### Ý nghĩa
- 24 điểm dữ liệu (một hàng/giờ simulator) cho `p000001`.
- Proba **tăng dần** từ 0.07 → 0.37 → model ngày càng tin đây là sepsis khi thấy nhiều giờ dữ liệu.
- `streak=48` = cả 48 giờ đều above threshold 0.04 → thoả mãn `min_consecutive=8` nên **alarm=True**.
- Lưu trong Redis list `patient:p000001:proba_history`, capped 48h.

### Bài học
- **Hysteresis thực tế**: thay vì alert ngay khi 1 lần proba > threshold (dễ false alarm), đợi **k giờ liên tiếp**.
- Chart Proba Timeline ở frontend Patient Detail đọc từ endpoint này.

---

## 6. Redis `KEYS "*"` — Trạng thái bộ nhớ ngắn hạn

```
patient:p000001:vitals        ← raw vitals 7 ngày
patient:p000001:meta          ← iculos, last_update
patient:p000001:proba_history ← proba 48h
patient:p000001:predictions   ← full prediction records
```

### Ý nghĩa
76 keys = **19 patients × 4 keys mỗi patient**:

| Key suffix | Nội dung | TTL/Cap |
|---|---|---|
| `:vitals` | HR, SBP, Temp, SpO2 raw theo giờ | capped 168h (7 ngày) |
| `:meta` | `{iculos_hours, last_update}` hash | không expire |
| `:proba_history` | List proba float | capped 48h |
| `:predictions` | Full prediction JSON (có cả features) | capped 48h |

### Bài học
- **Namespace key**: `<resource>:<id>:<subresource>` — dễ scan, dễ ACL.
- **List + LTRIM** cho rolling window O(1), không phải sorted set.
- **Redis = state store** cho streaming pipeline (không phải cache thuần).

---

## 7. `redis-cli LLEN` + `LINDEX` — Soi vitals raw

```
(integer) 150
"{\"timestamp\": \"2026-04-19T14:08:59\", \"iculos_hours\": 2,
  \"hr\": 97.0, \"o2sat\": 95.0, \"temp\": null, \"sbp\": 98.0,
  \"map\": 75.33, \"dbp\": null, \"resp\": 19.0}"
```

### Ý nghĩa
- 150 record vitals của `p000001` (nhiều lần replay cộng dồn).
- Mỗi record = JSON string với 8 vitals + timestamp + iculos.
- `temp: null` = bệnh nhân không được đo nhiệt giờ đó → model học từ **missing indicator**.

### Bài học
- **Missing = thông tin**: bác sĩ không đo nghĩa là không nghi ngờ → pattern "absence" cũng có giá trị tiên lượng.
- Consumer push vitals raw vào Redis ngay khi validate → frontend có thể vẽ chart vitals luôn, không chờ features.

---

## 8. PostgreSQL `alerts` table

```
 id  | patient_id |        proba        | acknowledged |           timestamp
-----+------------+---------------------+--------------+------------------
 989 | p000001    |   0.371654977306376 | f            | 2026-04-21 09:33:53
 988 | p000001    |  0.3170117610074677 | f            | 2026-04-21 09:33:53
```

### Ý nghĩa
- 989 alert row — bao gồm cả alert từ integration test + load test + session trước.
- `acknowledged=false` (`f`) = chưa có bác sĩ ấn "Xác nhận".
- `proba` field = snapshot xác suất tại **thời điểm alarm fire**.

### Bài học
- **PostgreSQL = bộ nhớ dài hạn**: lịch sử audit, không expire.
- Mỗi giờ proba > threshold → INSERT 1 row (không dedup) → dễ query theo khoảng thời gian.
- Frontend **AlertsFeed tab History** query `GET /alerts` từ đây.

---

## 9. PostgreSQL `users` table

```
 id | username |  role  | is_active
----+----------+--------+-----------
  1 | admin    | admin  | t
  2 | doctor01 | doctor | t
  3 | viewer01 | viewer | t
```

### Ý nghĩa
- 3 user = 3 role **RBAC** của hệ thống.
- `is_active=t` (true) = chưa bị admin disable.
- Password không hiện → lưu dạng bcrypt hash trong cột `hashed_password`.

### Bài học
- **3 role rõ ràng:**
  - `admin` → CRUD user + ack alert + tất cả
  - `doctor` → ack alert + xem
  - `viewer` → chỉ xem (read-only)
- Dependency `require_role(*allowed)` ở backend enforce ngay tầng HTTP (403 trước khi DB query).

---

## 10. `awslocal dynamodb list-tables`

```
{
    "TableNames": [
        "patient_latest_features",
        "patient_recent_predictions"
    ]
}
```

### Ý nghĩa
2 table DynamoDB do LocalStack giả lập:
- `patient_latest_features` — hàng mới nhất mỗi patient (131 features)
- `patient_recent_predictions` — ngược với Redis, lưu predictions ở DynamoDB (hiện empty vì consumer có thể đã disable nhánh này)

### Bài học
- **DynamoDB = NoSQL key-value**: lookup theo partition key `patient_id` O(1).
- Dùng DynamoDB khi cần **"hàng mới nhất"** — ghi đè upsert, không tích lũy history như PostgreSQL.
- **LocalStack** giả lập AWS API → đổi sang AWS thật chỉ cần bỏ `--endpoint-url`.

---

## 11. `awslocal dynamodb scan patient_latest_features` — 131 features

Output JSON rất dài với các field:
```
slope_temp_12h   : -0.046
std_o2sat_6h     : 1.38
mean_map_24h     : 84.35
min_sbp_6h       : 138.0
qsofa_score      : 1
sirs_count       : 1
missing_temp     : 1
iculos_hours     : 48.0
patient_id       : p000003
...
```

### Ý nghĩa
Đây là **output của FeatureEngineer** trong consumer. Phân loại:

| Nhóm | Số lượng | Ví dụ |
|---|---|---|
| Rolling stats | 120 | `mean_hr_6h`, `std_sbp_12h`, `slope_temp_24h` |
| Missing indicators | 8 | `missing_temp=1`, `missing_dbp=0` |
| Clinical scores | 3 | `qsofa_score=1`, `sirs_count=1`, `iculos_hours=48` |

**Công thức:** 8 vitals × 3 cửa sổ (6/12/24h) × 5 stats (mean/std/min/max/slope) = 120 + 8 missing + 3 clinical = **131 features**.

`Count: 5` = hiện có 5 patients trong bảng (scan chỉ giới hạn 1 bản ghi nhưng đếm tổng).

### Bài học
- **Feature parity 100%** training ↔ serving — cùng code `FeatureEngineer` class (`ml/src/build_features.py` import trực tiếp từ `data-pipeline/consumer/feature_engineer.py`).
- **Slope** = derivative dấu hiệu xu hướng (HR đang giảm/tăng) — quan trọng hơn absolute value trong sepsis.
- `Type: S` (string) vì DynamoDB không có float native — cast lại khi đọc.

---

## 12. `awslocal dynamodb scan patient_recent_predictions`

```
{"Items": [], "Count": 0}
```

### Ý nghĩa
Bảng trống — consumer hiện **không ghi** predictions vào DynamoDB (có thể đã chuyển sang Redis để tránh trùng).

### Bài học
- **Không dùng DynamoDB = không sai** — chỉ là 1 tùy chọn chưa dùng.
- Với streaming, Redis rẻ hơn DynamoDB (không tính chi phí read/write units).

---

## 13. `awslocal kinesis describe-stream vital-signs-stream`

```
"StreamStatus": "ACTIVE"
"RetentionPeriodHours": 24
"ShardId": "shardId-000000000000"
```

### Ý nghĩa
- 1 shard duy nhất (đủ cho scale đồ án).
- Retention 24h — record quá 24h sẽ bị Kinesis xoá tự động.
- **ACTIVE** = ready to accept writes.

### Bài học
- **Kinesis = message broker** tương tự Kafka.
- **Shard** = đơn vị song song. Scale bằng cách tăng shard (1 consumer/shard).
- Partition key = `patient_id` → đảm bảo record cùng BN rơi cùng shard → ordered processing.

---

## 14. `awslocal s3 ls s3://rpm-raw-data/` — NoSuchBucket ⚠️

```
An error occurred (NoSuchBucket) when calling the ListObjectsV2 operation
```

### Ý nghĩa
LocalStack **restart mất data** (không persist) → bucket init script tạo rồi cũng mất khi restart container.

### Bài học
- Nếu cần bucket, chạy lại init: `docker-compose restart localstack` hoặc:
  ```powershell
  awslocal s3 mb s3://rpm-raw-data
  awslocal s3 mb s3://rpm-mlflow-artifacts
  ```
- **MinIO** (dùng cho MLflow artifacts) có volume persist → không gặp vấn đề này.

---

## 15. `awslocal dynamodb get-item` — Lấy 1 patient cụ thể

Lấy features của `p000001` (current, `iculos_hours: 54.0`):
```
max_hr_6h     : 100.0      ← nhịp tim cao nhất 6h qua
mean_sbp_6h   : 105.5      ← huyết áp tâm thu trung bình — HẠ
min_map_6h    : 44.0       ← MAP cực thấp — RED FLAG sepsis
min_o2sat_6h  : 85.0       ← SpO2 85% = thiếu oxy nặng
qsofa_score   : 1          ← qSOFA dương tính 1/3
```

### Ý nghĩa lâm sàng
- **SBP 105**, **MAP 44**, **SpO2 85** — đây là dấu hiệu **sốc nhiễm khuẩn** sớm:
  - MAP < 65 mmHg là điểm cắt cho vasopressor.
  - SpO2 < 90% cần can thiệp hô hấp.
- Model đúng đã alarm cho patient này.

### Bài học
- **Features không chỉ là số** — cần hiểu ý nghĩa lâm sàng để debug alarm đúng/sai.
- `missing_dbp=1` → DBP không được đo → mean/std DBP vẫn tính được từ SBP+MAP công thức.

---

## 16. Monitoring profile — Prometheus + Grafana

```
✔ Container project-prometheus-1  Started   → port 9090
✔ Container project-grafana-1     Started   → port 3000
```

### Ý nghĩa
- Profile `monitoring` chạy riêng — không tốn RAM khi dev thường.
- Prometheus scrape `/metrics` backend mỗi 15s.
- Grafana pre-provisioned dashboard "Sepsis EWS".

---

## 17. `curl /metrics` — Prometheus exposition format

```
# HELP http_requests_total Total number of requests...
# TYPE http_requests_total counter
http_requests_total{handler="/metrics",method="GET",status="2xx"} 1.0

# HELP http_request_duration_highr_seconds Latency...
# TYPE http_request_duration_highr_seconds histogram
```

### Ý nghĩa
- **Text format** chuẩn Prometheus — human-readable.
- 3 metric types quan trọng:
  - `counter` (chỉ tăng) — `http_requests_total`
  - `gauge` (lên xuống) — `active_websocket_connections`
  - `histogram` (bucketed) — `http_request_duration_seconds`
- Label `{handler, method, status}` → query linh hoạt (PromQL).

### Bài học
- Grafana panel "p95 latency":
  ```
  histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))
  ```
- **Push vs Pull** — Prometheus **pull** (gọi đến backend) → đơn giản cho service discovery.

---

## 18. `pytest tests\unit` — 26 tests pass trong 3s

```
tests/unit/test_auth.py::test_hash_is_not_plaintext              PASSED
tests/unit/test_auth.py::test_hash_is_salted_so_two_calls_differ PASSED
tests/unit/test_decision.py::test_alarm_fires_after_k_consecutive PASSED
tests/unit/test_feature_engineer.py::test_feature_count_is_131   PASSED
tests/unit/test_utility_score.py::test_utility_tp_max_inside_optimal_window PASSED
...
26 passed in 3.08s
```

### Ý nghĩa
5 module được test:

| Module | Số test | Nội dung |
|---|---|---|
| `auth` | 4 | bcrypt hash + salted + verify |
| `decision` | 5 | hysteresis alarm logic |
| `feature_engineer` | 6 | 131 features + per-patient isolation |
| `utility_score` | 6 | PhysioNet utility + warmup |
| `validator` | 5 | vital signs trong khoảng sinh lý |

### Bài học
- **Unit test = không cần backend chạy** — chạy pure Python, ~3s.
- Test `test_per_patient_isolation` quan trọng: đảm bảo rolling window của BN A không leak vào BN B.

---

## 19. `pytest tests\integration` — 11 tests pass trong 72s

```
test_auth_flow.py::test_viewer_cannot_list_users          PASSED
test_auth_flow.py::test_viewer_cannot_acknowledge_alert   PASSED
test_auth_flow.py::test_invalid_token_returns_401         PASSED
test_predict_flow.py::test_high_risk_streak_triggers_alarm_and_persists PASSED
...
11 passed in 71.83s
```

### Ý nghĩa
- Gọi HTTP thật đến backend `http://localhost:8000`.
- Test cover:
  - **RBAC** (viewer không ack được, admin được)
  - **Auth** (token invalid → 401, role sai → 403)
  - **/predict → DB persist** (streak k+2 giờ → alert trong PostgreSQL)
- 72s = bcrypt slow (~300ms mỗi hash) × 20 lần login.

### Bài học
- **Skip-if-backend-down pattern**: fixture `backend_up` dùng `pytest.skip(...)` nếu `/health` không reachable → CI unit job vẫn pass khi Docker chưa lên.
- **Integration test = safety net** khi refactor — chỉ cần 11 test đã cover 80% happy path.

---

## 20. `locust` load test — 20 users, 20s

```
Type  Name           # reqs  # fails  Avg   p95
POST  /auth/login    20      0        3178  4800ms
POST  /predict       448     0        142   270ms
GET   /patients      41      0        656   2700ms
GET   /alerts        12      0        364   1300ms

/predict p95 = 270.0 ms  (SLO: <500 ms) ✅
```

### Ý nghĩa
- **530 requests** trong 20s, **0 failure**.
- `/predict` p95 = **270ms** — dưới SLO 500ms §10 CLAUDE.md → **PASS**.
- `/auth/login` chậm 4.8s p95 — **bcrypt cost** (verify password tốn CPU). Nhưng chỉ hit 1 lần/user `on_start()`.
- `/patients` p95 2700ms — chậm vì scan nhiều Redis keys (19 patient × 4 key).

### Bài học
- **SLO metric chính** cho inference: `/predict` p95 (đường nóng từ consumer).
- Load test không chỉ để test scale — còn để **khám phá bottleneck**. Ở đây thấy `/patients` chậm nếu nhiều BN → cần cache.
- Locust task `@task(3)` vs `@task(1)` = trọng số gọi — mô phỏng 3 lần GET patients cho mỗi lần GET alerts.

---

## Kết luận — Luồng dữ liệu đã thấy được

```
[Simulator]
    ↓ Kinesis (vital-signs-stream, 1 shard, 24h retention)
[Consumer]
    ├→ [DynamoDB] patient_latest_features (131 cols upsert)
    ├→ [Redis]    patient:{id}:vitals/meta/proba_history (rolling)
    ├→ [S3]       rpm-raw-data/ (batch dump, tùy có bucket)
    └→ [Backend /predict]
            ↓ load [MLflow Registry] models:/sepsis-lgbm-prod/N
            ↓ hysteresis check (k consecutive)
            ├→ [WebSocket /ws/alerts] broadcast
            └→ [PostgreSQL] alerts table INSERT
                    ↑
[Frontend React] ← curl /patients/*, /alerts, WS, /auth/*
    ├→ Login page
    ├→ PatientList (poll 5s + WS overlay)
    ├→ PatientDetail (proba + vitals + Temp separate chart)
    ├→ AlertsFeed (Live WS + History DB)
    └→ AdminSettings (CRUD users, role-gated)

[Prometheus] scrape backend /metrics mỗi 15s
[Grafana] dashboard "Sepsis EWS" (7 panels)
[pytest] unit (26) + integration (11)
[locust] load test (/predict p95=270ms)
```

### Bài học tổng
1. **Mỗi storage có vai trò riêng:**
   - Kinesis = queue
   - DynamoDB = latest-value NoSQL
   - Redis = rolling state + cache
   - PostgreSQL = audit log + users
   - S3 = cold batch
   - MLflow Registry = model versioning
2. **Feature parity** giữa training và serving = chia sẻ code class → không skew.
3. **Hysteresis** (k consecutive hours) = sức mạnh giảm false alarm cho y tế.
4. **Test pyramid đủ 3 tầng** — unit (nhanh) → integration (realistic) → load (SLO).
5. **RBAC bằng dependency factory** FastAPI đơn giản nhưng enforce đúng tầng HTTP.

---

*File tạo tự động từ session tour ngày 2026-04-21. Xem CLAUDE.md §12 cho lịch sử quyết định thiết kế.*
