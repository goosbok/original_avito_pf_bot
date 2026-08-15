"""«📖️ Проверить статус заказа» отвечает по-русски, а не сырым 'paid'."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.dates import now_iso


def _seed_order(tmp_db, status):
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
    return order_id


async def _answer_for(tmp_db, status):
    from handlers.profile import check_order
    order_id = _seed_order(tmp_db, status)
    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock(return_value=MagicMock(message_id=10))
    state = AsyncMock()
    with patch("handlers.profile.get_string", return_value="Заказ #{}: статус {}"), \
         patch("handlers.profile.bot", AsyncMock()):
        await check_order(message, state, user_id=1)
    return message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_paid_order_reported_as_in_progress(tmp_db):
    answer = await _answer_for(tmp_db, "paid")
    assert "🚀 В работе" in answer
    assert "paid" not in answer


@pytest.mark.asyncio
async def test_done_order_reported_as_completed(tmp_db):
    answer = await _answer_for(tmp_db, "done")
    assert "✅ Выполнен" in answer
    assert "done" not in answer
