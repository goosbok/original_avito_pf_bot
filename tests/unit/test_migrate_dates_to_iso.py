"""Тесты one-shot миграции dates → ISO. Используют tmp_db фикстуру
из tests/conftest.py — пустая БД с прод-схемой."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts.migrate_dates_to_iso import TARGETS, migrate


def _insert_order(db: Path, date_value: str | None) -> int:
    with sqlite3.connect(db) as con:
        cur = con.execute(
            "INSERT INTO orders (user_id, price, position_name, status, links, date, contacts, user_name) "
            "VALUES (1, 100, '7/30', 'paid', '[]', ?, 0, 'test')",
            (date_value,),
        )
        con.commit()
        return cur.lastrowid


def _get_date(db: Path, order_id: int) -> str | None:
    with sqlite3.connect(db) as con:
        row = con.execute("SELECT date FROM orders WHERE increment = ?", (order_id,)).fetchone()
        return row[0] if row else None


def test_migrate_legacy_to_iso(tmp_db: Path):
    oid = _insert_order(tmp_db, "23.05.2026 14:30:00")
    stats = migrate(tmp_db)
    after = _get_date(tmp_db, oid)
    parsed = datetime.fromisoformat(after)
    assert parsed.tzinfo is not None
    assert parsed.hour == 11
    assert stats["orders"]["migrated"] == 1


def test_migrate_iso_unchanged(tmp_db: Path):
    iso = "2026-05-23T11:30:00+00:00"
    oid = _insert_order(tmp_db, iso)
    migrate(tmp_db)
    assert _get_date(tmp_db, oid) == iso


def test_migrate_null_unchanged(tmp_db: Path):
    oid = _insert_order(tmp_db, None)
    migrate(tmp_db)
    assert _get_date(tmp_db, oid) is None


def test_migrate_garbage_skipped(tmp_db: Path):
    oid = _insert_order(tmp_db, "not a date")
    stats = migrate(tmp_db)
    assert _get_date(tmp_db, oid) == "not a date"
    assert stats["orders"]["skipped"] == 1


def test_migrate_idempotent(tmp_db: Path):
    oid = _insert_order(tmp_db, "23.05.2026 14:30:00")
    first = migrate(tmp_db)
    second = migrate(tmp_db)
    assert second["orders"]["migrated"] == 0
    assert _get_date(tmp_db, oid) == _get_date(tmp_db, oid)


def test_migrate_missing_table_does_not_raise(tmp_db: Path):
    seo_target = ("seo", "date")
    assert seo_target in TARGETS
    migrate(tmp_db)
