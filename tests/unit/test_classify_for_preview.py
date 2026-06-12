"""classify_for_preview — dry-run классификация заказа для admin Test auto."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, urls):
    """Создать paid-заказ с pending ссылками."""
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


def test_classify_for_preview_empty_order(tmp_db):
    """Заказ без pending-ссылок (например все done) → пустой list."""
    from services.order_links_dispatcher import classify_for_preview
    order_id = _seed_paid_order(tmp_db, urls=[])
    previews = classify_for_preview(order_id)
    assert previews == []


def test_classify_for_preview_mixed_cache(tmp_db):
    """Заказ с 2 ссылками: одна в кэше, одна нет."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить квартиру",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
        "https://avito.ru/y_9999999999",
    ])

    previews = classify_for_preview(order_id)
    assert len(previews) == 2

    auto = next(p for p in previews if p.decision == "auto")
    assert auto.ad_id == "1234567890"
    assert auto.phrase == "купить квартиру"
    assert auto.reason == "cache_hit"
    assert auto.deadline_at is not None

    manual = next(p for p in previews if p.decision == "manual")
    assert manual.ad_id == "9999999999"
    assert manual.phrase is None
    assert manual.reason == "cache_miss"
    assert manual.deadline_at is None


def test_classify_for_preview_no_ad_id(tmp_db):
    """URL без извлекаемого ad_id → manual / no_ad_id."""
    from services.order_links_dispatcher import classify_for_preview
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://example.com/no_ad",
    ])

    previews = classify_for_preview(order_id)
    assert len(previews) == 1
    assert previews[0].decision == "manual"
    assert previews[0].reason == "no_ad_id"
    assert previews[0].ad_id is None


def test_classify_for_preview_ignores_feature_flag(tmp_db):
    """PF_AUTO_DISPATCH_ENABLED=False — всё равно классифицируем по кэшу."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False,
    ):
        previews = classify_for_preview(order_id)

    assert previews[0].decision == "auto"
    assert previews[0].phrase == "купить"


def test_classify_for_preview_does_not_submit(tmp_db):
    """Не дёргает submit_link, mark_in_work и не меняет БД."""
    from services.order_links_dispatcher import classify_for_preview
    from services.avito_phrase_cache import upsert_many
    from services.order_links import list_links

    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "x",
        "created_at": "2026-06-01 12:00",
    }])
    order_id = _seed_paid_order(tmp_db, urls=[
        "https://avito.ru/x_1234567890",
    ])

    with patch("services.order_links_dispatcher.submit_link") as submit, \
         patch(
             "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
             True,
         ):
        classify_for_preview(order_id)

    submit.assert_not_called()

    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] is None


def test_classify_for_preview_raises_when_order_not_found(tmp_db):
    """Несуществующий order_id → OrderNotFound."""
    from services.order_links_dispatcher import classify_for_preview
    from services.exceptions import OrderNotFound
    import pytest
    with pytest.raises(OrderNotFound):
        classify_for_preview(99999)
