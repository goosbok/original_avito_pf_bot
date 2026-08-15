"""design.py order formatters читают ссылки из order_links."""
import sqlite3

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_order(tmp_db, urls):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance, user_name) "
                    "VALUES (1, 100, 'tester')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'tester')",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    return order_id


def test_render_order_links_block_uses_order_links(tmp_db):
    from design import _render_order_links_block
    oid = _seed_order(tmp_db, ["https://avito.ru/a", "https://avito.ru/b"])
    block = _render_order_links_block({"increment": oid})
    assert "https://avito.ru/a" in block
    assert "https://avito.ru/b" in block
    assert "Ссылки на объявления(2)" in block


def test_render_order_links_block_empty(tmp_db):
    from design import _render_order_links_block
    oid = _seed_order(tmp_db, [])
    block = _render_order_links_block({"increment": oid})
    assert block == "🔗 Ссылок нет"


def test_listord_array_uses_order_links(tmp_db):
    from design import listord_array
    oid = _seed_order(tmp_db, ["https://avito.ru/x"])
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        order = dict(con.execute(
            "SELECT * FROM orders WHERE increment=?", (oid,)
        ).fetchone())
    result = listord_array([order])
    assert len(result) == 1
    assert "https://avito.ru/x" in result[0]


def test_order_text_uses_order_links(tmp_db):
    from design import order_text
    oid = _seed_order(tmp_db, ["https://avito.ru/z"])
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        order = dict(con.execute(
            "SELECT * FROM orders WHERE increment=?", (oid,)
        ).fetchone())
    msg = order_text(order)
    assert "https://avito.ru/z" in msg
