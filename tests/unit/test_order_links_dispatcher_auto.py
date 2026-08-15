"""e2e: оплата → classify → submit_link → mark_in_work с external_id."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.avito_phrase_cache import upsert_many
from utils.dates import now_iso


def _seed(tmp_db, url):
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
        create_links(con, order_id=order_id, urls=[url])
        con.commit()
    return order_id


def test_e2e_auto_dispatch_when_phrase_cached(tmp_db):
    """Cache hit + feature on → submit_link вызван, link in_work auto."""
    url = "https://avito.ru/moskva/kvartiry/x_1234567890"
    order_id = _seed(tmp_db, url)
    upsert_many([{"ad_id": "1234567890",
                  "search_link": "купить квартиру",
                  "created_at": "2026-06-01 12:00"}])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        True), patch(
        "services.order_links_dispatcher.submit_link",
        return_value="ext-42",
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    # submit_link был вызван с search_phrase из кэша
    args, kwargs = submit.call_args
    assert kwargs["search_phrase"] == "купить квартиру"
    assert args[0] == url

    links = list_links(order_id)
    assert links[0]["status"] == "in_work"
    assert links[0]["delivery_mode"] == "auto"
    assert links[0]["external_id"] == "ext-42"


def test_e2e_manual_when_feature_off(tmp_db):
    url = "https://avito.ru/moskva/kvartiry/x_1234567890"
    order_id = _seed(tmp_db, url)
    upsert_many([{"ad_id": "1234567890", "search_link": "x",
                  "created_at": "2026-06-01 12:00"}])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False), patch(
        "services.order_links_dispatcher.submit_link"
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    submit.assert_not_called()
    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "manual"


def test_e2e_manual_when_cache_miss(tmp_db):
    url = "https://avito.ru/moskva/kvartiry/x_9999999999"
    order_id = _seed(tmp_db, url)
    # кэш пустой

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        True), patch(
        "services.order_links_dispatcher.submit_link"
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    submit.assert_not_called()
    links = list_links(order_id)
    assert links[0]["delivery_mode"] == "manual"
