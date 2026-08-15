"""CRUD-операции для order_links."""
import sqlite3
import pytest

from services.db import connect
from utils.dates import now_iso


def _seed_order(tmp_db, status="paid"):
    """Создаёт фиктивного user и order, возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', ?, ?)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_create_links_inserts_pending_rows(tmp_db):
    from services.order_links import create_links

    order_id = _seed_order(tmp_db)

    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/a", "https://avito.ru/b"])
        con.commit()

    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, delivery_mode, created_at FROM order_links "
            "WHERE order_id=? ORDER BY id", (order_id,)
        ))
    assert [r["url"] for r in rows] == ["https://avito.ru/a", "https://avito.ru/b"]
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["delivery_mode"] is None for r in rows)
    assert all(r["created_at"] for r in rows)


def test_create_links_empty_list_inserts_nothing(tmp_db):
    from services.order_links import create_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=[])
        con.commit()

    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 0


def test_list_links_returns_dicts_ordered_by_id(tmp_db):
    from services.order_links import create_links, list_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url1", "url2", "url3"])
        con.commit()

    links = list_links(order_id)
    assert [l["url"] for l in links] == ["url1", "url2", "url3"]
    assert all(isinstance(l, dict) for l in links)
    assert all("id" in l and "status" in l for l in links)


def test_get_link_returns_row(tmp_db):
    from services.order_links import create_links, get_link, list_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url"])
        con.commit()

    link_id = list_links(order_id)[0]["id"]
    link = get_link(link_id)
    assert link["url"] == "url"
    assert link["status"] == "pending"


def test_get_link_raises_link_not_found(tmp_db):
    from services.order_links import get_link
    from services.exceptions import LinkNotFound

    with pytest.raises(LinkNotFound):
        get_link(99999)
