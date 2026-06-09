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


def test_finalize_pending_to_succeeded(tmp_db: Path):
    _make_user(42, balance=0)
    _insert_refill(user_id=42, amount=500, payment_id="pid-a", status="pending")

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 500, payment_id="pid-a", source_type="web", source_app_id=None
    )
    assert new_balance == 500
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-a",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "succeeded"
    assert bal["balance"] == 500


def test_finalize_idempotent_on_already_succeeded(tmp_db: Path):
    _make_user(42, balance=500)
    _insert_refill(user_id=42, amount=500, payment_id="pid-b", status="succeeded")

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 500, payment_id="pid-b", source_type="web", source_app_id=None
    )
    assert new_balance == 500     # баланс не вырос
    assert was_new is False        # повторная финализация не считается «новой»


def test_finalize_backfill_when_no_pending_row(tmp_db: Path):
    """Если pending row нет (backfill 7 stuck, например) — finalize должен INSERT succeeded напрямую."""
    _make_user(42, balance=0)

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 700, payment_id="pid-backfill",
        source_type="telegram", source_app_id=None,
    )
    assert new_balance == 700
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status, source_type FROM refills WHERE payment_id=?",
            ("pid-backfill",),
        ).fetchone()
    assert row["status"] == "succeeded"
    assert row["source_type"] == "telegram"


def test_finalize_legacy_no_payment_id_inserts_succeeded(tmp_db: Path):
    """Старый вызов finalize(..., payment_id=None) должен по-прежнему работать (INSERT succeeded)."""
    _make_user(42, balance=0)

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 250, payment_id=None, source_type="telegram", source_app_id=None
    )
    assert new_balance == 250
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status, payment_id FROM refills WHERE user_id=42"
        ).fetchone()
    assert row["status"] == "succeeded"
    assert row["payment_id"] is None


def test_finalize_raises_on_unexpected_status(tmp_db: Path):
    """Если строка существует в canceled/expired — finalize должен бросить ValueError, не зачислить."""
    _make_user(42, balance=0)
    _insert_refill(user_id=42, amount=500, payment_id="pid-cx", status="canceled")

    from services.refill import finalize
    with pytest.raises(ValueError, match="canceled"):
        finalize(42, 500, payment_id="pid-cx", source_type="web", source_app_id=None)

    with connect() as con:
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert bal["balance"] == 0  # не зачислили


def test_finalize_backfill_detects_existing_succeeded_and_does_not_double_credit(tmp_db: Path):
    """Если строки нет в pending, но кто-то ИНОЙ уже сделал backfill (succeeded),
    то наш finalize должен это обнаружить через IntegrityError на INSERT и не задвоить кредит.

    Это lock-in для backfill-race: A добавляет succeeded строку → B пытается backfill →
    UNIQUE INDEX отлавливает дубликат → B возвращает (текущий_balance, False) без credit."""
    _make_user(42, balance=0)
    # Эмулируем то, что A уже успел: запись succeeded существует с этим payment_id,
    # баланс уже инкрементирован (B не должен инкрементировать его повторно).
    _insert_refill(user_id=42, amount=500, payment_id="pid-raced", status="succeeded")
    with connect() as con:
        con.execute("UPDATE users SET balance=500 WHERE id=42")
        con.commit()

    # B приходит — видит, что UPDATE pending не сработал (нет pending строки),
    # SELECT находит существующий succeeded — должен no-op.
    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 500, payment_id="pid-raced", source_type="web", source_app_id=None
    )
    assert new_balance == 500     # баланс НЕ удвоился
    assert was_new is False        # не считаем это новой финализацией

    with connect() as con:
        rows = con.execute(
            "SELECT COUNT(*) c FROM refills WHERE payment_id=?", ("pid-raced",)
        ).fetchone()
    assert rows["c"] == 1          # ровно одна строка, без задвоения
