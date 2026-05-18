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
