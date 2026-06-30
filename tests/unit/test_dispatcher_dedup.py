"""Дедуп: на ошибке add-tasks усыновляем уже созданную задачу через get-tasks."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso


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


def test_error_adopts_existing_task_no_retry(tmp_db):
    oid = _seed(tmp_db, 1)
    with patch("services.order_links_dispatcher.classify", return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link", side_effect=ExecutorAPIError("500")), \
         patch("services.order_links_dispatcher.find_existing_task", return_value="ext-dup"):
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    link = list_links(oid)[0]
    assert link["status"] == "in_work"
    assert link["delivery_mode"] == "auto"
    assert link["external_id"] == "ext-dup"
    assert link["dispatch_attempts"] == 0  # усыновление НЕ считается попыткой


def test_error_no_existing_falls_back_to_cap(tmp_db):
    oid = _seed(tmp_db, 1)
    with patch("services.order_links_dispatcher.classify", return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link", side_effect=ExecutorAPIError("500")), \
         patch("services.order_links_dispatcher.find_existing_task", return_value=None):
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    link = list_links(oid)[0]
    assert link["status"] == "pending"
    assert link["delivery_mode"] == "auto"
    assert link["dispatch_attempts"] == 1
