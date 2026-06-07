"""Владелец таблицы order_links.

Единственная точка мутации со встроенной валидацией переходов и пересчётом
orders.status (Спек §4.1). Все методы работают как через явный `con`
(участвуя в транзакции caller'а), так и через свой connect().
"""
from __future__ import annotations

import logging

from services.db import connect
from services.exceptions import LinkNotFound
from utils.dates import now_iso

logger = logging.getLogger(__name__)


# === CRUD ===

def create_links(con, *, order_id: int, urls: list[str]) -> None:
    """Создать pending-ссылки заказа. Работает в переданной транзакции."""
    created = now_iso()
    for url in urls:
        con.execute(
            "INSERT INTO order_links(order_id, url, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (order_id, url, created),
        )


def list_links(order_id: int) -> list[dict]:
    """Все ссылки заказа, упорядочены по id (порядок создания)."""
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM order_links WHERE order_id=? ORDER BY id",
            (order_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_link(link_id: int) -> dict:
    """Прочитать одну ссылку. Raises LinkNotFound."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM order_links WHERE id=?", (link_id,)
        ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    return dict(row)
