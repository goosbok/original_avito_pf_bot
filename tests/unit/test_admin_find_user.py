"""Tests for find_user() in handlers.admin_base."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        # Legacy user: id == tg_id (old schema style)
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (111, 'legacy_user', 'Лёша', 0, '2026-01-01')"
        )
        # New user: id is a large random number, tg_id in auth_providers
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (8794553795, '', 'Андрей', 0, '2026-07-01')"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, verified, created_at) "
            "VALUES (8794553795, 'telegram', '385609378', 1, '2026-07-01T00:00:00')"
        )
        # Another user found only by username
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (222, 'alice', 'Alice', 0, '2026-03-01')"
        )
        con.execute("INSERT INTO settings(parametr, description, value) VALUES ('admins','admins','1')")
        con.commit()


@pytest.mark.asyncio
async def test_find_by_system_id_returns_list(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("111")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == 111


@pytest.mark.asyncio
async def test_find_by_tg_id_returns_user(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("385609378")
    assert len(result) == 1
    assert result[0]["id"] == 8794553795


@pytest.mark.asyncio
async def test_find_by_username_without_at(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("alice")
    assert len(result) == 1
    assert result[0]["user_name"] == "alice"


@pytest.mark.asyncio
async def test_find_by_username_with_at(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("@alice")
    assert len(result) == 1
    assert result[0]["user_name"] == "alice"


@pytest.mark.asyncio
async def test_not_found_returns_empty_list(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("999999")
    assert result == []


@pytest.mark.asyncio
async def test_dedup_when_id_equals_tg_id(tmp_db: Path):
    """Legacy user whose users.id == their TG ID → found by both paths → dedup to 1."""
    _seed(tmp_db)
    # Give legacy user a matching auth_providers entry
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, verified, created_at) "
            "VALUES (111, 'telegram', '111', 1, '2026-01-01T00:00:00')"
        )
        con.commit()
    from handlers.admin_base import find_user
    result = await find_user("111")
    assert len(result) == 1
    assert result[0]["id"] == 111
