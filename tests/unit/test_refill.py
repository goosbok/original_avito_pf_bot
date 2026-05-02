import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize


def _make_user(tmp_db: Path, user_id: int = 1, balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, "u", "U", balance, "2026-05-02"),
        )
        con.commit()


def test_create_invoice_delegates_to_yookassa(tmp_db: Path) -> None:
    with patch(
        "services.refill._yookassa_create_invoice",
        return_value=("https://pay/xyz", "pay-id-1"),
    ) as mock:
        url, pid = create_invoice(user_id=1, amount=200)
    assert url == "https://pay/xyz"
    assert pid == "pay-id-1"
    mock.assert_called_once_with(1, 200)


def test_create_invoice_wraps_yookassa_errors(tmp_db: Path) -> None:
    with patch(
        "services.refill._yookassa_create_invoice",
        side_effect=RuntimeError("yookassa down"),
    ):
        with pytest.raises(PaymentError):
            create_invoice(user_id=1, amount=200)


def test_finalize_credits_balance_and_writes_refill(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    new_balance = finalize(user_id=1, amount=200)
    assert new_balance == 210
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, amount FROM refills WHERE user_id = 1"
        ).fetchall()
    assert rows == [(1, 200)]


def test_finalize_unknown_user_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        finalize(user_id=999, amount=100)


def test_finalize_amount_must_be_positive(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=-50)


from services.refill import finalize_with_referral_bonus


def _make_user_full(
    tmp_db: Path,
    user_id: int,
    balance: int = 0,
    ref_id: int | None = None,
    is_vip: bool = False,
) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date, ref_id, is_vip) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, f"u{user_id}", f"U{user_id}", balance, "2026-05-02",
             ref_id, 1 if is_vip else None),
        )
        con.commit()


def test_referral_bonus_first_refill_credits_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id == 1
    assert result.referrer_bonus == 300  # 30%
    assert result.referrer_new_balance == 300


def test_referral_bonus_only_first_refill(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)  # реферер +300
    result = finalize_with_referral_bonus(user_id=2, amount=2000)
    assert result.user_balance == 3000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None


def test_referral_bonus_skipped_for_vip(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1, is_vip=True)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None


def test_referral_bonus_skipped_when_no_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=None)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id is None
    assert result.referrer_bonus == 0


def test_referral_bonus_referrer_does_not_exist(tmp_db: Path) -> None:
    """ref_id указывает на несуществующего пользователя — поведение: бонус не начислен, не падаем."""
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=999)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None
