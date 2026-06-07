"""Публичные методы перехода (mark_*) + пересчёт order.status."""
import sqlite3

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_order_with_links(tmp_db, n_links=2):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"url{i}" for i in range(n_links)])
        con.commit()
    return order_id, [l["id"] for l in list_links(order_id)]


def _order_status(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]


def test_mark_in_work_returns_none_when_others_still_pending(tmp_db):
    from services.order_links import mark_in_work
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=2)
    result = mark_in_work(
        link_ids[0], delivery_mode="auto",
        deadline_at="2026-06-30T00:00:00+00:00",
    )
    assert result is None
    assert _order_status(tmp_db, order_id) == "paid"


def test_mark_done_last_link_returns_old_new(tmp_db):
    from services.order_links import mark_in_work, mark_done
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    mark_in_work(link_ids[0], delivery_mode="manual",
                 deadline_at="2026-06-30T00:00:00+00:00")
    result = mark_done(link_ids[0])
    assert result == ("paid", "done")
    assert _order_status(tmp_db, order_id) == "done"


def test_mark_failed_writes_reason_and_aggregates(tmp_db):
    from services.order_links import mark_failed
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    result = mark_failed(link_ids[0], reason="manual cancel")
    assert result == ("paid", "failed")
    assert _order_status(tmp_db, order_id) == "failed"


def test_mark_done_idempotent(tmp_db):
    """Повторный mark_done — не падает, не дублирует notify."""
    from services.order_links import mark_in_work, mark_done
    _, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    mark_in_work(link_ids[0], delivery_mode="auto",
                 deadline_at="2026-06-30T00:00:00+00:00")
    first = mark_done(link_ids[0])
    second = mark_done(link_ids[0])
    assert first == ("paid", "done")
    assert second is None
