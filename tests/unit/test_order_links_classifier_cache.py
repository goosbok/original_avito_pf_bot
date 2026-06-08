from unittest.mock import patch
from services.order_links_classifier import classify


def _order():
    return {"position_name": "3/10"}


def test_feature_off_returns_manual(tmp_db, caplog):
    import logging
    caplog.set_level(logging.INFO)
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any("feature_off" in r.message for r in caplog.records)


def test_no_ad_id_returns_manual(tmp_db, caplog):
    import logging
    caplog.set_level(logging.INFO)
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://example.com/no_ad", _order(),
                                link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any("no_ad_id" in r.message for r in caplog.records)


def test_cache_miss_returns_manual(tmp_db, caplog):
    import logging
    caplog.set_level(logging.INFO)
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any("cache_miss" in r.message for r in caplog.records)


def test_cache_hit_returns_auto(tmp_db, caplog):
    import logging
    caplog.set_level(logging.INFO)
    from services.avito_phrase_cache import upsert_many
    upsert_many([{"ad_id": "1234567890", "search_link": "купить квартиру",
                  "created_at": "2026-06-01 12:00"}])
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "auto"
    assert phrase == "купить квартиру"
    assert any("cache_hit" in r.message for r in caplog.records)
