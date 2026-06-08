from datetime import date
from unittest.mock import patch, MagicMock

from services.avito_phrase_cache_refresh import refresh_recent


def test_refresh_skipped_when_flag_off(tmp_db):
    with patch("services.avito_phrase_cache_refresh."
               "config.PF_PHRASE_CACHE_REFRESH_ENABLED", False), \
         patch("services.avito_phrase_cache_refresh.login") as login:
        n = refresh_recent(days=2)
    assert n == 0
    login.assert_not_called()


def test_refresh_window_is_last_n_days(tmp_db):
    sess = MagicMock()
    with patch("services.avito_phrase_cache_refresh."
               "config.PF_PHRASE_CACHE_REFRESH_ENABLED", True), \
         patch("services.avito_phrase_cache_refresh.login",
               return_value=sess), \
         patch("services.avito_phrase_cache_refresh.fetch_dashboard",
               return_value="<html></html>") as fetch, \
         patch("services.avito_phrase_cache_refresh.parse_dashboard_html",
               return_value=[
                   {"ad_id": "111", "search_link": "x",
                    "created_at": "2026-06-08 09:00"},
               ]) as parse, \
         patch("services.avito_phrase_cache_refresh."
               "_today", return_value=date(2026, 6, 8)):
        n = refresh_recent(days=2)
    fetch.assert_called_once()
    args, kwargs = fetch.call_args
    assert kwargs["date_from"] == date(2026, 6, 6)
    assert kwargs["date_to"] == date(2026, 6, 8)
    assert n == 1
