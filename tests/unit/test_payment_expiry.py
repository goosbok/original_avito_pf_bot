"""Тесты payment_expiry job."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


def _make_user(con):
    cur = con.execute("INSERT INTO users(balance, user_name, first_name) VALUES (0, NULL, NULL)")
    return cur.lastrowid


def test_expire_unpaid_marks_expired_orders_as_payment_failed(tmp_db):
    from services.payment_expiry import expire_unpaid_orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        # expired
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts, "
                    "payment_method, payment_expires_at) VALUES (?, 100, '1/1', 'unpaid', '[]', 0, 'yookassa', ?)",
                    (uid, past))
        # not yet
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts, "
                    "payment_method, payment_expires_at) VALUES (?, 100, '1/1', 'unpaid', '[]', 0, 'balance', ?)",
                    (uid, future))
        con.commit()

    expire_unpaid_orders()

    with sqlite3.connect(tmp_db) as con:
        statuses = [row[0] for row in con.execute("SELECT status FROM orders ORDER BY increment").fetchall()]
    assert statuses == ["payment_failed", "unpaid"]


def test_expire_unpaid_skips_orders_with_no_expires_at(tmp_db):
    """Заказы без payment_expires_at не трогаем."""
    from services.payment_expiry import expire_unpaid_orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts) "
                    "VALUES (?, 100, '1/1', 'unpaid', '[]', 0)", (uid,))
        con.commit()
    expire_unpaid_orders()
    with sqlite3.connect(tmp_db) as con:
        status = con.execute("SELECT status FROM orders").fetchone()[0]
    assert status == "unpaid"
