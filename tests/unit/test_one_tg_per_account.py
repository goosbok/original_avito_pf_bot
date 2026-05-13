"""Invariant: one Telegram account cannot be linked to multiple ProBoost accounts.

Backstop test for the user-facing concern: if a TG identifier already belongs to
one user, attempting to link the same TG (or phone tied to that TG) to a
different web account must raise ProviderAlreadyLinked → the API surfaces 409.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services import identity
from services.exceptions import ProviderAlreadyLinked


def _seed_user(tmp_db: Path, user_id: int, first_name: str = "U") -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, NULL, ?, 0, '2026-01-01')",
            (user_id, first_name),
        )
        con.commit()


def test_telegram_cannot_link_to_two_accounts(tmp_db: Path):
    _seed_user(tmp_db, user_id=100, first_name="Alice")
    _seed_user(tmp_db, user_id=200, first_name="Bob")

    # Alice gets the Telegram first.
    identity.link_provider(100, "telegram", "123456789")

    # Bob attempts to claim the same Telegram → blocked.
    with pytest.raises(ProviderAlreadyLinked) as exc:
        identity.link_provider(200, "telegram", "123456789")
    assert exc.value.existing_user_id == 100


def test_phone_cannot_link_to_two_accounts(tmp_db: Path):
    _seed_user(tmp_db, user_id=100, first_name="Alice")
    _seed_user(tmp_db, user_id=200, first_name="Bob")

    identity.link_provider(100, "phone", "+79001234567")
    with pytest.raises(ProviderAlreadyLinked):
        identity.link_provider(200, "phone", "+79001234567")


def test_relink_same_owner_is_idempotent(tmp_db: Path):
    """Reusing /connect from the same TG should not double-insert or raise."""
    _seed_user(tmp_db, user_id=100, first_name="Alice")
    identity.link_provider(100, "phone", "+79001234567")
    # Same phone, same user → no-op (no exception, no duplicate row).
    identity.link_provider(100, "phone", "+79001234567")
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT COUNT(*) AS c FROM auth_providers "
            "WHERE provider = 'phone' AND identifier = '+79001234567'"
        ).fetchone()
    assert rows[0] == 1
