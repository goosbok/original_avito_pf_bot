"""Агрегация orders.status из order_links. Спек §4.1."""
import sqlite3
import pytest

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_order(tmp_db, status="paid"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', ?, ?)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def _seed_links_with_statuses(tmp_db, order_id, statuses):
    """Создать N ссылок и расставить им заданные статусы напрямую."""
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"u{i}" for i in range(len(statuses))])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        for link_id, s in zip(link_ids, statuses):
            con.execute("UPDATE order_links SET status=? WHERE id=?",
                        (s, link_id))
        con.commit()


def _get_order_status(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]


def test_all_pending_keeps_paid(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["pending", "pending"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None  # no change
    assert _get_order_status(tmp_db, order_id) == "paid"


def test_mixed_pending_in_work_keeps_paid(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["pending", "in_work", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == "paid"


def test_all_done_transitions_to_done(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["done", "done", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "done")
    assert _get_order_status(tmp_db, order_id) == "done"


def test_done_with_failed_transitions_to_failed(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["done", "failed", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "failed")
    assert _get_order_status(tmp_db, order_id) == "failed"


def test_all_failed_transitions_to_failed(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["failed", "failed"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "failed")
    assert _get_order_status(tmp_db, order_id) == "failed"


@pytest.mark.parametrize("guarded", ["unpaid", "payment_failed", "cancelled"])
def test_guard_does_not_touch_non_paid_orders(tmp_db, guarded):
    """Заказ в unpaid/payment_failed/cancelled не апается в done даже если
    все ссылки done (защита от багов; работа невозможна до paid)."""
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status=guarded)
    _seed_links_with_statuses(tmp_db, order_id, ["done", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == guarded


def test_no_links_keeps_paid(tmp_db):
    """Заказ без ссылок — формально все terminal, но edge case: оставляем paid."""
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == "paid"
