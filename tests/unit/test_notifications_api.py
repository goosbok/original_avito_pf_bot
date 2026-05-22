"""Notifications HTTP API."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (20, 'bob', 'Bob', 0, '2026-01-02')"
        )
        con.commit()


def _seed_notif(tmp_db: Path, **kwargs):
    defaults = {
        "user_id": 10, "kind": "order", "order_id": 1,
        "new_status": "Completed", "text": "test", "read_at": None,
    }
    defaults.update(kwargs)
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text, read_at) "
            "VALUES (:user_id, :kind, :order_id, :new_status, :text, :read_at)",
            defaults,
        )
        con.commit()
        return cur.lastrowid


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _client():
    from web.main import app
    return TestClient(app)


def test_list_notifications_unauthorized(tmp_db):
    _seed(tmp_db)
    r = _client().get("/api/notifications")
    assert r.status_code == 401


def test_list_notifications_returns_user_records_only(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10, text="alice-1")
    _seed_notif(tmp_db, user_id=20, text="bob-1")
    _seed_notif(tmp_db, user_id=10, text="alice-2")

    r = _client().get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    assert r.status_code == 200
    body = r.json()
    texts = [i["text"] for i in body["items"]]
    assert texts == ["alice-2", "alice-1"]  # newest first
    assert body["unread_count"] == 2


def test_list_notifications_unread_count_excludes_read(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10, text="unread")
    _seed_notif(tmp_db, user_id=10, text="read", read_at="2026-05-22 10:00:00")

    r = _client().get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    body = r.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 2


def test_mark_all_read_marks_only_caller(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10)
    _seed_notif(tmp_db, user_id=10)
    _seed_notif(tmp_db, user_id=20)

    r = _client().post(
        "/api/notifications/mark-all-read",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    assert r.status_code == 200
    assert r.json() == {"marked": 2}

    # bob's record untouched
    with sqlite3.connect(tmp_db) as con:
        bob_unread = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = 20 AND read_at IS NULL"
        ).fetchone()[0]
    assert bob_unread == 1


def test_mark_all_read_idempotent(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10)

    headers = {"Authorization": f"Bearer {_token_for(10)}"}
    assert _client().post("/api/notifications/mark-all-read", headers=headers).json() == {"marked": 1}
    assert _client().post("/api/notifications/mark-all-read", headers=headers).json() == {"marked": 0}


def test_mark_all_read_unauthorized(tmp_db):
    _seed(tmp_db)
    r = _client().post("/api/notifications/mark-all-read")
    assert r.status_code == 401
