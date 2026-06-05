"""E2E регрессия после фикса формата дат: убеждаемся, что заказ,
созданный сегодня через add_order(), попадает в orders_today и
revenue_today, и что гостевые тоже учитываются."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _setup_admin_user(tmp_db: Path):
    """Setup admin user in the test database."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users (id, user_name, first_name, balance, reg_date) "
            "VALUES (1, 'admin', 'Admin', 1000, ?)",
            (f"{today}T10:00:00+00:00",),
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )
        con.commit()


def test_admin_stats_counts_today_order(tmp_db: Path):
    """Заказ созданный сегодня должен попадать в orders_today и revenue_today."""
    _setup_admin_user(tmp_db)
    from utils.sqlite3 import add_order

    add_order(
        user_id=1, price=500, position_name="7/30", status="paid",
        links="[]", contacts=False, user_name="admin",
    )

    from web.main import app
    client = TestClient(app)
    r = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {_token_for(1)}"})
    assert r.status_code == 200
    data = r.json()
    assert data["orders_today"] >= 1
    assert data["revenue_today"] >= 500


def test_admin_stats_counts_today_guest_order(tmp_db: Path):
    """Гостевой заказ со статусом 'paid' должен учитываться в revenue_today.

    После Task 2 миграции guest_orders больше нет — гости пишутся прямо
    в orders с payment_method='yookassa' и phone=<E.164>. Сидим именно так.
    """
    _setup_admin_user(tmp_db)

    today_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO orders "
            "(user_id, price, position_name, status, links, date, contacts, "
            "user_name, payment_method, phone) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1, 500, "7/30", "paid",
                '["https://www.avito.ru/item/123"]', today_iso, 0,
                "guest", "yookassa", "+79991234567",
            ),
        )
        con.commit()

    from web.main import app
    client = TestClient(app)
    r = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {_token_for(1)}"})
    assert r.status_code == 200
    data = r.json()
    assert data["orders_today"] >= 1
    assert data["revenue_today"] >= 500
