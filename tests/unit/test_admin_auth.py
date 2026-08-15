"""Auth gate for /api/admin/* endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from web.admin_deps import is_admin


def _seed_user(tmp_db: Path, user_id: int, tg_provider_id: str | None = None) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, NULL, 'U', 0, '2026-01-01')",
            (user_id,),
        )
        if tg_provider_id is not None:
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                "VALUES (?, 'telegram', ?, '2026-01-01')",
                (user_id, tg_provider_id),
            )
        con.commit()


def _seed_admin(tmp_db: Path, tg_id: int) -> None:
    """Add tg_id to the legacy admin list in settings table."""
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT value FROM settings WHERE parametr = 'admins'"
        ).fetchone()
        current = row[0] if row else ""
        ids = [s for s in current.split(",") if s]
        if str(tg_id) not in ids:
            ids.append(str(tg_id))
        new_val = ",".join(ids)
        if row is None:
            con.execute(
                "INSERT INTO settings(parametr, description, value) "
                "VALUES ('admins', 'admin list', ?)",
                (new_val,),
            )
        else:
            con.execute(
                "UPDATE settings SET value = ? WHERE parametr = 'admins'",
                (new_val,),
            )
        con.commit()


def test_legacy_user_with_id_in_admins_is_admin(tmp_db: Path):
    _seed_user(tmp_db, user_id=295642149)
    _seed_admin(tmp_db, tg_id=295642149)
    assert is_admin(295642149) is True


def test_new_user_with_tg_provider_in_admins_is_admin(tmp_db: Path):
    _seed_user(tmp_db, user_id=42, tg_provider_id="295642149")
    _seed_admin(tmp_db, tg_id=295642149)
    assert is_admin(42) is True


def test_user_without_admin_tg_id_is_not_admin(tmp_db: Path):
    _seed_user(tmp_db, user_id=7, tg_provider_id="111222333")
    _seed_admin(tmp_db, tg_id=295642149)
    assert is_admin(7) is False


def test_unknown_user_is_not_admin(tmp_db: Path):
    _seed_admin(tmp_db, tg_id=295642149)
    assert is_admin(999999) is False
