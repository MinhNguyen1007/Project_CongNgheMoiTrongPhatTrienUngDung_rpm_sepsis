"""Test manual trigger endpoints: POST /api/drift/check, POST /api/models/retrain.

Cả 2 endpoint phải trả 202 ngay + spawn background task (không block client).
Test dùng TestClient với FastAPI app minimal (không qua lifespan của main.py)
để tránh load model + connect Kafka.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Minimal app chỉ mount 2 router cần test."""
    from backend.app.api import drift, models

    app = FastAPI()
    app.include_router(drift.router)
    app.include_router(models.router)
    return TestClient(app)


def test_post_drift_check_returns_202_and_spawns_task(client: TestClient) -> None:
    """Endpoint phải trả 202 ngay + gọi asyncio.create_task để chạy nền."""
    with patch("backend.app.api.drift.asyncio.create_task") as mock_task:
        resp = client.post("/api/drift/check")

    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted", "reason": "manual"}
    assert mock_task.call_count == 1
    # Close coro để tránh "never awaited" warning.
    mock_task.call_args[0][0].close()


def test_post_retrain_returns_202_and_spawns_task(client: TestClient) -> None:
    with patch("backend.app.api.models.asyncio.create_task") as mock_task:
        resp = client.post("/api/models/retrain")

    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted", "reason": "manual"}
    assert mock_task.call_count == 1
    mock_task.call_args[0][0].close()
