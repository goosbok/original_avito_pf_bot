import sqlite3
from pathlib import Path
import pytest


def test_pending_email_links_table_exists(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_email_links'"
        ).fetchone()
        assert row is not None


def test_password_reset_tokens_table_exists(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset_tokens'"
        ).fetchone()
        assert row is not None


def test_pending_email_links_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pending_email_links)").fetchall()}
    assert cols == {"email", "user_id", "password_hash", "code", "expires_at", "created_at"}


def test_password_reset_tokens_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(password_reset_tokens)").fetchall()}
    assert cols == {"token_hash", "email", "expires_at", "used_at", "created_at"}


def test_notifications_table_in_schema(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(notifications)")}
    assert cols == {
        "id", "user_id", "kind", "order_id", "new_status",
        "text", "created_at", "read_at",
    }


def test_notifications_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notifications'"
        )}
    assert "idx_notifications_user_unread" in idx
    assert "idx_notifications_user_created" in idx
