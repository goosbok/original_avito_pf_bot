"""Сервис для работы с балансом пользователя.

Все операции атомарны на уровне SQLite через UPDATE ... RETURNING.
Не делайте read-modify-write поверх get_balance() — используйте credit/debit.
"""
from __future__ import annotations

from services.db import connect
from services.exceptions import InsufficientBalance, UserNotFound


def get_balance(user_id: int) -> int:
    with connect() as con:
        row = con.execute(
            "SELECT balance FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return int(row["balance"] or 0)


def credit(user_id: int, amount: int) -> int:
    """Атомарно увеличить баланс. Возвращает новый баланс."""
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount}")
    if amount == 0:
        return get_balance(user_id)

    with connect() as con:
        cur = con.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? "
            "WHERE id = ? RETURNING balance",
            (amount, user_id),
        )
        row = cur.fetchone()
        con.commit()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return int(row["balance"])


def debit(user_id: int, amount: int) -> int:
    """Атомарно списать сумму. Бросает InsufficientBalance если средств не хватает."""
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount}")
    if amount == 0:
        return get_balance(user_id)

    with connect() as con:
        cur = con.execute(
            "UPDATE users SET balance = balance - ? "
            "WHERE id = ? AND balance >= ? RETURNING balance",
            (amount, user_id, amount),
        )
        row = cur.fetchone()
        con.commit()

    if row is None:
        current = _try_get_balance(user_id)
        if current is None:
            raise UserNotFound(f"user_id={user_id}")
        raise InsufficientBalance(user_id, available=current, required=amount)

    return int(row["balance"])


def _try_get_balance(user_id: int) -> int | None:
    try:
        return get_balance(user_id)
    except UserNotFound:
        return None
