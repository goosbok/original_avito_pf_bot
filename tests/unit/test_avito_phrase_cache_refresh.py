import asyncio
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
                   {"ad_id": "111",
                    "search_link": "https://www.avito.ru/msk?q=диван",
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


def _refresh_with_rows(rows):
    """Прогон refresh_recent с подменённым дашбордом. Возвращает n upsert'ов."""
    sess = MagicMock()
    with patch("services.avito_phrase_cache_refresh."
               "config.PF_PHRASE_CACHE_REFRESH_ENABLED", True), \
         patch("services.avito_phrase_cache_refresh.login",
               return_value=sess), \
         patch("services.avito_phrase_cache_refresh.fetch_dashboard",
               return_value="<html></html>"), \
         patch("services.avito_phrase_cache_refresh.parse_dashboard_html",
               return_value=rows):
        return refresh_recent(days=2)


def test_refresh_skips_invalid_force_majeure_key(tmp_db):
    """«1» (форс-мажор, прямой запуск) не попадает в кэш автозапуска."""
    n = _refresh_with_rows([
        {"ad_id": "111", "search_link": "1", "created_at": "2026-10-04 09:00"},
        {"ad_id": "222", "search_link": "https://www.avito.ru/msk?q=диван",
         "created_at": "2026-10-04 09:00"},
    ])
    assert n == 1
    from services.avito_phrase_cache import lookup
    assert lookup("111") is None
    assert lookup("222") == "https://www.avito.ru/msk?q=диван"


def test_refresh_strips_price_filter_before_upsert(tmp_db):
    n = _refresh_with_rows([
        {"ad_id": "111",
         "search_link": "https://www.avito.ru/msk?q=диван"
                        "&priceMax=3300&priceMin=2700",
         "created_at": "2026-10-04 09:00"},
    ])
    assert n == 1
    from services.avito_phrase_cache import lookup
    assert lookup("111") == "https://www.avito.ru/msk?q=диван"


def test_refresh_invalid_new_key_does_not_overwrite_good_old(tmp_db):
    """Latest-wins работает только среди валидных: форс-мажорный запуск
    позже по времени не затирает хороший ключ."""
    n = _refresh_with_rows([
        {"ad_id": "111", "search_link": "https://www.avito.ru/msk?q=диван",
         "created_at": "2026-10-03 09:00"},
        {"ad_id": "111", "search_link": "1",
         "created_at": "2026-10-04 09:00"},
    ])
    assert n == 1
    from services.avito_phrase_cache import lookup
    assert lookup("111") == "https://www.avito.ru/msk?q=диван"


def test_refresh_semicolon_key_is_split_before_upsert(tmp_db):
    n = _refresh_with_rows([
        {"ad_id": "111",
         "search_link": "https://www.avito.ru/msk?q=диван"
                        ";https://www.avito.ru/msk/divan_111",
         "created_at": "2026-10-04 09:00"},
    ])
    assert n == 1
    from services.avito_phrase_cache import lookup
    assert lookup("111") == "https://www.avito.ru/msk?q=диван"


def test_run_refresh_loop_does_boot_refresh():
    """Loop вызывает refresh_recent ОДИН раз сразу при старте,
    до первого asyncio.sleep."""
    from services.avito_phrase_cache_refresh import run_refresh_loop

    call_count = 0

    def fake_refresh(days=2):
        nonlocal call_count
        call_count += 1
        return 0

    async def runner():
        with patch("services.avito_phrase_cache_refresh.refresh_recent",
                   side_effect=fake_refresh), \
             patch("services.avito_phrase_cache_refresh.asyncio.sleep",
                   side_effect=asyncio.CancelledError):
            try:
                await run_refresh_loop()
            except asyncio.CancelledError:
                pass

    asyncio.run(runner())
    # Boot refresh ran, then loop hit sleep and got cancelled.
    assert call_count == 1
