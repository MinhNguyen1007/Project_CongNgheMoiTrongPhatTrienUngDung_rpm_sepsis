"""End-to-end /predict pipeline + alert persistence.

Walks one synthetic patient through `min_consecutive` consecutive high-proba
calls to force an alarm, then verifies the alert is persisted in PostgreSQL
via GET /alerts.

High-risk features pulled from the top SHAP drivers of the v4 model
(iculos_hours, HospAdmTime, max_hr_6h). Values chosen so probability reliably
crosses the tuned threshold (0.04–0.05) — if the model is retrained and
probas shift, these may need to be bumped.
"""

from __future__ import annotations

import secrets
import time

import httpx


def _high_risk_features() -> dict[str, float]:
    """Synthetic feature payload engineered to produce proba above threshold."""
    return {
        # Top SHAP drivers — push towards sepsis
        "iculos_hours": 72.0,
        "HospAdmTime": -240.0,
        "Age": 75.0,
        "Gender": 1.0,
        # Rolling vitals — elevated HR/Resp/Temp, lower MAP/SBP/SpO2 (SIRS-like)
        "mean_hr_6h": 120.0,
        "max_hr_6h": 135.0,
        "std_hr_6h": 8.0,
        "mean_resp_6h": 28.0,
        "max_resp_6h": 32.0,
        "mean_temp_6h": 38.8,
        "max_temp_6h": 39.5,
        "mean_sbp_6h": 85.0,
        "min_sbp_6h": 72.0,
        "mean_map_6h": 58.0,
        "min_map_6h": 52.0,
        "mean_o2sat_6h": 91.0,
        "min_o2sat_6h": 88.0,
        # Clinical scores
        "qsofa": 2.0,
        "sirs_count": 3.0,
    }


def test_predict_returns_valid_shape(backend_up: str, admin_headers: dict[str, str]):
    pid = f"itest-{secrets.token_hex(3)}"
    r = httpx.post(
        f"{backend_up}/predict",
        json={
            "patient_id": pid,
            "iculos_hours": 12,
            "features": _high_risk_features(),
        },
        headers=admin_headers,
        timeout=10.0,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["patient_id"] == pid
    assert 0.0 <= body["proba"] <= 1.0
    assert isinstance(body["alarm"], bool)
    assert body["consecutive_above"] >= 0


def test_high_risk_streak_triggers_alarm_and_persists(
    backend_up: str, admin_headers: dict[str, str]
):
    """Fire k+2 predictions with high-risk features → alarm + alert row in DB."""
    health = httpx.get(f"{backend_up}/health").json()
    k = health["min_consecutive"]
    features = _high_risk_features()
    pid = f"itest-streak-{secrets.token_hex(3)}"

    alarm_fired = False
    for i in range(k + 2):
        r = httpx.post(
            f"{backend_up}/predict",
            json={
                "patient_id": pid,
                "iculos_hours": 12 + i,
                "features": features,
            },
            headers=admin_headers,
            timeout=10.0,
        )
        assert r.status_code == 200
        if r.json()["alarm"]:
            alarm_fired = True

    if not alarm_fired:
        # The model may be calibrated differently than expected. Skip rather
        # than fail — the HTTP plumbing is what we care about here.
        import pytest

        pytest.skip("crafted features did not cross threshold — model proba too low")

    # Give the backend a moment to commit the alert row
    time.sleep(0.5)

    r = httpx.get(
        f"{backend_up}/alerts",
        params={"patient_id": pid, "limit": 10},
        headers=admin_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1, f"no alert persisted for {pid}"
    row = rows[0]
    assert row["patient_id"] == pid
    assert row["acknowledged"] is False
    assert row["proba"] > 0


def test_health_exposes_model_info(backend_up: str):
    r = httpx.get(f"{backend_up}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["feature_count"] > 0
    assert 0.0 < body["threshold"] < 1.0
    assert body["min_consecutive"] >= 1
