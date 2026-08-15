"""Карточка заказа в админке берёт подпись статуса из общего справочника."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.dates import now_iso


async def _card_for(tmp_db, status):
    from handlers.admin_orders import order_work_start
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts) VALUES (1, 100, '7/50', ?, ?, 0)",
            (status, now_iso()),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()
    with patch("handlers.admin_orders.get_string",
               return_value="{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}"):
        await order_work_start(message, state)
    return message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [
    ("unpaid", "🕐 Ожидает оплаты"),
    ("paid", "🚀 В работе"),
    ("done", "✅ Выполнен"),
    ("failed", "❌ Ошибка накрутки"),
    ("payment_failed", "⌛ Не оплачен"),
    ("cancelled", "🚫 Отменён"),
])
async def test_admin_card_uses_shared_status_labels(tmp_db, status, expected):
    assert expected in await _card_for(tmp_db, status)
