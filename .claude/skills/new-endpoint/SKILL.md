---
name: new-endpoint
description: Scaffold một FastAPI endpoint mới trong app/backend với router, schema, dependency injection, test. Dùng khi thêm API cho dashboard hoặc integration.
---

# Skill: New FastAPI Endpoint

Tạo endpoint FastAPI mới đầy đủ: router + Pydantic schema + business logic + test.

## Quy trình

1. Hỏi user (nếu chưa rõ):
   - Method (GET/POST/PUT/DELETE) và path (vd `/patients/{id}/alerts`)
   - Input schema (body/query params)
   - Output schema
   - Auth required? (mặc định yes, trừ healthcheck)
2. Xác định router phù hợp trong `app/backend/src/routers/`. Nếu chưa có, tạo mới.
3. Thêm schema Pydantic vào `app/backend/src/schemas/`.
4. Thêm handler vào router. Dùng dependency injection cho DB session, current user.
5. Nếu có logic phức tạp, tách ra service trong `app/backend/src/services/`.
6. Viết test trong `tests/unit/backend/test_<router>.py` bao gồm: happy path, auth fail, validation fail.
7. Chạy `pytest tests/unit/backend/ -v` để verify.

## Cấu trúc thư mục backend

```
app/backend/
├── src/
│   ├── main.py              # FastAPI app, include routers
│   ├── config.py            # Settings (pydantic-settings)
│   ├── deps.py              # Dependencies: get_db, get_current_user
│   ├── routers/
│   │   ├── patients.py
│   │   ├── alerts.py
│   │   ├── predictions.py
│   │   └── ws.py            # WebSocket
│   ├── schemas/
│   │   ├── patient.py
│   │   └── alert.py
│   ├── services/
│   │   ├── ml_inference.py  # load MLflow model, predict
│   │   └── realtime.py      # broadcast WebSocket
│   ├── models/              # SQLAlchemy / dataclass
│   └── db.py                # SessionLocal
└── Dockerfile
```

## Template router

```python
"""Alerts router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.backend.src.deps import get_db, get_current_user
from app.backend.src.schemas.alert import AlertAck, AlertOut
from app.backend.src.services import alerts as alerts_service
from app.backend.src.models.user import User

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertOut:
    alert = alerts_service.get_by_id(db, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.post("/{alert_id}/ack", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    body: AlertAck,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertOut:
    return alerts_service.acknowledge(db, alert_id, user.id, body.note)
```

## Template schema

```python
from datetime import datetime
from pydantic import BaseModel, Field


class AlertAck(BaseModel):
    note: str | None = Field(None, max_length=500)


class AlertOut(BaseModel):
    id: int
    patient_id: str
    triggered_at: datetime
    probability: float
    acknowledged: bool
    acknowledged_by: int | None
    acknowledged_at: datetime | None

    model_config = {"from_attributes": True}
```

## Template test

```python
def test_ack_alert_happy_path(client, auth_headers, db_session, sample_alert):
    response = client.post(
        f"/alerts/{sample_alert.id}/ack",
        json={"note": "Đã xử lý"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged"] is True


def test_ack_alert_requires_auth(client, sample_alert):
    response = client.post(f"/alerts/{sample_alert.id}/ack", json={})
    assert response.status_code == 401


def test_ack_alert_not_found(client, auth_headers):
    response = client.post("/alerts/99999/ack", json={}, headers=auth_headers)
    assert response.status_code == 404
```

## Lưu ý

- Luôn dùng `response_model` để giới hạn field trả về (tránh leak).
- Auth mặc định qua `get_current_user` dependency.
- Status code rõ ràng: 201 cho Create, 204 cho Delete.
- Nếu liên quan realtime (vd alert mới), gọi `realtime.broadcast()` sau khi commit DB.
