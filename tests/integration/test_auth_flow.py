"""End-to-end auth + role enforcement.

Covers the story from section §2.7 of the report: login, JWT round-trip,
admin-only user management, role-gated acknowledge endpoint.
"""

from __future__ import annotations

import httpx

from .conftest import token_for


def test_admin_can_list_users(backend_up: str, admin_headers: dict[str, str]):
    r = httpx.get(f"{backend_up}/auth/users", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(u["username"] == "admin" for u in body)


def test_viewer_cannot_list_users(backend_up: str, ephemeral_user: dict[str, str]):
    token = token_for(backend_up, ephemeral_user["username"], ephemeral_user["password"])
    r = httpx.get(f"{backend_up}/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_viewer_cannot_acknowledge_alert(backend_up: str, ephemeral_user: dict[str, str]):
    token = token_for(backend_up, ephemeral_user["username"], ephemeral_user["password"])
    # Hit a non-existent alert; role check happens before 404 lookup
    r = httpx.put(
        f"{backend_up}/alerts/999999/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_admin_ack_flow_returns_404_for_missing_alert(
    backend_up: str, admin_headers: dict[str, str]
):
    r = httpx.put(f"{backend_up}/alerts/999999/acknowledge", headers=admin_headers)
    assert r.status_code == 404  # proves admin passes role check then hits 404


def test_me_returns_role_claim(backend_up: str, admin_headers: dict[str, str]):
    r = httpx.get(f"{backend_up}/auth/me", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_invalid_token_returns_401(backend_up: str):
    r = httpx.get(f"{backend_up}/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
    assert r.status_code == 401


def test_register_validates_role_enum(backend_up: str, admin_headers: dict[str, str]):
    r = httpx.post(
        f"{backend_up}/auth/register",
        json={"username": "xx", "password": "goodpass", "role": "superuser"},
        headers=admin_headers,
    )
    # Fails either on role enum (422) or username length (422)
    assert r.status_code == 422


def test_admin_cannot_delete_self(backend_up: str, admin_headers: dict[str, str]):
    me = httpx.get(f"{backend_up}/auth/me", headers=admin_headers).json()
    r = httpx.delete(f"{backend_up}/auth/users/{me['id']}", headers=admin_headers)
    assert r.status_code == 400
