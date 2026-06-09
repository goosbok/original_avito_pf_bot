"""Тесты reconcile_pending — поведение крона при разных ответах YK."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.db import connect


def _make_user(uid: int, balance: int = 0):
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (?, ?, NULL, 'X', '2026-06-09')",
            (uid, balance),
        )
        con.commit()


def _insert_pending(uid: int, amount: int, pid: str,
                    date: str = None, source_type: str = "web"):
    if date is None:
        date = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (uid, amount, date, pid, source_type),
        )
        con.commit()


def _yk_payment(status: str, amount: int = 500, pid: str = "pid"):
    """Имитируем yookassa.domain.response.payment_response.PaymentResponse."""
    return SimpleNamespace(
        id=pid,
        status=status,
        amount=SimpleNamespace(value=f"{amount}.00", currency="RUB"),
        description=f"Пполнение баланса {pid}",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.asyncio
async def test_reconcile_succeeded_finalizes_and_notifies(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-ok")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("succeeded", 500, "pid-ok")), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock) as nu, \
         patch("services.payment_reconciler.notify_admins_success", new_callable=AsyncMock) as na:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-ok",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "succeeded"
    assert bal["balance"] == 500
    nu.assert_called_once()
    na.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_canceled_updates_status_no_credit(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-cx")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("canceled", 500, "pid-cx")), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock) as nu:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-cx",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "canceled"
    assert bal["balance"] == 0  # not credited
    nu.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_waiting_for_capture_calls_capture(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-wc")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("waiting_for_capture", 500, "pid-wc")), \
         patch("yookassa.Payment.capture") as cap:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    cap.assert_called_once_with("pid-wc")
    # status в БД ОСТАЁТСЯ pending (следующий тик увидит succeeded)
    with connect() as con:
        row = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-wc",)).fetchone()
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_yk_exception_continues_to_next(tmp_db: Path):
    """Исключение на одном платеже не должно ломать обработку остальных."""
    _make_user(1); _make_user(2)
    _insert_pending(1, 100, "pid-fail")
    _insert_pending(2, 200, "pid-ok")

    def find_one_side(pid):
        if pid == "pid-fail":
            raise RuntimeError("YK timeout")
        return _yk_payment("succeeded", 200, "pid-ok")

    with patch("yookassa.Payment.find_one", side_effect=find_one_side), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock), \
         patch("services.payment_reconciler.notify_admins_success", new_callable=AsyncMock):
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()  # не падает

    with connect() as con:
        ok = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-ok",)).fetchone()
        fail = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-fail",)).fetchone()
        bal2 = con.execute("SELECT balance FROM users WHERE id=2").fetchone()
    assert ok["status"] == "succeeded"
    assert fail["status"] == "pending"  # осталось pending, попробуем в следующий тик
    assert bal2["balance"] == 200


@pytest.mark.asyncio
async def test_reconcile_skips_pending_older_than_24h(tmp_db: Path):
    _make_user(42)
    old_date = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    _insert_pending(42, 500, "pid-old", date=old_date)

    with patch("yookassa.Payment.find_one") as find_one:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    find_one.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_empty_pending_set_is_noop(tmp_db: Path):
    with patch("yookassa.Payment.find_one") as find_one:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()
    find_one.assert_not_called()
