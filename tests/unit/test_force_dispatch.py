"""force_dispatch — реальный submit для admin Test auto confirm."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, urls):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, '3/10', 'paid', NULL, ?)",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    return order_id


def _seed_phrase(ad_id, phrase):
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": ad_id, "search_link": phrase,
        "created_at": "2026-06-01 12:00",
    }])


def test_force_dispatch_empty_link_ids(tmp_db):
    """link_ids пуст → возвращает пустой list."""
    from services.order_links_dispatcher import force_dispatch
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    results = force_dispatch(order_id, link_ids=[])
    assert results == []


def test_force_dispatch_success_path(tmp_db):
    """Cache hit + submit OK → in_work, delivery_mode=auto, external_id."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "купить квартиру")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               return_value="ext-42") as submit:
        results = force_dispatch(order_id, link_ids=[link_id])

    assert len(results) == 1
    r = results[0]
    assert r.success is True
    assert r.external_id == "ext-42"
    assert r.error is None

    # link мутировал в in_work / auto / external_id
    link = list_links(order_id)[0]
    assert link["status"] == "in_work"
    assert link["delivery_mode"] == "auto"
    assert link["external_id"] == "ext-42"

    # submit_link был вызван с правильной phrase
    args, kwargs = submit.call_args
    assert kwargs["search_phrase"] == "купить квартиру"


def test_force_dispatch_executor_rejected_keeps_pending(tmp_db):
    """API Rejected → success=False, link остаётся pending (не flip в manual)."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIRejected("400 invalid")):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert len(results) == 1
    assert results[0].success is False
    assert "API отказал" in results[0].error
    assert results[0].external_id is None

    # link остался pending — Test auto осознанно не flip'ает
    link = list_links(order_id)[0]
    assert link["status"] == "pending"


def test_force_dispatch_executor_error_keeps_pending(tmp_db):
    """API временная ошибка → success=False, link не трогаем."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("429 rate")):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is False
    assert "временная" in results[0].error
    assert list_links(order_id)[0]["status"] == "pending"


def test_force_dispatch_skips_non_pending(tmp_db):
    """Если ссылка уже in_work — success=False, error 'уже не pending'."""
    from services.order_links_dispatcher import force_dispatch
    from services.order_links import mark_in_work
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    # transition link to in_work first
    mark_in_work(link_id, delivery_mode="manual",
                 deadline_at="2099-01-01T00:00:00+00:00")

    with patch("services.order_links_dispatcher.submit_link") as submit:
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is False
    assert "не pending" in results[0].error
    submit.assert_not_called()


def test_force_dispatch_ignores_feature_flag(tmp_db):
    """PF_AUTO_DISPATCH_ENABLED=False — всё равно отправляет."""
    from services.order_links_dispatcher import force_dispatch
    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False,
    ), patch("services.order_links_dispatcher.submit_link",
             return_value="ext-77"):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert results[0].success is True
    assert results[0].external_id == "ext-77"


def test_force_dispatch_race_invalidlinktransition(tmp_db):
    """Race: link уже не pending к моменту mark_in_work → отдельный error string.

    Cимулируется через mock'инг mark_in_work с InvalidLinkTransition.
    """
    from services.order_links_dispatcher import force_dispatch
    from services.exceptions import InvalidLinkTransition

    _seed_phrase("1234567890", "x")
    order_id = _seed_paid_order(tmp_db, urls=["https://avito.ru/x_1234567890"])
    link_id = list_links(order_id)[0]["id"]

    with patch("services.order_links_dispatcher.submit_link",
               return_value="ext-99"), \
         patch("services.order_links.mark_in_work",
               side_effect=InvalidLinkTransition(
                   from_status="in_work", to_status="in_work"
               )):
        results = force_dispatch(order_id, link_ids=[link_id])

    assert len(results) == 1
    r = results[0]
    assert r.success is False
    assert r.external_id == "ext-99"  # API уже создала
    assert "гонка" in r.error
    assert "ext-99" in r.error  # внешний id виден в error для диагностики
