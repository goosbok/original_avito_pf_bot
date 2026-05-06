"""Tests for web/routers/auth_link.py endpoints."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    """Create a test client with JWT secret and BOT_TOKEN monkeypatched."""
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    from web.main import app
    return TestClient(app)


def _make_headers(uid: int) -> dict:
    """Create Authorization header with JWT for given user_id."""
    from web.auth import create_jwt
    return {"Authorization": f"Bearer {create_jwt(uid)}"}


def test_link_email_to_telegram_user(client, tmp_db: Path):
    """Telegram user links email — should return 204."""
    from services import identity
    # Create a telegram user first
    uid = identity.get_or_create_user_by_telegram(888999)
    headers = _make_headers(uid)
    r = client.post("/api/auth/link/email", json={
        "email": "newlink@example.com",
        "password": "password123",
    }, headers=headers)
    assert r.status_code == 204
    # Verify email was linked to this user
    assert identity.find_user_id_by_provider("email", "newlink@example.com") == uid


def test_link_email_already_used_409(client, tmp_db: Path):
    """Attempting to link email already used by another user — should return 409."""
    from services import auth_email, identity
    # Register user A with email
    uid_a = auth_email.register("taken@example.com", "password123")
    # Create user B (telegram)
    uid_b = identity.get_or_create_user_by_telegram(777888)
    # Try to link that email to user B
    r = client.post("/api/auth/link/email", json={
        "email": "taken@example.com",
        "password": "password123",
    }, headers=_make_headers(uid_b))
    assert r.status_code == 409


def test_unlink_when_only_one_provider_400(client, tmp_db: Path):
    """Trying to unlink last provider — should return 400."""
    from services import auth_email
    uid = auth_email.register("solo@example.com", "password123")
    r = client.delete("/api/auth/link/email/solo@example.com", headers=_make_headers(uid))
    assert r.status_code == 400


def test_link_telegram_to_email_user(client, tmp_db: Path, monkeypatch):
    """Email user links telegram via OTP — should return 204."""
    from services import auth_email, auth_telegram
    uid = auth_email.register("linkme@example.com", "password123")
    captured = {}
    def fake_send(token, tg_id, text):
        m = re.search(r"\b(\d{6})\b", text)
        captured["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    # Request code
    r = client.post("/api/auth/link/telegram/request-code", json={
        "identifier": "555666",
    }, headers=_make_headers(uid))
    assert r.status_code == 204

    # Verify code
    r = client.post("/api/auth/link/telegram/verify-code", json={
        "identifier": "555666", "code": captured["code"],
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_unlink_provider_success(client, tmp_db: Path):
    """Link two providers, then unlink one — should return 204."""
    from services import auth_email, identity
    uid = auth_email.register("two@example.com", "password123")
    # Link telegram too
    identity.link_provider(uid, "telegram", "111222")
    # Now unlink email
    r = client.delete("/api/auth/link/email/two@example.com", headers=_make_headers(uid))
    assert r.status_code == 204
    # Verify email is no longer linked
    assert identity.find_user_id_by_provider("email", "two@example.com") is None
