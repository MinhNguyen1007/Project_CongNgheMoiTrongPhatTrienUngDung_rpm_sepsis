"""Integration-test fixtures — require a running backend at BACKEND_URL.

All tests in this folder are skipped cleanly when the backend is unreachable,
so unit-test CI passes even without docker-compose up.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Generator

import httpx
import pytest

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


@pytest.fixture(scope="session")
def backend_up() -> str:
    try:
        r = httpx.get(f"{BACKEND_URL}/health", timeout=2.0)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"backend not reachable at {BACKEND_URL}: {exc}")
    return BACKEND_URL


@pytest.fixture(scope="session")
def admin_token(backend_up: str) -> str:
    r = httpx.post(
        f"{backend_up}/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=5.0,
    )
    if r.status_code != 200:
        pytest.skip(f"admin login failed ({r.status_code}) — seed admin first")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def ephemeral_user(
    backend_up: str, admin_headers: dict[str, str]
) -> Generator[dict[str, str], None, None]:
    """Create a throwaway user, yield credentials + id, clean up after test."""
    uname = f"itest_{secrets.token_hex(4)}"
    pwd = "integration-pass-123"
    payload = {
        "username": uname,
        "password": pwd,
        "full_name": "Integration Test",
        "role": "viewer",
    }
    r = httpx.post(f"{backend_up}/auth/register", json=payload, headers=admin_headers, timeout=5.0)
    r.raise_for_status()
    user = r.json()
    try:
        yield {"username": uname, "password": pwd, "id": str(user["id"]), "token": ""}
    finally:
        httpx.delete(f"{backend_up}/auth/users/{user['id']}", headers=admin_headers, timeout=5.0)


def token_for(backend_url: str, username: str, password: str) -> str:
    r = httpx.post(
        f"{backend_url}/auth/login",
        json={"username": username, "password": password},
        timeout=5.0,
    )
    r.raise_for_status()
    return r.json()["access_token"]
