"""Тест миграции refills.status: ALTER, индексы, дефолт для существующих."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _old_schema_create(path: Path) -> None:
    """Старая схема refills (до миграции): без колонки status."""
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "payment_id TEXT,"
            "source_type TEXT NOT NULL DEFAULT 'telegram',"
            "source_app_id INTEGER"
            ")"
        )
        # Заодно нужны users для FK + auth_providers/orders (apply_phase2_migrations их трогает).
        con.execute(
            "CREATE TABLE users(id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0,"
            " user_name TEXT, first_name TEXT, reg_date TEXT)"
        )
        con.execute(
            "CREATE TABLE orders(increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            " user_id INTEGER, price INTEGER, status TEXT)"
        )
        con.execute(
            "CREATE TABLE auth_providers(id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " user_id INTEGER, provider TEXT, identifier TEXT, created_at TEXT)"
        )
        con.execute(
            "CREATE TABLE otp_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " destination TEXT, code TEXT)"
        )
        # Засеять 3 существующие записи без status — должны получить 'succeeded'.
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id) VALUES "
            "(1, 100, '2026-05-01T10:00:00+00:00', NULL),"
            "(1, 200, '2026-05-02T10:00:00+00:00', NULL),"
            "(2, 300, '2026-05-03T10:00:00+00:00', 'pid-historical')"
        )
        con.commit()


def test_migration_adds_status_with_succeeded_default(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()

    with sqlite3.connect(db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(refills)").fetchall()}
        assert "status" in cols, "колонка status должна появиться"
        rows = con.execute("SELECT status FROM refills ORDER BY increment").fetchall()
        assert [r[0] for r in rows] == ["succeeded", "succeeded", "succeeded"], (
            "существующие записи получают status='succeeded' через DEFAULT"
        )


def test_migration_creates_indexes(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()

    with sqlite3.connect(db) as con:
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
    assert "idx_refills_status_date" in idx
    assert "uq_refills_payment_id" in idx


def test_migration_is_idempotent(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()
    apply_phase2_migrations()  # повторный запуск не должен падать

    with sqlite3.connect(db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(refills)").fetchall()}
        assert "status" in cols
