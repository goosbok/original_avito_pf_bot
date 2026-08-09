"""Колонка order_links.search_link: схема, персист, dispatcher."""
import sqlite3

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_order(tmp_db, position_name='3/100', contacts=0):
    """Создаёт юзера и paid-заказ, возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, ?, 'paid', ?, ?, 'user1')",
            (position_name, now_iso(), contacts),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    return order_id


def test_order_links_has_search_link_column(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(order_links)")}
    assert 'search_link' in cols


def test_search_link_defaults_to_null(tmp_db):
    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links").fetchone()
    assert row[0] is None


def test_mark_in_work_persists_search_link(tmp_db):
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 external_id="777", search_link="https://avito.ru/search?q=диван")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT status, external_id, search_link FROM order_links WHERE id=?",
            (link_id,),
        ).fetchone()
    assert row[0] == "in_work"
    assert row[1] == "777"
    assert row[2] == "https://avito.ru/search?q=диван"


def test_mark_in_work_without_search_link_leaves_null(tmp_db):
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="manual",
                 deadline_at="2026-08-20T00:00:00+03:00")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] is None


def test_repeated_mark_in_work_does_not_overwrite_phrase(tmp_db):
    """Повторный вызов — no-op по контракту _transition, фраза сохраняется."""
    from services.order_links import mark_in_work

    oid = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["https://avito.ru/a_1234567890"])
        con.commit()
    with connect() as con:
        link_id = int(con.execute("SELECT id FROM order_links").fetchone()["id"])

    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 search_link="первая-фраза")
    mark_in_work(link_id, delivery_mode="auto", deadline_at="2026-08-20T00:00:00+03:00",
                 search_link="вторая-фраза")

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] == "первая-фраза"
