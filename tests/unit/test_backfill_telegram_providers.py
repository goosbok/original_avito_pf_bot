"""Tests for scripts/backfill_telegram_providers.py"""
import sqlite3
from pathlib import Path

import pytest

from services.identity import find_user_id_by_provider


def _seed_user_no_provider(tmp_db: Path, user_id: int) -> None:
    """Insert a legacy user (users.id == tg_id) with no auth_providers row."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, 'legacy', 'Legacy', 0, '2024-01-01')",
            (user_id,),
        )
        con.commit()


def _seed_user_with_provider(tmp_db: Path, user_id: int) -> None:
    """Insert a user who already has a telegram auth_providers row."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, 'modern', 'Modern', 0, '2024-01-01')",
            (user_id,),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2024-01-01')",
            (user_id, str(user_id)),
        )
        con.commit()


def test_single_user_without_provider_inserts_one_row(tmp_db: Path):
    """User without telegram provider -> backfill inserts one row, returns 1."""
    _seed_user_no_provider(tmp_db, 100001)
    from scripts.backfill_telegram_providers import backfill
    result = backfill()
    assert result == 1


def test_user_with_existing_provider_not_duplicated(tmp_db: Path):
    """User who already has telegram provider -> backfill returns 0."""
    _seed_user_with_provider(tmp_db, 200001)
    from scripts.backfill_telegram_providers import backfill
    result = backfill()
    assert result == 0


def test_two_users_without_providers_returns_two(tmp_db: Path):
    """Two legacy users without providers -> backfill inserts 2, returns 2."""
    _seed_user_no_provider(tmp_db, 300001)
    _seed_user_no_provider(tmp_db, 300002)
    from scripts.backfill_telegram_providers import backfill
    result = backfill()
    assert result == 2


def test_rerun_after_backfill_returns_zero(tmp_db: Path):
    """Re-running backfill after first run is idempotent — returns 0."""
    _seed_user_no_provider(tmp_db, 400001)
    from scripts.backfill_telegram_providers import backfill
    first = backfill()
    assert first == 1
    second = backfill()
    assert second == 0


def test_backfill_provider_resolves_via_find_user_id(tmp_db: Path):
    """After backfill, find_user_id_by_provider('telegram', str(uid)) returns uid."""
    uid = 500001
    _seed_user_no_provider(tmp_db, uid)
    from scripts.backfill_telegram_providers import backfill
    backfill()
    resolved = find_user_id_by_provider("telegram", str(uid))
    assert resolved == uid


def test_mixed_users_only_legacy_gets_backfilled(tmp_db: Path):
    """One user with provider, one without — only the one without gets backfilled."""
    _seed_user_with_provider(tmp_db, 600001)
    _seed_user_no_provider(tmp_db, 600002)
    from scripts.backfill_telegram_providers import backfill
    result = backfill()
    assert result == 1
    # The one with provider was not duplicated
    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM auth_providers WHERE user_id = 600001"
        ).fetchone()[0]
    assert count == 1
