"""Admin users endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        # Two users, one admin
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date, is_vip) "
            "VALUES (1, 'admin', 'Admin', 1000, '2026-01-01', 1)"
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 250, '2026-02-01')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )
        con.commit()


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _client():
    from web.main import app
    return TestClient(app)


def test_list_users_requires_admin(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    # Non-admin gets 403
    r = c.get("/api/admin/users", headers={"Authorization": f"Bearer {_token_for(10)}"})
    assert r.status_code == 403


def test_list_users_returns_paginated(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get("/api/admin/users", headers={"Authorization": f"Bearer {_token_for(1)}"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {u["user_name"] for u in body["items"]} == {"admin", "alice"}


def test_search_users_by_name(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get(
        "/api/admin/users?q=alice",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200
    assert [u["user_name"] for u in r.json()["items"]] == ["alice"]


def test_user_detail_includes_providers_and_orders(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get(
        "/api/admin/users/10",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 10
    assert isinstance(body["providers"], list)
    assert isinstance(body["recent_orders"], list)


def test_adjust_balance_credits_user(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/users/10/balance",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"delta": 500, "reason": "manual top-up"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance_before"] == 250
    assert body["balance_after"] == 750

    with sqlite3.connect(tmp_db) as con:
        bal = con.execute("SELECT balance FROM users WHERE id=10").fetchone()[0]
        refill = con.execute(
            "SELECT amount, source_type FROM refills WHERE user_id=10 ORDER BY increment DESC LIMIT 1"
        ).fetchone()
    assert bal == 750
    assert refill[0] == 500
    assert refill[1] == "admin_manual"


def test_adjust_balance_rejects_non_positive(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/users/10/balance",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"delta": 0, "reason": "x"},
    )
    assert r.status_code == 422


def test_set_vip_toggles_flag(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/users/10/vip",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"is_vip": True},
    )
    assert r.status_code == 200
    with sqlite3.connect(tmp_db) as con:
        v = con.execute("SELECT is_vip FROM users WHERE id=10").fetchone()[0]
    assert v == 1
