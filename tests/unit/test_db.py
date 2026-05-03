"""Smoke-тесты на тестовую инфраструктуру."""
import sqlite3
from pathlib import Path


def test_tmp_db_has_users_table(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("PRAGMA table_info(users)").fetchall()
    assert len(rows) == 10


def test_tmp_db_can_insert_user(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 0, "2026-05-02"),
        )
        con.commit()
        row = con.execute("SELECT id, balance FROM users WHERE id = 42").fetchone()
    assert row == (42, 0)


def test_tmp_db_isolated_per_test_a(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, "a", "A", 100, "2026-05-02"),
        )
        con.commit()


def test_tmp_db_isolated_per_test_b(tmp_db: Path) -> None:
    """Если первая фикстура утекла — тут будет 1 строка вместо 0."""
    with sqlite3.connect(tmp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 0
