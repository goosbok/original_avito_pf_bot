"""Tests for scripts/merge_duplicate_tg_users.py"""
import sqlite3
from pathlib import Path

import pytest

from utils.dates import now_iso


def _seed_legacy_user(tmp_db: Path, tg_id: int, balance: int = 0,
                      user_name: str | None = None,
                      first_name: str | None = None) -> int:
    """Seed a legacy user (users.id == tg_id, no auth_providers)."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, '2024-01-01')",
            (tg_id, user_name, first_name, balance),
        )
        con.commit()
    return tg_id


def _seed_duplicate_user(tmp_db: Path, tg_id: int, balance: int = 0,
                         user_name: str | None = None,
                         first_name: str | None = None,
                         extra_provider: tuple | None = None) -> int:
    """Seed a duplicate user (auto-increment id) with telegram provider pointing to tg_id."""
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, '2025-01-01')",
            (user_name, first_name, balance),
        )
        dup_id = cur.lastrowid
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2025-01-01')",
            (dup_id, str(tg_id)),
        )
        if extra_provider:
            provider, identifier = extra_provider
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                "VALUES (?, ?, ?, '2025-01-01')",
                (dup_id, provider, identifier),
            )
        con.commit()
    return dup_id


def _seed_order(tmp_db: Path, user_id: int) -> int:
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (?, 100, '3/100', 'paid', ?)",
            (user_id, now_iso()),
        )
        con.commit()
        return cur.lastrowid


def _get_order_user_id(tmp_db: Path, user_id_original: int) -> int | None:
    """Return user_id of the first order that was for the given user (by position_name scan)."""
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id FROM orders WHERE position_name='3/100' LIMIT 1"
        ).fetchone()
    return int(row[0]) if row else None


def _seed_refill(tmp_db: Path, user_id: int) -> int:
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO refills(user_id, amount, date) "
            "VALUES (?, 500, ?)",
            (user_id, now_iso()),
        )
        con.commit()
        return cur.lastrowid


def test_no_pairs_returns_zero(tmp_db: Path):
    """No duplicate pairs in DB -> merge_duplicates returns 0."""
    from scripts.merge_duplicate_tg_users import merge_duplicates
    result = merge_duplicates()
    assert result == 0


def test_merge_orders_and_balance(tmp_db: Path):
    """Duplicate's orders and balance land on legacy; duplicate row removed."""
    tg_id = 700001
    legacy_id = _seed_legacy_user(tmp_db, tg_id, balance=100)
    dup_id = _seed_duplicate_user(tmp_db, tg_id, balance=50)
    _seed_order(tmp_db, dup_id)

    from scripts.merge_duplicate_tg_users import merge_duplicates
    merged = merge_duplicates()
    assert merged == 1

    with sqlite3.connect(tmp_db) as con:
        # Duplicate user should be gone
        dup_row = con.execute("SELECT id FROM users WHERE id = ?", (dup_id,)).fetchone()
        assert dup_row is None

        # Legacy balance should be 150 (100 + 50)
        legacy_row = con.execute(
            "SELECT balance FROM users WHERE id = ?", (legacy_id,)
        ).fetchone()
        assert int(legacy_row[0]) == 150

        # Order should now belong to legacy
        order_row = con.execute(
            "SELECT user_id FROM orders WHERE position_name='3/100' LIMIT 1"
        ).fetchone()
        assert int(order_row[0]) == legacy_id

        # Telegram provider should point to legacy now
        ap_row = con.execute(
            "SELECT user_id FROM auth_providers WHERE provider='telegram' AND identifier=?",
            (str(tg_id),),
        ).fetchone()
        assert int(ap_row[0]) == legacy_id


def test_merge_refills_reparented(tmp_db: Path):
    """Duplicate's refills are reparented to legacy."""
    tg_id = 700002
    legacy_id = _seed_legacy_user(tmp_db, tg_id)
    dup_id = _seed_duplicate_user(tmp_db, tg_id)
    refill_increment = _seed_refill(tmp_db, dup_id)

    from scripts.merge_duplicate_tg_users import merge_duplicates
    merge_duplicates()

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id FROM refills WHERE increment = ?", (refill_increment,)
        ).fetchone()
        assert int(row[0]) == legacy_id


def test_provider_conflict_legacy_wins_on_integrity_error(tmp_db: Path):
    """_merge_one handles UNIQUE IntegrityError by deleting the conflicting duplicate
    provider row (legacy already owns same (provider, identifier)).

    Scenario: legacy already owns (telegram, str(tg_id)) via a prior backfill.
    Duplicate owns the SAME (telegram, str(tg_id)). That's impossible in real DB due
    to UNIQUE, so we test via _merge_one with a different provider pair that triggers
    the same code path: both legacy and duplicate own (phone, same_phone).
    We seed this by inserting the duplicate's phone row WITH UNIQUE disabled (INSERT
    OR REPLACE bypasses the insert but not an existing row).

    Instead, we use a simpler approach: seed the DB with PRAGMA unique_check=0 and
    raw SQL to bypass the unique constraint — but that's not supported.

    Actually the cleanest approach: seed legacy with phone provider, seed duplicate
    with a DIFFERENT phone. After merge, phone transfers to legacy normally. Then
    test the IntegrityError path via _merge_one directly by pre-inserting duplicate's
    row that would conflict, using the sqlite3 without_rowid or direct INSERT after
    disabling triggers — but UNIQUE is not a trigger.

    Since we cannot bypass UNIQUE via normal sqlite3, we instead verify the try/except
    branch is reachable by unit-testing _merge_one with a mocked connection.
    """
    import unittest.mock as mock
    from scripts.merge_duplicate_tg_users import _merge_one

    # Build a fake connection that raises IntegrityError on UPDATE auth_providers
    call_log = []

    class FakeCursor:
        def __init__(self, rows=None):
            self._rows = rows or []
        def fetchone(self):
            return self._rows[0] if self._rows else None
        def fetchall(self):
            return self._rows

    fake_dup_row = {"balance": 0, "referral_balance": 0, "user_name": None, "first_name": None}
    fake_ap_rows = [{"id": 99, "provider": "telegram", "identifier": "700003"}]

    execute_call_count = [0]

    def fake_execute(sql, params=()):
        call_log.append(sql)
        execute_call_count[0] += 1
        if "SELECT balance" in sql:
            return FakeCursor([fake_dup_row])
        if "SELECT id, provider" in sql:
            return FakeCursor(fake_ap_rows)
        if "UPDATE auth_providers SET user_id" in sql:
            raise sqlite3.IntegrityError("UNIQUE constraint failed")
        return FakeCursor()

    fake_con = mock.MagicMock()
    fake_con.execute.side_effect = fake_execute

    # Should not raise — IntegrityError is caught and delete is called
    _merge_one(fake_con, legacy_id=700003, duplicate_id=9999)

    # Verify DELETE was called for the conflicting provider row
    executed_sqls = [c[0][0] for c in fake_con.execute.call_args_list]
    delete_calls = [s for s in executed_sqls if "DELETE FROM auth_providers" in s]
    assert len(delete_calls) == 1, f"Expected one DELETE for conflicting provider, got: {executed_sqls}"


def test_legacy_gets_user_name_from_duplicate_when_empty(tmp_db: Path):
    """Legacy has no user_name, duplicate has user_name -> legacy gets it (COALESCE)."""
    tg_id = 700004
    legacy_id = _seed_legacy_user(tmp_db, tg_id, user_name=None)
    _seed_duplicate_user(tmp_db, tg_id, user_name="newname")

    from scripts.merge_duplicate_tg_users import merge_duplicates
    merge_duplicates()

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_name FROM users WHERE id = ?", (legacy_id,)
        ).fetchone()
    assert row[0] == "newname"


def test_legacy_keeps_own_user_name_when_already_set(tmp_db: Path):
    """Legacy already has user_name, duplicate also has user_name -> legacy keeps own."""
    tg_id = 700005
    legacy_id = _seed_legacy_user(tmp_db, tg_id, user_name="original")
    _seed_duplicate_user(tmp_db, tg_id, user_name="shouldnotwin")

    from scripts.merge_duplicate_tg_users import merge_duplicates
    merge_duplicates()

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_name FROM users WHERE id = ?", (legacy_id,)
        ).fetchone()
    assert row[0] == "original"


def test_rerun_after_merge_returns_zero(tmp_db: Path):
    """Re-running merge after all pairs are merged is idempotent — returns 0."""
    tg_id = 700006
    _seed_legacy_user(tmp_db, tg_id)
    _seed_duplicate_user(tmp_db, tg_id)

    from scripts.merge_duplicate_tg_users import merge_duplicates
    first = merge_duplicates()
    assert first == 1

    second = merge_duplicates()
    assert second == 0


def test_merge_referral_balance_and_withdrawals(tmp_db: Path):
    """Duplicate's referral_balance lands on legacy; referral_withdrawals rows
    repoint to legacy — no FOREIGN KEY crash on the merge DELETE."""
    tg_id = 700002
    legacy_id = _seed_legacy_user(tmp_db, tg_id, balance=0)
    dup_id = _seed_duplicate_user(tmp_db, tg_id, balance=0)
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE users SET referral_balance = 500 WHERE id = ?", (dup_id,))
        con.execute(
            "INSERT INTO referral_withdrawals(user_id, amount, destination, created_at) "
            "VALUES (?, 200, 'main_balance', '2026-07-18')",
            (dup_id,),
        )
        con.commit()

    from scripts.merge_duplicate_tg_users import merge_duplicates
    merged = merge_duplicates()
    assert merged == 1

    with sqlite3.connect(tmp_db) as con:
        legacy_row = con.execute(
            "SELECT referral_balance FROM users WHERE id = ?", (legacy_id,)
        ).fetchone()
        assert int(legacy_row[0]) == 500
        withdrawal_row = con.execute("SELECT user_id FROM referral_withdrawals").fetchone()
        assert int(withdrawal_row[0]) == legacy_id
