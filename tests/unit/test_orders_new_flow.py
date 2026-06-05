"""Тесты нового unpaid → paid flow заказов (services/orders.py)."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _make_user(con, balance=0):
    cur = con.execute(
        "INSERT INTO users(balance, user_name, first_name, reg_date) "
        "VALUES (?, NULL, NULL, '2026-01-01T00:00:00+00:00')",
        (balance,),
    )
    return cur.lastrowid


# --- create_unpaid ---


def test_create_unpaid_inserts_row_with_status_unpaid(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()

    order_id = orders.create_unpaid(
        user_id=uid, links=["https://avito.ru/x"], days=1, fix_count=1,
        contacts=False, phone=None,
    )

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT status, payment_method, payment_id, price, phone "
            "FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
    assert row[0] == "unpaid"
    assert row[1] is None  # ещё не выбран
    assert row[2] is None
    assert row[3] > 0
    assert row[4] is None


def test_create_unpaid_with_phone_for_guest(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    order_id = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1,
        contacts=False, phone="+79991234567",
    )
    with sqlite3.connect(tmp_db) as con:
        phone = con.execute(
            "SELECT phone FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]
    assert phone == "+79991234567"


def test_create_unpaid_sets_expiry_in_the_future(tmp_db: Path):
    """payment_expires_at должен быть выставлен на TTL_NO_METHOD_MINUTES вперёд."""
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    order_id = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    with sqlite3.connect(tmp_db) as con:
        expires_at = con.execute(
            "SELECT payment_expires_at FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]
    expires = datetime.fromisoformat(expires_at)
    delta_min = (expires - datetime.now(timezone.utc)).total_seconds() / 60
    assert 0 < delta_min <= orders.TTL_NO_METHOD_MINUTES


# --- pay_with_balance ---


def test_pay_with_balance_success_marks_paid_and_decrements_balance(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=1000)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.pay_with_balance(order_id=oid, user_id=uid)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT status, payment_method FROM orders WHERE increment=?", (oid,)
        ).fetchone()
        balance = con.execute(
            "SELECT balance FROM users WHERE id=?", (uid,)
        ).fetchone()[0]
    assert row == ("paid", "balance")
    # default price_per_unit = 6 (seeded в create_db); 6 * 1 fix * 1 day * 1 link = 6
    assert balance == 994


def test_pay_with_balance_insufficient_raises(tmp_db: Path):
    from services import orders
    from services.exceptions import InsufficientBalance
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=0)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    with pytest.raises(InsufficientBalance):
        orders.pay_with_balance(order_id=oid, user_id=uid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute(
            "SELECT status FROM orders WHERE increment=?", (oid,)
        ).fetchone()[0]
    assert status == "unpaid"  # не изменился


def test_pay_with_balance_on_already_paid_raises_status_conflict(tmp_db: Path):
    from services import orders
    from services.exceptions import OrderStatusConflict
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=10)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.pay_with_balance(order_id=oid, user_id=uid)
    with pytest.raises(OrderStatusConflict):
        orders.pay_with_balance(order_id=oid, user_id=uid)


def test_pay_with_balance_order_not_found_raises(tmp_db: Path):
    from services import orders
    from services.exceptions import OrderNotFound
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    with pytest.raises(OrderNotFound):
        orders.pay_with_balance(order_id=9999, user_id=uid)


def test_pay_with_balance_other_users_order_raises_not_found(tmp_db: Path):
    """Атаки: юзер не может оплатить чужой order. Возвращаем OrderNotFound
    (а не Forbidden) — не сливаем факт существования заказа."""
    from services import orders
    from services.exceptions import OrderNotFound
    with sqlite3.connect(tmp_db) as con:
        owner = _make_user(con, balance=100)
        attacker = _make_user(con, balance=100)
        con.commit()
    oid = orders.create_unpaid(
        user_id=owner, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    with pytest.raises(OrderNotFound):
        orders.pay_with_balance(order_id=oid, user_id=attacker)


# --- mark_paid (idempotent webhook) ---


def test_mark_paid_transitions_unpaid_to_paid(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.mark_paid(oid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute(
            "SELECT status FROM orders WHERE increment=?", (oid,)
        ).fetchone()[0]
    assert status == "paid"


def test_mark_paid_is_idempotent_on_already_paid(tmp_db: Path):
    """Дубликат webhook от YooKassa не должен ломать ничего."""
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=10)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.pay_with_balance(order_id=oid, user_id=uid)
    # webhook прилетает после балансной оплаты — должно быть no-op
    orders.mark_paid(oid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute(
            "SELECT status FROM orders WHERE increment=?", (oid,)
        ).fetchone()[0]
    assert status == "paid"


# --- mark_payment_failed ---


def test_mark_payment_failed_sets_status(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.mark_payment_failed(oid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute(
            "SELECT status FROM orders WHERE increment=?", (oid,)
        ).fetchone()[0]
    assert status == "payment_failed"


def test_mark_payment_failed_no_op_on_already_paid(tmp_db: Path):
    """expiry-job не должен сломать уже-оплаченный заказ если webhook гонится с expiry."""
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=10)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    orders.pay_with_balance(order_id=oid, user_id=uid)
    orders.mark_payment_failed(oid)  # no-op, потому что статус paid, не unpaid
    with sqlite3.connect(tmp_db) as con:
        status = con.execute(
            "SELECT status FROM orders WHERE increment=?", (oid,)
        ).fetchone()[0]
    assert status == "paid"


# --- get_order ---


def test_get_order_returns_dict(tmp_db: Path):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    oid = orders.create_unpaid(
        user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None,
    )
    order = orders.get_order(oid)
    assert order["status"] == "unpaid"
    assert order["user_id"] == uid


def test_get_order_raises_not_found(tmp_db: Path):
    from services import orders
    from services.exceptions import OrderNotFound
    with pytest.raises(OrderNotFound):
        orders.get_order(9999)
