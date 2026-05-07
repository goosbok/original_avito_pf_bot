"""Tests for web/routers/auth_telegram.py endpoints."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def test_request_code_sends_via_bot(client, monkeypatch):
    captured = {}
    def fake_send(token, tg_id, text):
        captured.update(token=token, tg_id=tg_id, text=text)
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    r = client.post("/api/auth/telegram/request-code", json={"identifier": "12345"})
    assert r.status_code == 204
    assert captured["tg_id"] == 12345


def test_request_then_verify_returns_jwt(client, monkeypatch):
    captured_code = {}
    def fake_send(token, tg_id, text):
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    client.post("/api/auth/telegram/request-code", json={"identifier": "777"}).raise_for_status()
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "777", "code": captured_code["code"],
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_verify_wrong_code_401(client, monkeypatch):
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    client.post("/api/auth/telegram/request-code", json={"identifier": "888"}).raise_for_status()
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "888", "code": "000000",
    })
    assert r.status_code == 401


def test_request_cooldown_returns_429(client, monkeypatch):
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    client.post("/api/auth/telegram/request-code", json={"identifier": "999"}).raise_for_status()
    r = client.post("/api/auth/telegram/request-code", json={"identifier": "999"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_invalid_code_format_422(client):
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "777", "code": "abc",
    })
    assert r.status_code == 422


def test_request_code_chat_not_found_returns_400(client, monkeypatch):
    """Telegram 'chat not found' must surface as HTTP 400, not 502."""
    from unittest.mock import MagicMock

    fake_response = MagicMock()
    fake_response.status_code = 400
    fake_response.text = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'

    monkeypatch.setattr(
        "services.auth_telegram.httpx.post",
        lambda *a, **kw: fake_response,
    )

    r = client.post("/api/auth/telegram/request-code", json={"identifier": "12345"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "бот" in detail.lower() or "start" in detail.lower() or "bot" in detail.lower()


def test_request_code_bot_blocked_returns_400(client, monkeypatch):
    """Telegram 'bot was blocked by the user' must also surface as HTTP 400."""
    from unittest.mock import MagicMock

    fake_response = MagicMock()
    fake_response.status_code = 403
    fake_response.text = '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'

    monkeypatch.setattr(
        "services.auth_telegram.httpx.post",
        lambda *a, **kw: fake_response,
    )

    r = client.post("/api/auth/telegram/request-code", json={"identifier": "12345"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "бот" in detail.lower() or "bot" in detail.lower()
