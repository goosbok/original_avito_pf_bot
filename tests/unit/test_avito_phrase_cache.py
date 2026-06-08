from services import avito_phrase_cache as cache


def test_lookup_missing_returns_none(tmp_db):
    assert cache.lookup("12345") is None


def test_upsert_then_lookup(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "купить",
         "created_at": "2026-06-01 12:00"},
    ])
    assert cache.lookup("111") == "купить"


def test_upsert_latest_created_at_wins(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "old",
         "created_at": "2026-06-01 12:00"},
    ])
    cache.upsert_many([
        {"ad_id": "111", "search_link": "new",
         "created_at": "2026-06-05 12:00"},
    ])
    assert cache.lookup("111") == "new"


def test_upsert_older_does_not_overwrite(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "new",
         "created_at": "2026-06-05 12:00"},
    ])
    cache.upsert_many([
        {"ad_id": "111", "search_link": "old",
         "created_at": "2026-06-01 12:00"},
    ])
    assert cache.lookup("111") == "new"


def test_last_refreshed_at(tmp_db):
    assert cache.last_refreshed_at() is None
    cache.upsert_many([
        {"ad_id": "111", "search_link": "x",
         "created_at": "2026-06-05 12:00"},
    ])
    assert cache.last_refreshed_at() is not None
