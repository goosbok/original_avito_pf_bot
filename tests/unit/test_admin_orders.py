"""Admin orders endpoints."""
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
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )
        con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (10, 1260, '7/30', 'Posted', '[\"https://www.avito.ru/foo\"]', '2026-05-11', 0, 'alice')"
        )
        con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (10, 500, '7/15', 'Completed', '', '2026-05-12', 1, 'alice')"
        )
        con.commit()


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _client():
    from web.main import app
    return TestClient(app)


def test_list_orders_requires_admin(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get("/api/admin/orders", headers={"Authorization": f"Bearer {_token_for(10)}"})
    assert r.status_code == 403


def test_list_orders_returns_all(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get("/api/admin/orders", headers={"Authorization": f"Bearer {_token_for(1)}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert {o["status"] for o in body["items"]} == {"Posted", "Completed"}


def test_list_orders_filtered_by_status(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.get(
        "/api/admin/orders?status=Posted",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200
    assert {o["status"] for o in r.json()["items"]} == {"Posted"}


def test_change_order_status(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/orders/1/status",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"status": "Completed"},
    )
    assert r.status_code == 200, r.text
    with sqlite3.connect(tmp_db) as con:
        s = con.execute("SELECT status FROM orders WHERE increment=1").fetchone()[0]
    assert s == "Completed"


def test_change_order_status_rejects_unknown(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/orders/1/status",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"status": "Frobnicated"},
    )
    assert r.status_code == 422


def test_change_order_status_404_when_missing(tmp_db: Path):
    _seed(tmp_db)
    c = _client()
    r = c.post(
        "/api/admin/orders/9999/status",
        headers={"Authorization": f"Bearer {_token_for(1)}"},
        json={"status": "Completed"},
    )
    assert r.status_code == 404
