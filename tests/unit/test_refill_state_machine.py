"""State machine для refills + идемпотентность finalize."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.db import connect


def _insert_refill(*, user_id: int, amount: int, payment_id: str | None,
                   status: str, date: str = "2026-06-09T12:00:00+00:00") -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, date, payment_id, "web", status),
        )
        con.commit()


def _make_user(user_id: int, *, balance: int = 0, ref_id: int | None = None,
               is_vip: int | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, ref_id, is_vip, user_name, first_name) "
            "VALUES (?, ?, ?, ?, NULL, NULL)",
            (user_id, balance, ref_id, is_vip),
        )
        con.commit()


def test_is_first_refill_ignores_pending(tmp_db: Path):
    """Юзер только с pending refill — ещё имеет право на реф-бонус."""
    _make_user(42)
    _insert_refill(user_id=42, amount=100, payment_id="pid-pending", status="pending")

    from services.refill import _is_first_refill
    assert _is_first_refill(42) is True


def test_is_first_refill_false_after_succeeded(tmp_db: Path):
    _make_user(42)
    _insert_refill(user_id=42, amount=100, payment_id="pid-ok", status="succeeded")

    from services.refill import _is_first_refill
    assert _is_first_refill(42) is False


def test_refill_result_has_was_newly_finalized(tmp_db: Path):
    """RefillResult должен иметь поле was_newly_finalized."""
    from services.refill import RefillResult
    r = RefillResult(
        user_balance=100,
        referrer_id=None,
        referrer_bonus=0,
        referrer_new_balance=None,
        was_newly_finalized=True,
    )
    assert r.was_newly_finalized is True
