"""Тесты миграции старых статусов и данных guest_orders в новую схему."""
import sqlite3

import pytest


def _seed_orders_with_old_statuses(tmp_db_path):
    """Добавляет в existing orders записи с legacy-статусами для теста миграции."""
    with sqlite3.connect(tmp_db_path) as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name) VALUES (1, 0, 'u1', NULL)"
        )
        for inc, status in enumerate(("Posted", "Completed", "Cancelled", "Pending"), start=1):
            con.execute(
                "INSERT INTO orders(increment, user_id, price, position_name, "
                "status, links, contacts, user_name) "
                "VALUES (?, 1, ?, '1/1', ?, '[]', 0, 'u1')",
                (inc, inc * 100, status),
            )
        con.commit()


def test_status_migration_renames_legacy_statuses(tmp_db):
    _seed_orders_with_old_statuses(tmp_db)
    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()
    with sqlite3.connect(tmp_db) as con:
        statuses = {row[0] for row in con.execute("SELECT status FROM orders").fetchall()}
    assert statuses == {"paid", "done", "cancelled", "payment_failed"}


def test_guest_orders_table_dropped_after_migration(tmp_db):
    from utils.sqlite3 import create_db, apply_phase2_migrations
    create_db()
    apply_phase2_migrations()
    with sqlite3.connect(tmp_db) as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "guest_orders" not in tables


def test_guest_orders_paid_row_migrated_to_orders_with_phone_provider(tmp_db):
    """Запись guest_orders.paid → orders.paid + user с phone-provider verified=1.

    guest_orders больше не в schema, поэтому таблица создаётся вручную (имитация legacy).
    """
    from utils.sqlite3 import create_db, apply_phase2_migrations
    create_db()
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "CREATE TABLE guest_orders("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "phone TEXT NOT NULL,"
            "links TEXT NOT NULL,"
            "days INTEGER NOT NULL,"
            "fix_count INTEGER NOT NULL,"
            "contacts INTEGER NOT NULL DEFAULT 0,"
            "price INTEGER NOT NULL,"
            "price_per_unit INTEGER NOT NULL,"
            "payment_id TEXT,"
            "status TEXT NOT NULL DEFAULT 'pending_payment',"
            "created_at TEXT NOT NULL)"
        )
        con.execute(
            "INSERT INTO guest_orders(phone, links, days, fix_count, contacts, "
            "price, price_per_unit, status, created_at, payment_id) "
            "VALUES ('+79991234567', '[\"https://avito.ru/x\"]', 7, 3, 0, "
            "200, 10, 'paid', ?, 'pay_abc')",
            ("2026-06-01T10:00:00+00:00",),
        )
        con.commit()

    apply_phase2_migrations()

    with sqlite3.connect(tmp_db) as con:
        # таблицы больше нет
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "guest_orders" not in tables
        # есть order с phone, status='paid', payment_id='pay_abc'
        order = con.execute(
            "SELECT user_id, status, phone, payment_method, payment_id, price "
            "FROM orders WHERE phone='+79991234567'"
        ).fetchone()
        assert order is not None
        user_id, status, phone, method, pay_id, price = order
        assert status == "paid"
        assert phone == "+79991234567"
        assert method == "yookassa"
        assert pay_id == "pay_abc"
        assert price == 200
        # есть user с phone-provider verified=1 (status был paid)
        ap = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
        assert ap == (user_id, 1)
