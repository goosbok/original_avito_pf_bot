"""Сервис пополнения баланса.

create_invoice — создаёт счёт в Yookassa.
finalize — после подтверждения оплаты атомарно зачисляет баланс и пишет в refills.
"""
from __future__ import annotations

from services.balance import credit, get_balance
from services.db import connect
from services.exceptions import PaymentError
from utils.other import get_date
from utils.yookassa_refil import create_invoice as _yookassa_create_invoice


def create_invoice(user_id: int, amount: int) -> tuple[str, str]:
    """Возвращает (payment_url, payment_id)."""
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")
    try:
        return _yookassa_create_invoice(user_id, amount)
    except Exception as exc:
        raise PaymentError(f"yookassa create_invoice failed: {exc}") from exc


def finalize(user_id: int, amount: int, payment_id: str | None = None) -> int:
    """Атомарно зачислить amount на баланс и записать в refills.

    Если передан payment_id — операция идемпотентна: повторный вызов с тем же
    payment_id не зачисляет деньги повторно, а возвращает текущий баланс.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    if payment_id is not None:
        with connect() as con:
            existing = con.execute(
                "SELECT 1 FROM refills WHERE payment_id = ? LIMIT 1", (payment_id,)
            ).fetchone()
        if existing is not None:
            return get_balance(user_id)

    new_balance = credit(user_id, amount)
    with connect() as con:
        con.execute(
            "INSERT INTO refills(amount, date, user_id, payment_id) VALUES (?, ?, ?, ?)",
            (amount, get_date(), user_id, payment_id),
        )
        con.commit()
    return new_balance


from dataclasses import dataclass

from services.exceptions import UserNotFound


@dataclass(frozen=True)
class RefillResult:
    user_balance: int
    referrer_id: int | None
    referrer_bonus: int
    referrer_new_balance: int | None


def _is_first_refill(user_id: int) -> bool:
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    return row is None


def _get_user_for_referral(user_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT id, ref_id, is_vip FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return row


def finalize_with_referral_bonus(
    user_id: int, amount: int, payment_id: str | None = None
) -> RefillResult:
    """Atomically finalize a refill and credit a referral bonus when applicable.

    Bonus rules (preserved from handlers/user_functions.py:722-744):
    - Only on the user's FIRST refill.
    - User must not be VIP (is_vip IS NULL/falsy).
    - User must have a ref_id pointing to an existing user.
    - Bonus = int(amount * 0.3), credited and recorded in refills under referrer's id.
    """
    user = _get_user_for_referral(user_id)
    is_first = _is_first_refill(user_id)

    new_balance = finalize(user_id, amount, payment_id=payment_id)

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    if is_first and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            referrer_new_balance = finalize(int(referrer_id), bonus) if bonus > 0 else None
        except UserNotFound:
            referrer_new_balance = None
            bonus = 0

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_balance=referrer_new_balance,
    )
