"""Схема реферального баланса: users.referral_balance, referral_withdrawals."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _columns(tmp_db: Path, table: str) -> set[str]:
    with sqlite3.connect(tmp_db) as con:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def test_users_has_referral_balance(tmp_db: Path) -> None:
    assert "referral_balance" in _columns(tmp_db, "users")


def test_referral_balance_defaults_to_zero(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.commit()
        row = con.execute(
            "SELECT referral_balance FROM users WHERE id = 1"
        ).fetchone()
    assert row[0] == 0


def test_referral_withdrawals_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_withdrawals") == {
        "id", "user_id", "amount", "destination", "created_at",
    }
