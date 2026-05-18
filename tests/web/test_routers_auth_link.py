"""Tests for web/routers/auth_link.py endpoints."""
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
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


def _get_link_code(tmp_db: Path, email: str) -> str:
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT code FROM pending_email_links WHERE email = ?", (email,)
        ).fetchone()
    assert row is not None
    return row["code"]


# ── /email/request ────────────────────────────────────────────────────────────

def test_link_email_request_204(client, tmp_db, no_email):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(2001)
    r = client.post("/api/auth/link/email/request", json={
        "email": "newlink@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_link_email_request_password_mismatch_422(client, tmp_db):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(2002)
    r = client.post("/api/auth/link/email/request", json={
        "email": "mismatch@example.com",
        "password": "password123",
        "password_confirm": "different123",
    }, headers=_make_headers(uid))
    assert r.status_code == 422


def test_link_email_request_email_taken_by_other_409(client, tmp_db, no_email):
    from services import auth_email, identity
    uid_a = auth_email.register("taken@example.com", "password123")
    uid_b = identity.get_or_create_user_by_telegram(2003)
    r = client.post("/api/auth/link/email/request", json={
        "email": "taken@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }, headers=_make_headers(uid_b))
    assert r.status_code == 409


def test_link_email_request_already_linked_to_same_user_400(client, tmp_db, no_email):
    from services import auth_email
    uid = auth_email.register("myemail@example.com", "password123")
    r = client.post("/api/auth/link/email/request", json={
        "email": "myemail@example.com",
        "password": "newpass123",
        "password_confirm": "newpass123",
    }, headers=_make_headers(uid))
    assert r.status_code == 400


def test_link_email_request_requires_auth(client, tmp_db):
    r = client.post("/api/auth/link/email/request", json={
        "email": "a@b.com",
        "password": "password123",
        "password_confirm": "password123",
    })
    assert r.status_code == 401


# ── /email/verify ─────────────────────────────────────────────────────────────

def test_link_email_verify_204(client, tmp_db, no_email):
    from services import auth_email, identity
    uid = identity.get_or_create_user_by_telegram(2004)
    auth_email.link_email_request(uid, "verifylink@example.com", "password123")
    code = _get_link_code(tmp_db, "verifylink@example.com")
    r = client.post("/api/auth/link/email/verify", json={
        "email": "verifylink@example.com",
        "code": code,
    }, headers=_make_headers(uid))
    assert r.status_code == 204
    assert identity.find_user_id_by_provider("email", "verifylink@example.com") == uid


def test_link_email_verify_wrong_code_401(client, tmp_db, no_email):
    from services import auth_email, identity
    uid = identity.get_or_create_user_by_telegram(2005)
    auth_email.link_email_request(uid, "badcode@example.com", "password123")
    r = client.post("/api/auth/link/email/verify", json={
        "email": "badcode@example.com",
        "code": "000000",
    }, headers=_make_headers(uid))
    assert r.status_code == 401


def test_link_email_verify_requires_auth(client, tmp_db):
    r = client.post("/api/auth/link/email/verify", json={
        "email": "a@b.com",
        "code": "123456",
    })
    assert r.status_code == 401


# ── Remaining provider linking tests (unchanged) ──────────────────────────────

def test_unlink_when_only_one_provider_400(client, tmp_db):
    from services import auth_email
    uid = auth_email.register("solo@example.com", "password123")
    r = client.delete("/api/auth/link/email/solo@example.com", headers=_make_headers(uid))
    assert r.status_code == 400


def test_link_telegram_to_email_user(client, tmp_db, monkeypatch):
    from services import auth_email, auth_telegram
    uid = auth_email.register("linkme@example.com", "password123")
    captured = {}
    def fake_send(token, tg_id, text):
        m = re.search(r"\b(\d{6})\b", text)
        captured["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)
    r = client.post("/api/auth/link/telegram/request-code", json={
        "identifier": "555666",
    }, headers=_make_headers(uid))
    assert r.status_code == 204
    r = client.post("/api/auth/link/telegram/verify-code", json={
        "identifier": "555666", "code": captured["code"],
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_unlink_provider_success(client, tmp_db):
    from services import auth_email, identity
    uid = auth_email.register("two@example.com", "password123")
    identity.link_provider(uid, "telegram", "111222")
    r = client.delete("/api/auth/link/email/two@example.com", headers=_make_headers(uid))
    assert r.status_code == 204
    assert identity.find_user_id_by_provider("email", "two@example.com") is None
