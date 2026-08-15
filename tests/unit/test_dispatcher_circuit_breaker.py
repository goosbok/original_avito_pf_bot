"""Стоп-кран в диспетчере: после N ошибок подряд проход прерывается; cooldown пропускает тики."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso

# Сброс _breaker/rate_limiter между тестами обеспечивает autouse-фикстура
# _reset_biza_singletons из conftest.py (Task 1).


def _seed(tmp_db, n):
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


def test_breaker_aborts_pass_after_consecutive_errors(tmp_db):
    # 5 ссылок, submit_link всегда падает. Брейкер открывается на 3-й → проход
    # прерывается, submit вызван ровно BIZA_BREAKER_ERRORS (3) раз.
    oid = _seed(tmp_db, 5)
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    assert submit.call_count == 3


def test_dispatch_for_paid_orders_skips_when_breaker_open(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import _breaker, dispatch_for_paid_orders
    # вручную открываем брейкер
    for _ in range(3):
        _breaker.record_error()
    assert _breaker.allow() is False
    with patch("services.order_links_dispatcher.dispatch_pending_links") as dpl:
        handled = dispatch_for_paid_orders()
    assert handled == 0
    dpl.assert_not_called()


def test_success_resets_breaker(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import _breaker, dispatch_pending_links
    _breaker.record_error(); _breaker.record_error()
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-9"):
        dispatch_pending_links(oid)
    assert _breaker.allow() is True
    # счётчик обнулён: 2 новые ошибки не открывают (нужно 3 подряд)
    _breaker.record_error(); _breaker.record_error()
    assert _breaker.allow() is True
