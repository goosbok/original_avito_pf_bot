"""Cron-задача закрытия in_work-ссылок по deadline."""
import sqlite3
from unittest.mock import AsyncMock, patch

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order_with_in_work_links(tmp_db, deadlines):
    """Создаёт заказ + len(deadlines) ссылок в status=in_work."""
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
                     urls=[f"url{i}" for i in range(len(deadlines))])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        for link_id, deadline in zip(link_ids, deadlines):
            con.execute(
                "UPDATE order_links SET status='in_work', "
                "delivery_mode='manual', deadline_at=? WHERE id=?",
                (deadline, link_id),
            )
        con.commit()
    return order_id, link_ids


def test_close_expired_marks_done_when_deadline_passed(tmp_db):
    from services.order_links_deadline import close_expired_links
    order_id, link_ids = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]  # давно в прошлом
    )
    closed = close_expired_links()
    assert closed == 1
    links = list_links(order_id)
    assert links[0]["status"] == "done"


def test_close_expired_skips_future_deadline(tmp_db):
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2099-01-01T00:00:00+00:00"]
    )
    closed = close_expired_links()
    assert closed == 0
    links = list_links(order_id)
    assert links[0]["status"] == "in_work"


def test_close_expired_recomputes_order_status(tmp_db):
    """Если все ссылки заказа done — order перейдёт в done."""
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00",
                           "2020-01-01T00:00:00+00:00"]
    )
    close_expired_links()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]
    assert s == "done"


def test_close_expired_fires_notification(tmp_db):
    """Заказ перешёл в done → должен вызваться notify_order_status_changed."""
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]
    )
    with patch("services.order_links_deadline.notify_order_status_changed",
               new=AsyncMock()) as mock:
        close_expired_links()
    # Должен быть один вызов: kind=order, order_id=<тот самый>, paid→done
    assert mock.called
    kwargs = mock.call_args.kwargs
    assert kwargs["order_id"] == order_id
    assert kwargs["old_status"] == "paid"
    assert kwargs["new_status"] == "done"


def test_close_expired_skips_already_done(tmp_db):
    """Уже done-ссылки не должны попасть в SELECT."""
    from services.order_links_deadline import close_expired_links
    order_id, link_ids = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]
    )
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done' WHERE id=?",
                    (link_ids[0],))
        con.commit()
    closed = close_expired_links()
    assert closed == 0
