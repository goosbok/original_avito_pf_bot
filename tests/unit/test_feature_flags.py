"""Runtime-флаг auto-dispatch: fallback на env + переключение через settings."""
from unittest.mock import patch

from services import feature_flags
from services.order_links_classifier import classify


def _order():
    return {"position_name": "3/10"}


def test_fallback_to_env_when_no_db_row(tmp_db):
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED", True):
        assert feature_flags.auto_dispatch_enabled() is True
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED", False):
        assert feature_flags.auto_dispatch_enabled() is False


def test_db_row_overrides_env(tmp_db):
    feature_flags.set_auto_dispatch_enabled(True)
    # env=False, но БД говорит «вкл» → включено
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED", False):
        assert feature_flags.auto_dispatch_enabled() is True

    feature_flags.set_auto_dispatch_enabled(False)
    # env=True, но БД говорит «выкл» → выключено
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED", True):
        assert feature_flags.auto_dispatch_enabled() is False


def test_classifier_respects_db_toggle(tmp_db, caplog):
    import logging
    caplog.set_level(logging.INFO)
    feature_flags.set_auto_dispatch_enabled(False)
    # env включён, но админ выключил через кнопку → manual
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED", True):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=100)
    assert mode == "manual"
    assert phrase is None
    assert any("feature_off" in r.message for r in caplog.records)


def test_classifier_force_ignores_db_toggle(tmp_db):
    from services.avito_phrase_cache import upsert_many
    upsert_many([{"ad_id": "1234567890",
                  "search_link": "https://www.avito.ru/msk?q=квартира",
                  "created_at": "2026-06-01 12:00"}])
    feature_flags.set_auto_dispatch_enabled(False)
    # Test auto-dispatch из админки (force=True) работает даже при выкл флаге
    mode, phrase = classify("https://avito.ru/x_1234567890",
                            _order(), link_id=101, force=True)
    assert mode == "auto"
    assert phrase == "https://www.avito.ru/msk?q=квартира"
