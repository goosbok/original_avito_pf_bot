"""Bulk-операции: 'Отправил все manual' и 'Заказ failed'."""
import sqlite3

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, status="paid"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, start_date) "
            "VALUES (1, 100, '3/100', ?, ?, NULL)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_mark_all_manual_in_work_only_picks_manual_pending(tmp_db):
    """Должны быть переведены ТОЛЬКО pending+manual ссылки с due-start."""
    from services.order_links import mark_all_manual_in_work
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a", "b", "c", "d"])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        # 0: pending + manual — должна перейти
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_ids[0],))
        # 1: pending + auto — НЕ должна (она для API)
        con.execute("UPDATE order_links SET delivery_mode='auto' WHERE id=?",
                    (link_ids[1],))
        # 2: pending + NULL — НЕ должна (ещё не классифицирована)
        # 3: in_work + manual — уже в работе
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='manual' WHERE id=?", (link_ids[3],))
        con.commit()

    n = mark_all_manual_in_work(admin_id=42)
    assert n == 1
    statuses = {l["id"]: l["status"] for l in list_links(order_id)}
    assert statuses[link_ids[0]] == "in_work"
    assert statuses[link_ids[1]] == "pending"
    assert statuses[link_ids[2]] == "pending"
    assert statuses[link_ids[3]] == "in_work"


def test_mark_all_manual_in_work_skips_future_start_date(tmp_db):
    """Ссылки заказов с start_date > today не должны попадать в bulk."""
    from services.order_links import mark_all_manual_in_work
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, start_date) "
            "VALUES (1, 100, '3/100', 'paid', ?, '2099-01-01')",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_id,))
        con.commit()
    n = mark_all_manual_in_work(admin_id=42)
    assert n == 0
    assert list_links(order_id)[0]["status"] == "pending"


def test_mark_all_manual_sets_deadline_at(tmp_db):
    from services.order_links import mark_all_manual_in_work
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_id,))
        con.commit()
    mark_all_manual_in_work(admin_id=42)
    link = list_links(order_id)[0]
    assert link["status"] == "in_work"
    assert link["deadline_at"] is not None


def test_fail_remaining_links_transitions_pending_and_in_work(tmp_db):
    from services.order_links import fail_remaining_links
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a", "b", "c"])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='auto' WHERE id=?", (link_ids[1],))
        con.execute("UPDATE order_links SET status='done' WHERE id=?",
                    (link_ids[2],))
        con.commit()

    transition = fail_remaining_links(
        order_id=order_id, reason="manual cancel", admin_id=42
    )
    statuses = {l["id"]: (l["status"], l["failure_reason"])
                for l in list_links(order_id)}
    assert statuses[link_ids[0]] == ("failed", "manual cancel")
    assert statuses[link_ids[1]] == ("failed", "manual cancel")
    assert statuses[link_ids[2]] == ("done", None)
    assert transition == ("paid", "failed")


def test_fail_remaining_links_idempotent(tmp_db):
    """Повтор на уже failed-заказе — no-op."""
    from services.order_links import fail_remaining_links
    order_id = _seed_paid_order(tmp_db, status="paid")
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    fail_remaining_links(order_id=order_id, reason="x", admin_id=1)
    second = fail_remaining_links(order_id=order_id, reason="y", admin_id=1)
    assert second is None  # status уже failed
