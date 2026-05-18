"""Tests for email registration and login endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def _make_headers(uid: int) -> dict:
    from web.auth import create_jwt
    return {"Authorization": f"Bearer {create_jwt(uid)}"}


@pytest.fixture
def no_email(monkeypatch):
    """Suppress actual email sends."""
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda *a, **kw: None)


def test_register_returns_jwt(client):
    r = client.post("/api/auth/email/register", json={
        "email": "alice@example.com",
        "password": "password123",
        "password_confirm": "password123",
        "first_name": "Alice",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_register_duplicate_email_409(client):
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }
    client.post("/api/auth/email/register", json=payload).raise_for_status()
    r = client.post("/api/auth/email/register", json=payload)
    assert r.status_code == 409


def test_register_invalid_email_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "not-an-email",
        "password": "password123",
        "password_confirm": "password123",
    })
    assert r.status_code == 422


def test_register_short_password_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com",
        "password": "short",
        "password_confirm": "short",
    })
    assert r.status_code == 422


def test_register_password_mismatch_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com",
        "password": "password123",
        "password_confirm": "different123",
    })
    assert r.status_code == 422


def test_login_success(client):
    client.post("/api/auth/email/register", json={
        "email": "login@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "login@example.com",
        "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_401(client):
    client.post("/api/auth/email/register", json={
        "email": "user@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "user@example.com",
        "password": "wrongpass",
    })
    assert r.status_code == 401


def test_login_unknown_email_401(client):
    r = client.post("/api/auth/email/login", json={
        "email": "nobody@example.com",
        "password": "password123",
    })
    assert r.status_code == 401


# ── password reset endpoint tests ─────────────────────────────────────────────

import re as _re


def _register_and_get_reset_token(client, monkeypatch, email: str) -> str:
    """Register a user, call forgot-password, return the raw token from the email."""
    captured = {}

    import services.email_sender as es
    monkeypatch.setattr(
        es, "send_email",
        lambda to, subject, body, **kw: captured.update({"body": body}),
    )
    client.post("/api/auth/email/register", json={
        "email": email,
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    client.post("/api/auth/email/forgot-password", json={"email": email})
    m = _re.search(r"token=([^\s\n]+)", captured["body"])
    assert m, "no token in reset email"
    return m.group(1)


def test_forgot_password_always_200(client, monkeypatch):
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda *a, **kw: None)
    r = client.post("/api/auth/email/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200


def test_forgot_password_sends_email_for_known_address(client, monkeypatch):
    calls = []
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda to, *a, **kw: calls.append(to))
    client.post("/api/auth/email/register", json={
        "email": "knownreset@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/forgot-password", json={"email": "knownreset@example.com"})
    assert r.status_code == 200
    assert calls == ["knownreset@example.com"]


def test_reset_password_success_204(client, tmp_db, monkeypatch):
    raw_token = _register_and_get_reset_token(client, monkeypatch, "newpw@example.com")
    r = client.post("/api/auth/email/reset-password", json={
        "token": raw_token,
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123",
    })
    assert r.status_code == 204
    # Can now log in with new password
    r2 = client.post("/api/auth/email/login", json={
        "email": "newpw@example.com",
        "password": "newpassword123",
    })
    assert r2.status_code == 200


def test_reset_password_mismatch_422(client):
    r = client.post("/api/auth/email/reset-password", json={
        "token": "anytoken",
        "new_password": "password123",
        "new_password_confirm": "different123",
    })
    assert r.status_code == 422


def test_reset_password_invalid_token_400(client, tmp_db):
    r = client.post("/api/auth/email/reset-password", json={
        "token": "invalidtoken",
        "new_password": "password123",
        "new_password_confirm": "password123",
    })
    assert r.status_code == 400


# ── /change-password ──────────────────────────────────────────────────────

def _link_email_for_user(uid: int, email: str, password: str, tmp_db) -> None:
    """Helper: fully link email to uid (request + verify)."""
    import sqlite3
    from services import auth_email as _ae
    _ae.link_email_request(uid, email, password)
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT code FROM pending_email_links WHERE email = ?", (email,)
        ).fetchone()
    _ae.link_email_verify(uid, email, row["code"])


def test_change_password_204(client, tmp_db, no_email):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(8001)
    _link_email_for_user(uid, "chpw@example.com", "oldpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "oldpass1",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_change_password_wrong_current_401(client, tmp_db, no_email):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(8002)
    _link_email_for_user(uid, "chpw2@example.com", "rightpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "wrongpass1",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    }, headers=_make_headers(uid))
    assert r.status_code == 401


def test_change_password_mismatch_422(client, tmp_db, no_email):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(8003)
    _link_email_for_user(uid, "chpw3@example.com", "oldpass1", tmp_db)

    r = client.post("/api/auth/change-password", json={
        "current_password": "oldpass1",
        "new_password": "newpass99",
        "new_password_confirm": "different99",
    }, headers=_make_headers(uid))
    assert r.status_code == 422


def test_change_password_requires_auth_401(client, tmp_db):
    r = client.post("/api/auth/change-password", json={
        "current_password": "any",
        "new_password": "newpass99",
        "new_password_confirm": "newpass99",
    })
    assert r.status_code == 401
