"""Admin stats endpoint."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_db: Path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (1, 'admin', 'Admin', 0, ?)",
            (f"{today}T00:00:00+00:00",),
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2025-01-01T00:00:00+00:00')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )
        con.execute(
            f"INSERT INTO orders(user_id, price, position_name, status, links, date, contacts, user_name) "
            f"VALUES (10, 1260, '7/30', 'Posted', '', '{today} 10:00:00', 0, 'alice')"
        )
        con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at) "
            "VALUES (10, 'user', 'Help', '2026-05-13T10:00:00')"
        )
        con.commit()


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def test_stats_requires_admin(tmp_db: Path):
    _seed(tmp_db)
    from web.main import app
    c = TestClient(app)
    r = c.get("/api/admin/stats", headers={"Authorization": f"Bearer {_token_for(10)}"})
    assert r.status_code == 403


def test_stats_returns_today_numbers(tmp_db: Path):
    _seed(tmp_db)
    from web.main import app
    c = TestClient(app)
    r = c.get("/api/admin/stats", headers={"Authorization": f"Bearer {_token_for(1)}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["users_total"] == 2
    assert body["users_registered_today"] == 1
    assert body["orders_today"] == 1
    assert body["revenue_today"] == 1260
    assert body["open_support_threads"] == 1
