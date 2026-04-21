"""Smoke tests for password hashing used by the auth layer."""

from __future__ import annotations

import pytest

pytest.importorskip("passlib")

from app.backend.auth import hash_password, verify_password


def test_hash_is_not_plaintext():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert len(h) > 20


def test_hash_is_salted_so_two_calls_differ():
    assert hash_password("s3cret") != hash_password("s3cret")


def test_verify_accepts_correct_password():
    h = hash_password("s3cret")
    assert verify_password("s3cret", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("s3cret")
    assert verify_password("wrong", h) is False
