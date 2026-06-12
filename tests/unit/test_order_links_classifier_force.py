"""Classifier `force=True` kwarg — bypasses feature flag gate."""
from unittest.mock import patch
from services.order_links_classifier import classify


def _order():
    return {"position_name": "3/10"}


def test_force_true_bypasses_feature_off_when_cache_hit(tmp_db):
    """force=True + кэш есть → auto даже когда фича выключена."""
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить квартиру",
        "created_at": "2026-06-01 12:00",
    }])

    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890",
            _order(), link_id=99, force=True,
        )

    assert mode == "auto"
    assert phrase == "купить квартиру"


def test_force_true_returns_manual_when_no_ad_id(tmp_db):
    """force=True не магически делает auto без ad_id."""
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://example.com/no_ad", _order(),
            link_id=99, force=True,
        )

    assert mode == "manual"
    assert phrase is None


def test_force_true_returns_manual_when_cache_miss(tmp_db):
    """force=True + кэш пуст → manual (cache_miss)."""
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890", _order(),
            link_id=99, force=True,
        )

    assert mode == "manual"
    assert phrase is None


def test_force_false_respects_feature_off(tmp_db):
    """force=False (дефолт) + фича выключена → manual независимо от кэша."""
    from services.avito_phrase_cache import upsert_many
    upsert_many([{
        "ad_id": "1234567890",
        "search_link": "купить",
        "created_at": "2026-06-01 12:00",
    }])

    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify(
            "https://avito.ru/x_1234567890",
            _order(), link_id=99,  # force=False default
        )

    assert mode == "manual"
    assert phrase is None
