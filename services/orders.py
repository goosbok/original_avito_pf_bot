"""Business logic for order creation and listing."""
from __future__ import annotations

from dataclasses import dataclass

from services.db import connect
from services.exceptions import UserNotFound
from utils.sqlite3 import (
    add_order,
    get_price,
    get_users_last_order,
    user_orders_count,
    user_orders_paginated,
)


class InsufficientBalance(Exception):
    pass


@dataclass
class PFOrderResult:
    order_id: int
    total_price: int
    status: str


def get_pf_price_per_unit() -> int:
    raw = get_price("price_avito_pf")
    return int(raw) if raw is not None else 1


def create_pf_order(
    user_id: int,
    links: list[str],
    days: int,
    fix_count: int,
    contacts: bool,
) -> PFOrderResult:
    price_per_unit = get_pf_price_per_unit()
    total = price_per_unit * fix_count * days * len(links)

    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")

    balance = int(row["balance"] or 0)
    if balance < total:
        raise InsufficientBalance(f"need {total}, have {balance}")

    with connect() as con:
        con.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (balance - total, user_id),
        )
        con.commit()

    add_order(
        user_id=user_id,
        price=total,
        position_name=f"{days}/{fix_count}",
        status="Posted",
        links=str(links),
        contacts=contacts,
        user_name=row["user_name"],
    )

    order = get_users_last_order(user_id)
    return PFOrderResult(order_id=order["increment"], total_price=total, status="Posted")


def list_orders(user_id: int, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    items = user_orders_paginated(user_id, limit=page_size, offset=offset)
    total = user_orders_count(user_id)
    return items, total
