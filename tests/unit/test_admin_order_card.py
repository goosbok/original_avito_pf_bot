"""Карточка заказа показывает ссылки + их статусы (Спек §5)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import sqlite3


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_db):
    """tmp_db creates schema; this fixture binds it to each test."""
    return tmp_db


@pytest.mark.asyncio
async def test_order_card_lists_links_with_statuses(tmp_db):
    from handlers.admin_orders import order_work_start
    from services.db import connect
    from services.order_links import create_links
    from utils.dates import now_iso

    # Seed order with mixed-status links
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance, user_name) VALUES (1, 0, 'user')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/a", "https://avito.ru/b"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done', "
                    "delivery_mode='manual' WHERE url=?",
                    ("https://avito.ru/a",))
        con.commit()

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.get_string", return_value="{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}"):
        await order_work_start(message, state)
    rendered = message.answer.await_args.args[0]
    assert "https://avito.ru/a" in rendered
    assert "done" in rendered
    assert "https://avito.ru/b" in rendered
    assert "pending" in rendered
