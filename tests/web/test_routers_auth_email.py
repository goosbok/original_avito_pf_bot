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


def test_login_success(client):
    from services import auth_email as _ae
    _ae.register("login@example.com", "password123")
    r = client.post("/api/auth/email/login", json={
        "email": "login@example.com",
        "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_401(client):
    from services import auth_email as _ae
    _ae.register("user@example.com", "password123")
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


# ── /forgot-password & /reset-password (OTP-based) ────────────────────────

def _register_and_get_reset_code(client, monkeypatch, email: str) -> str:
    """Register user, trigger forgot-password, return the 6-digit OTP code."""
    captured = {}

    import services.email_sender as es
    monkeypatch.setattr(
        es, "send_email",
        lambda to, subject, body, **kw: captured.update({"body": body}),
    )
    from services import auth_email as _ae
    _ae.register(email, "password123")
    client.post("/api/auth/email/forgot-password", json={"email": email})
    import re
    m = re.search(r"пароля:\s*(\d{6})", captured.get("body", ""))
    assert m, f"no 6-digit code in reset email body: {captured.get('body')!r}"
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
    from services import auth_email as _ae
    _ae.register("knownreset@example.com", "password123")
    r = client.post("/api/auth/email/forgot-password", json={"email": "knownreset@example.com"})
    assert r.status_code == 200
    assert calls == ["knownreset@example.com"]


def test_reset_password_success_204(client, tmp_db, monkeypatch):
    code = _register_and_get_reset_code(client, monkeypatch, "newpw@example.com")
    r = client.post("/api/auth/email/reset-password", json={
        "email": "newpw@example.com",
        "code": code,
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123",
    })
    assert r.status_code == 204
    r2 = client.post("/api/auth/email/login", json={
        "email": "newpw@example.com",
        "password": "newpassword123",
    })
    assert r2.status_code == 200


def test_reset_password_mismatch_422(client):
    r = client.post("/api/auth/email/reset-password", json={
        "email": "x@example.com",
        "code": "123456",
        "new_password": "password123",
        "new_password_confirm": "different123",
    })
    assert r.status_code == 422


def test_reset_password_wrong_code_401(client, tmp_db, monkeypatch):
    _register_and_get_reset_code(client, monkeypatch, "wrongcode@example.com")
    r = client.post("/api/auth/email/reset-password", json={
        "email": "wrongcode@example.com",
        "code": "000000",
        "new_password": "password123",
        "new_password_confirm": "password123",
    })
    assert r.status_code == 401


def test_reset_password_expired_code_410(client, tmp_db, monkeypatch):
    import sqlite3
    code = _register_and_get_reset_code(client, monkeypatch, "expired@example.com")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE otp_codes SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE destination = 'expired@example.com' AND purpose = 'password_reset'"
        )
        con.commit()
    r = client.post("/api/auth/email/reset-password", json={
        "email": "expired@example.com",
        "code": code,
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123",
    })
    assert r.status_code == 410


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
