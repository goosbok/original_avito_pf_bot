"""Dispatcher: classify → API → manual fallback (Спек §5.1)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, n_links=2):
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
    return order_id


def test_dispatch_stub_all_to_manual_pending(tmp_db):
    """Стабы: classifier→manual → links остаются pending+manual."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=2)
    dispatch_pending_links(order_id)
    links = list_links(order_id)
    assert all(l["status"] == "pending" for l in links)
    assert all(l["delivery_mode"] == "manual" for l in links)


def test_dispatch_classifier_auto_api_success_sets_in_work(tmp_db):
    """classifier→auto + submit_link OK → in_work, delivery_mode=auto."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "купить квартиру")), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-123"):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "in_work"
    assert links[0]["delivery_mode"] == "auto"
    assert links[0]["external_id"] == "ext-123"
    assert links[0]["deadline_at"] is not None


def test_dispatch_classifier_auto_api_rejected_falls_back_to_manual(tmp_db):
    """classifier→auto + ExecutorAPIRejected → pending+manual (fallback)."""
    from services.order_links_dispatcher import dispatch_pending_links
    from services.exceptions import ExecutorAPIRejected
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "купить квартиру")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIRejected("nope")):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "manual"


def test_dispatch_classifier_auto_api_error_keeps_pending_for_retry(tmp_db):
    """classifier→auto + временный ExecutorAPIError → остаётся pending+auto."""
    from services.order_links_dispatcher import dispatch_pending_links
    from services.exceptions import ExecutorAPIError
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "купить квартиру")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("timeout")):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "auto"


def test_dispatch_idempotent_skips_already_classified(tmp_db):
    """Второй вызов dispatch не должен трогать ссылки в in_work."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=2)
    dispatch_pending_links(order_id)  # все → pending+manual

    # Симулируем, что одну ссылку админ уже отправил
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE order_links SET status='in_work', delivery_mode='manual' "
            "WHERE id=?", (link_ids[0],)
        )
        con.commit()

    dispatch_pending_links(order_id)  # повторно
    links = list_links(order_id)
    # Первая осталась in_work, вторая по-прежнему pending+manual
    assert links[0]["status"] == "in_work"
    assert links[1]["status"] == "pending"
    assert links[1]["delivery_mode"] == "manual"
