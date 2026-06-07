"""Tests for legacy fallback in services/identity.get_or_create_user_by_telegram."""
import sqlite3
from pathlib import Path

import pytest

from services.identity import (
    find_user_id_by_provider,
    get_or_create_user_by_telegram,
    get_user,
)


def _count_users(tmp_db: Path) -> int:
    with sqlite3.connect(tmp_db) as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def _count_providers(tmp_db: Path, provider: str, identifier: str) -> int:
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT COUNT(*) FROM auth_providers WHERE provider=? AND identifier=?",
            (provider, identifier),
        ).fetchone()[0]


def test_legacy_user_without_provider_is_claimed(tmp_db: Path):
    """tg_id where users.id=tg_id exists without telegram-provider ->
    returns that id, creates the provider, no new user row inserted."""
    tg_id = 800001
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, 'legacy', 'L', 50, '2024-01-01')",
            (tg_id,),
        )
        con.commit()

    user_count_before = _count_users(tmp_db)
    result = get_or_create_user_by_telegram(tg_id)

    assert result == tg_id
    # No new user row was created
    assert _count_users(tmp_db) == user_count_before
    # Provider was linked
    assert find_user_id_by_provider("telegram", str(tg_id)) == tg_id


def test_new_tg_id_creates_brand_new_user(tmp_db: Path):
    """tg_id with nothing in the DB -> creates a brand new user."""
    tg_id = 800002
    user_count_before = _count_users(tmp_db)

    result = get_or_create_user_by_telegram(tg_id)

    assert result > 0
    # A new row was added
    assert _count_users(tmp_db) == user_count_before + 1
    # Provider was linked
    assert find_user_id_by_provider("telegram", str(tg_id)) == result


def test_existing_telegram_provider_returns_without_writes(tmp_db: Path):
    """tg_id with existing telegram-provider -> returns existing user_id (fast path)."""
    tg_id = 800003
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date) "
            "VALUES ('modern', 'M', 0, '2024-01-01')",
        )
        internal_id = cur.lastrowid
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2024-01-01')",
            (internal_id, str(tg_id)),
        )
        con.commit()

    user_count_before = _count_users(tmp_db)
    result = get_or_create_user_by_telegram(tg_id)

    assert result == internal_id
    # No new user was created
    assert _count_users(tmp_db) == user_count_before
    # Exactly one provider row
    assert _count_providers(tmp_db, "telegram", str(tg_id)) == 1


def test_legacy_fallback_updates_user_name(tmp_db: Path):
    """Legacy row + user_name/first_name args -> users.user_name and first_name updated."""
    tg_id = 800004
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, NULL, NULL, 0, '2024-01-01')",
            (tg_id,),
        )
        con.commit()

    result = get_or_create_user_by_telegram(
        tg_id, user_name="updated_name", first_name="Updated"
    )
    assert result == tg_id

    user = get_user(tg_id)
    assert user.user_name == "updated_name"
    assert user.first_name == "Updated"


def test_legacy_fallback_provider_linked_only_once(tmp_db: Path):
    """Calling get_or_create_user_by_telegram twice for same legacy user -> only one provider row."""
    tg_id = 800005
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, 'leg', 'L', 0, '2024-01-01')",
            (tg_id,),
        )
        con.commit()

    result1 = get_or_create_user_by_telegram(tg_id)
    result2 = get_or_create_user_by_telegram(tg_id)
    assert result1 == result2 == tg_id
    assert _count_providers(tmp_db, "telegram", str(tg_id)) == 1
