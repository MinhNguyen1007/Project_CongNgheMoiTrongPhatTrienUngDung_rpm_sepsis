---
description: Khởi động toàn bộ hệ thống local qua docker-compose và verify health
allowed-tools: Bash(docker-compose:*), Bash(docker:*), Bash(curl:*), Bash(sleep:*), Read
---

# Deploy Local Stack

Khởi động đầy đủ hệ thống local và kiểm tra health của từng service.

## Quy trình

1. Check docker đang chạy: `docker ps > /dev/null || echo "Docker Desktop chưa start"`.
2. Chạy `docker-compose up -d --build`.
3. Đợi 15-30s cho service khởi động. Hiển thị log khởi tạo cuối.
4. Verify sequence (mỗi service test riêng):

| Service              | Health check command                                              |
|----------------------|-------------------------------------------------------------------|
| LocalStack           | `curl -sf http://localhost:4566/_localstack/health`               |
| MLflow               | `curl -sf http://localhost:5000`                                  |
| MinIO                | `curl -sf http://localhost:9000/minio/health/live`                |
| PostgreSQL           | `docker exec postgres pg_isready`                                 |
| Redis                | `docker exec redis redis-cli ping`                                |
| FastAPI              | `curl -sf http://localhost:8000/health`                           |
| Frontend             | `curl -sf http://localhost:5173`                                  |
| Prometheus           | `curl -sf http://localhost:9090/-/healthy`                        |
| Grafana              | `curl -sf http://localhost:3000/api/health`                       |

5. Init LocalStack resources nếu cần: chạy `bash infra/localstack/init.sh`.
6. Tóm tắt bảng trạng thái + URL truy cập.

## Output template

```
Stack status:
  [✓] LocalStack     http://localhost:4566
  [✓] MLflow UI      http://localhost:5000
  [✓] MinIO console  http://localhost:9001
  [✓] Backend API    http://localhost:8000/docs
  [✓] Frontend       http://localhost:5173
  [✓] Grafana        http://localhost:3000  (admin/admin)
  [✗] Prometheus     http://localhost:9090  ← service DOWN

Next steps:
- Chạy simulator:  python data-pipeline/simulator/run.py --patients 10
- Mở dashboard:    http://localhost:5173
- Xem logs:        docker-compose logs -f <service>
```

## Lưu ý

- Nếu 1 service DOWN, check `docker-compose logs <service>` và báo lỗi cụ thể thay vì chỉ "DOWN".
- Nếu cổng conflict, suggest đổi port trong `docker-compose.yml`.
- Lần đầu run sẽ lâu (pull image) — cảnh báo user đợi.
