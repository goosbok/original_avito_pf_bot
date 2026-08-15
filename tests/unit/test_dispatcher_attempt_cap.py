"""Потолок попыток авто-отправки: 2 неудачи → manual; + миграция колонки."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso


def test_order_links_has_dispatch_attempts_column(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(order_links)").fetchall()}
    assert "dispatch_attempts" in cols


def _seed(tmp_db, n=1):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/10', 'paid', ?)", (now_iso(),))
        oid = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=oid, urls=[f"u{i}" for i in range(n)])
        con.commit()
    return oid


def test_first_api_error_keeps_pending_auto_increments_attempts(tmp_db):
    oid = _seed(tmp_db, 1)
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    link = list_links(oid)[0]
    assert link["status"] == "pending"
    assert link["delivery_mode"] == "auto"
    assert link["dispatch_attempts"] == 1


def test_second_api_error_flips_to_manual(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import dispatch_pending_links
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        dispatch_pending_links(oid)   # attempts -> 1
        dispatch_pending_links(oid)   # attempts -> 2 → manual
    link = list_links(oid)[0]
    assert link["status"] == "pending"
    assert link["delivery_mode"] == "manual"
    assert link["dispatch_attempts"] == 2


def test_capped_manual_link_not_redispatched(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import dispatch_pending_links
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        dispatch_pending_links(oid)
        dispatch_pending_links(oid)   # → manual (attempts=2)
        with patch("services.order_links_dispatcher.submit_link") as submit3:
            dispatch_pending_links(oid)   # уже manual — не должен сабмититься
            submit3.assert_not_called()
