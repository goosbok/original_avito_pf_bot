"""Cron-задача закрытия in_work-ссылок по deadline."""
import asyncio
import sqlite3

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
    count, transitions = close_expired_links()
    assert count == 1
    links = list_links(order_id)
    assert links[0]["status"] == "done"


def test_close_expired_skips_future_deadline(tmp_db):
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2099-01-01T00:00:00+00:00"]
    )
    count, transitions = close_expired_links()
    assert count == 0
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
    count, transitions = close_expired_links()
    assert count == 0


def test_close_expired_returns_transitions_with_user_id(tmp_db):
    """Заказ перешёл в done → возвращаем (count, [(order_id, user_id, old, new)])."""
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]
    )
    count, transitions = close_expired_links()
    assert count == 1
    assert transitions == [(order_id, 1, "paid", "done")]  # user_id=1 from seed


import pytest


@pytest.mark.asyncio
async def test_run_deadline_loop_iteration_fires_notify(tmp_db, monkeypatch):
    """Одна итерация run_deadline_loop должна await'ить notify для каждого
    transition'а."""
    from services import order_links_deadline as mod

    called = []

    async def fake_notify(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr(mod, "notify_order_status_changed", fake_notify)
    monkeypatch.setattr(mod, "close_expired_links",
                        lambda: (1, [(99, 5, "paid", "done")]))

    async def short_sleep(_):
        raise asyncio.CancelledError()

    monkeypatch.setattr(mod.asyncio, "sleep", short_sleep)

    with pytest.raises(asyncio.CancelledError):
        await mod.run_deadline_loop()

    assert len(called) == 1
    assert called[0]["order_id"] == 99
    assert called[0]["user_id"] == 5
    assert called[0]["old_status"] == "paid"
    assert called[0]["new_status"] == "done"
