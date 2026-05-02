"""Сервис пополнения баланса.

create_invoice — создаёт счёт в Yookassa.
finalize — после подтверждения оплаты атомарно зачисляет баланс и пишет в refills.
"""
from __future__ import annotations

from services.balance import credit
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


def finalize(user_id: int, amount: int) -> int:
    """Атомарно зачислить amount на баланс и записать в refills.

    Возвращает новый баланс. Бросает UserNotFound если такого user_id нет.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    new_balance = credit(user_id, amount)
    with connect() as con:
        con.execute(
            "INSERT INTO refills(amount, date, user_id) VALUES (?, ?, ?)",
            (amount, get_date(), user_id),
        )
        con.commit()
    return new_balance
