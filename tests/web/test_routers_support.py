"""Tests for /api/support/messages endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("user@example.com", "password123", first_name="User")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    client = TestClient(app)
    return client, uid, {"Authorization": f"Bearer {token}"}


def test_get_messages_empty(authed):
    client, _, headers = authed
    r = client.get("/api/support/messages", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_messages_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/support/messages")
    assert r.status_code == 401


def test_send_message_success(authed, monkeypatch):
    client, _, headers = authed

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.support._forward_to_admins", _noop)

    r = client.post("/api/support/messages", headers=headers,
                    json={"text": "Hello support, I have a question"})
    assert r.status_code == 204


def test_send_message_requires_auth(authed):
    client, _, _ = authed
    r = client.post("/api/support/messages", json={"text": "hello"})
    assert r.status_code == 401


def test_send_message_empty_text_rejected(authed, monkeypatch):
    client, _, headers = authed
    r = client.post("/api/support/messages", headers=headers, json={"text": ""})
    assert r.status_code == 422


def test_messages_appear_after_send(authed, monkeypatch):
    client, uid, headers = authed

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.support._forward_to_admins", _noop)

    client.post("/api/support/messages", headers=headers, json={"text": "My question"})

    r = client.get("/api/support/messages", headers=headers)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 1
    assert msgs[0]["direction"] == "user"
    assert msgs[0]["text"] == "My question"
    assert "created_at" in msgs[0]


def test_admin_reply_visible_to_user(authed, tmp_db):
    client, uid, headers = authed
    from services.support import create_admin_reply
    create_admin_reply(uid, "Hello, this is support answering")

    r = client.get("/api/support/messages", headers=headers)
    msgs = r.json()
    assert any(m["direction"] == "admin" and "support answering" in m["text"] for m in msgs)
