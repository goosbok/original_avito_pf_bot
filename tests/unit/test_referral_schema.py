"""Схема партнерской программы: таблицы referral_links/referral_bonuses, users.ref_link_id."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _columns(tmp_db: Path, table: str) -> set[str]:
    with sqlite3.connect(tmp_db) as con:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def test_referral_links_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_links") == {
        "id", "user_id", "slug", "clicks", "custom_percent", "created_at", "archived_at",
    }


def test_referral_bonuses_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_bonuses") == {
        "id", "referrer_id", "referred_user_id", "refill_id", "link_id",
        "amount", "percent", "created_at",
    }


def test_users_has_ref_link_id(tmp_db: Path) -> None:
    assert "ref_link_id" in _columns(tmp_db, "users")


def test_slug_unique_per_user_not_globally(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO users(id, balance) VALUES (2, 0)")
        con.execute(
            "INSERT INTO referral_links(user_id, slug, created_at) VALUES (1, 'promo', '2026-07-18')"
        )
        # Другой юзер — тот же слаг: ОК
        con.execute(
            "INSERT INTO referral_links(user_id, slug, created_at) VALUES (2, 'promo', '2026-07-18')"
        )
        # Тот же юзер — тот же слаг (регистр не важен): IntegrityError
        try:
            con.execute(
                "INSERT INTO referral_links(user_id, slug, created_at) VALUES (1, 'PROMO', '2026-07-18')"
            )
            assert False, "expected IntegrityError"
        except sqlite3.IntegrityError:
            pass
