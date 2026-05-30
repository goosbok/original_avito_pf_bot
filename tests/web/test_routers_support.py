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


def test_forward_to_admins_sends_to_group(monkeypatch, tmp_db):
    import asyncio
    import sqlite3
    from unittest.mock import AsyncMock, MagicMock

    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text, created_at) "
            "VALUES (5, 10, 'user', 'Help', '2026-01-01 12:00:00')"
        )
        con.commit()

    sent_mock = MagicMock()
    sent_mock.message_id = 99
    mock_send = AsyncMock(return_value=sent_mock)

    # Patch config — both chat id and the questions thread id (non-zero so
    # send_admins actually delivers and returns the Message)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 7)

    # Patch identity.get_user
    mock_user = MagicMock()
    mock_user.user_name = "alice"
    monkeypatch.setattr("services.identity.get_user", lambda uid: mock_user)

    # Patch db_connect
    import contextlib
    @contextlib.contextmanager
    def mock_db_connect():
        yield sqlite3.connect(tmp_db)
    monkeypatch.setattr("services.db.connect", mock_db_connect)

    # Patch bot.send_message — send_admins imports `bot` from data.loader,
    # so patch it on that module.
    import data.loader
    mock_bot = MagicMock()
    mock_bot.send_message = mock_send
    monkeypatch.setattr(data.loader, "bot", mock_bot)
    # utils.sender did `from data.loader import bot`, so patch the bound name there too.
    import utils.sender
    monkeypatch.setattr(utils.sender, "bot", mock_bot)

    from web.routers.support import _forward_to_admins
    asyncio.run(_forward_to_admins(10, 5, "Help"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["chat_id"] == -100500
    assert mock_send.call_args.kwargs["message_thread_id"] == 7

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT tg_message_id FROM support_messages WHERE id = 5"
        ).fetchone()
    assert row[0] == 99
