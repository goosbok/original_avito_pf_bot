"""Admin support endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (1, 'admin', 'Admin', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-02-01')"
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (11, 'bob', 'Bob', 0, '2026-02-02')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )
        # Alice asked, no admin reply yet → unanswered
        con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at) "
            "VALUES (10, 'user', 'Help!', '2026-05-13T10:00:00')"
        )
        # Bob: user asked, admin replied → answered
        con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at) "
            "VALUES (11, 'user', 'Hi', '2026-05-13T09:00:00')"
        )
        con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at) "
            "VALUES (11, 'admin', 'Hi back', '2026-05-13T09:05:00')"
        )
        con.commit()


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _client():
    from web.main import app
    return TestClient(app)


def test_threads_requires_admin(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get("/api/admin/support/threads", headers={"Authorization": f"Bearer {_token_for(10)}"})
    assert r.status_code == 403


def test_threads_lists_users_with_messages(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get(
        "/api/admin/support/threads",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200, r.text
    threads = r.json()["threads"]
    assert {t["user_id"] for t in threads} == {10, 11}
    alice = next(t for t in threads if t["user_id"] == 10)
    bob = next(t for t in threads if t["user_id"] == 11)
    assert alice["has_unanswered"] is True
    assert bob["has_unanswered"] is False
    # Most recent first: alice (10:00) before bob (09:05)
    assert threads[0]["user_id"] == 10


def test_get_thread_returns_full_history(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get(
        "/api/admin/support/threads/11",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 2
    assert [m["direction"] for m in msgs] == ["user", "admin"]


def test_reply_inserts_admin_message(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/support/threads/10/reply",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"text": "On it."},
    )
    assert r.status_code == 200, r.text
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT direction, text FROM support_messages WHERE user_id = 10 ORDER BY id"
        ).fetchall()
    assert rows[-1] == ("admin", "On it.")


def test_reply_404_when_no_thread(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/support/threads/9999/reply",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"text": "..."},
    )
    assert r.status_code == 404
