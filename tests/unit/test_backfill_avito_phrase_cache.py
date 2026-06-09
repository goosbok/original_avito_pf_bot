from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from scripts.backfill_avito_phrase_cache import iter_chunks, backfill
from services.biznesklondaik_client import LoginFailed


def test_iter_chunks_splits_correctly():
    chunks = list(iter_chunks(date(2026, 6, 8), days_back=10, chunk_size=4))
    # ожидаем 3 чанка: [-10..-6], [-6..-2], [-2..0]
    assert len(chunks) == 3
    assert chunks[0] == (date(2026, 5, 29), date(2026, 6, 2))
    assert chunks[-1][1] == date(2026, 6, 8)


def test_backfill_idempotent(tmp_db):
    sess = MagicMock()
    with patch("scripts.backfill_avito_phrase_cache.login",
               return_value=sess), \
         patch("scripts.backfill_avito_phrase_cache.fetch_dashboard",
               return_value="<html></html>"), \
         patch("scripts.backfill_avito_phrase_cache.parse_dashboard_html",
               return_value=[
                   {"ad_id": "111", "search_link": "x",
                    "created_at": "2026-06-05 12:00"},
               ]):
        n1 = backfill(days=8, chunk_size=4,
                      today=date(2026, 6, 8), delay_sec=0)
        n2 = backfill(days=8, chunk_size=4,
                      today=date(2026, 6, 8), delay_sec=0)
    # повторный запуск не валится; кэш консистентен
    from services.avito_phrase_cache import lookup
    assert lookup("111") == "x"


def test_backfill_login_failure_returns_zero(tmp_db, caplog):
    """Login fails → return 0, log error, don't bubble."""
    import logging
    caplog.set_level(logging.ERROR)
    with patch("scripts.backfill_avito_phrase_cache.login",
               side_effect=LoginFailed("bad creds")) as login_mock, \
         patch("scripts.backfill_avito_phrase_cache.fetch_dashboard") as fetch:
        n = backfill(days=8, chunk_size=4,
                     today=date(2026, 6, 8), delay_sec=0)
    assert n == 0
    fetch.assert_not_called()
    assert any("backfill.login_failed" in r.message for r in caplog.records)
