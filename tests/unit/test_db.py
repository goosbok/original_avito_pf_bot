"""Smoke-тесты на тестовую инфраструктуру."""
import sqlite3
from pathlib import Path


def test_tmp_db_has_users_table(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("PRAGMA table_info(users)").fetchall()
    assert len(rows) == 12


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


def test_connect_enables_wal_mode(tmp_db: Path) -> None:
    """services.db.connect() должен включать WAL для concurrent access."""
    from services.db import connect
    with connect() as con:
        mode = con.execute("PRAGMA journal_mode").fetchone()
    val = mode["journal_mode"] if hasattr(mode, "keys") else mode[0]
    assert val.lower() == "wal"


def test_connect_sets_busy_timeout(tmp_db: Path) -> None:
    """busy_timeout должен быть >0 чтобы не падать сразу на locked."""
    from services.db import connect
    with connect() as con:
        row = con.execute("PRAGMA busy_timeout").fetchone()
    val = row["timeout"] if hasattr(row, "keys") else row[0]
    assert val >= 1000  # хотя бы 1s


def test_connect_enables_foreign_keys(tmp_db: Path) -> None:
    """foreign_keys должен быть ON чтобы FOREIGN KEY на order_links работал."""
    from services.db import connect
    with connect() as con:
        row = con.execute("PRAGMA foreign_keys").fetchone()
    val = row["foreign_keys"] if hasattr(row, "keys") else row[0]
    assert val == 1
