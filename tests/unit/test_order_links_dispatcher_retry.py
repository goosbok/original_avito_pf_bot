"""Retry-loop dispatcher'а: добивает paid-заказы с pending-ссылками."""
import sqlite3
from unittest.mock import patch


def test_dispatch_for_paid_orders_picks_orders_with_pending_links(tmp_db):
    from services.order_links_dispatcher import dispatch_for_paid_orders
    from services.order_links import create_links
    from services.db import connect
    from utils.dates import now_iso

    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        # paid с pending
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        paid_with_pending = int(cur.lastrowid)
        # paid без pending — все ссылки уже in_work
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        paid_done = int(cur.lastrowid)
        # unpaid — не должен тронуться
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'unpaid', ?)", (now_iso(),)
        )
        unpaid = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=paid_with_pending, urls=["a"])
        create_links(con, order_id=paid_done, urls=["b"])
        create_links(con, order_id=unpaid, urls=["c"])
        con.commit()
    # Помечаем второй заказ как уже dispatch'нутый
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='auto' WHERE order_id=?",
                    (paid_done,))
        con.commit()

    with patch("services.order_links_dispatcher.dispatch_pending_links") as mock:
        dispatch_for_paid_orders()

    called_order_ids = [c.args[0] for c in mock.call_args_list]
    assert paid_with_pending in called_order_ids
    assert paid_done not in called_order_ids
    assert unpaid not in called_order_ids
