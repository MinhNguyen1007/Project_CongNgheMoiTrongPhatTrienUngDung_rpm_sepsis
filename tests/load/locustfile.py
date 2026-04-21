"""Locust load test for the Sepsis Early-Warning backend.

Goal: validate §10 SLO claim in CLAUDE.md — p95 inference latency < 500ms
end-to-end under concurrent load.

Two workloads:
  * InferenceUser  — posts /predict with realistic high-risk features
  * DashboardUser  — reads /patients, /patients/{id}/proba_history, /alerts

Run (headless, 50 users, 30 seconds)::

    locust -f tests/load/locustfile.py \\
        --host http://localhost:8000 \\
        --users 50 --spawn-rate 10 --run-time 30s \\
        --headless --csv reports/load

The HTML / CSV output lets you capture p95 for the report.
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, events, task

ADMIN_USERNAME = os.environ.get("LOCUST_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "admin123")

HIGH_RISK_FEATURES = {
    "iculos_hours": 72.0,
    "HospAdmTime": -240.0,
    "Age": 75.0,
    "Gender": 1.0,
    "mean_hr_6h": 118.0,
    "max_hr_6h": 135.0,
    "std_hr_6h": 9.0,
    "mean_resp_6h": 27.0,
    "max_resp_6h": 32.0,
    "mean_temp_6h": 38.9,
    "max_temp_6h": 39.4,
    "mean_sbp_6h": 86.0,
    "min_sbp_6h": 72.0,
    "mean_map_6h": 60.0,
    "min_map_6h": 52.0,
    "mean_o2sat_6h": 91.0,
    "min_o2sat_6h": 88.0,
    "qsofa": 2.0,
    "sirs_count": 3.0,
}


def _jitter(features: dict[str, float]) -> dict[str, float]:
    """Small per-request jitter so predict_proba doesn't cache identical inputs."""
    return {k: v + random.uniform(-0.5, 0.5) for k, v in features.items()}


class AuthedUser(HttpUser):
    """Base class — log in as admin on start to populate Authorization header."""

    abstract = True

    def on_start(self) -> None:
        r = self.client.post(
            "/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            name="/auth/login",
        )
        if r.status_code != 200:
            raise RuntimeError(f"login failed: {r.status_code} {r.text}")
        token = r.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"


class InferenceUser(AuthedUser):
    """Simulates a consumer pushing hourly readings for many patients."""

    wait_time = between(0.05, 0.3)

    def on_start(self) -> None:
        super().on_start()
        self.patient_id = f"load-{uuid.uuid4().hex[:6]}"
        self.iculos = random.randint(6, 120)

    @task
    def predict(self) -> None:
        self.iculos += 1
        self.client.post(
            "/predict",
            json={
                "patient_id": self.patient_id,
                "iculos_hours": self.iculos,
                "features": _jitter(HIGH_RISK_FEATURES),
            },
            name="/predict",
        )


class DashboardUser(AuthedUser):
    """Simulates clinicians refreshing the dashboard."""

    wait_time = between(1.0, 3.0)

    @task(3)
    def list_patients(self) -> None:
        self.client.get("/patients", name="/patients")

    @task(2)
    def list_alerts(self) -> None:
        self.client.get("/alerts?limit=50", name="/alerts")

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")


# ── Custom threshold reporting (p95 < 500ms per §10 SLO) ──


@events.test_stop.add_listener
def _report_slo_breach(environment, **_kwargs) -> None:
    stats = environment.stats.get("/predict", "POST")
    if stats.num_requests == 0:
        return
    p95 = stats.get_response_time_percentile(0.95)
    print(f"\n/predict p95 = {p95:.1f} ms  (SLO: <500 ms)")
    if p95 > 500:
        environment.process_exit_code = 1
        print(f"SLO BREACH: p95 {p95:.1f} ms exceeds 500 ms budget.")
