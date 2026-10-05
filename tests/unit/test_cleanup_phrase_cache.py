"""cleanup_phrase_cache: чистка исторического кэша от невалидных ключей."""
from services.avito_phrase_cache import lookup, upsert_many
from scripts.cleanup_phrase_cache import cleanup


def _seed(tmp_db):
    upsert_many([
        {"ad_id": "good", "search_link": "https://www.avito.ru/msk?q=диван",
         "created_at": "2026-10-01 12:00"},
        {"ad_id": "price", "search_link": "https://www.avito.ru/msk?q=диван"
                                           "&priceMax=3300&priceMin=2700",
         "created_at": "2026-10-01 12:00"},
        {"ad_id": "semicolon", "search_link": "https://www.avito.ru/msk?q=диван"
                                              ";https://www.avito.ru/msk/d_1",
         "created_at": "2026-10-01 12:00"},
        {"ad_id": "force", "search_link": "1",
         "created_at": "2026-10-01 12:00"},
    ])


def test_dry_run_does_not_write(tmp_db):
    _seed(tmp_db)
    stats = cleanup(apply=False)
    assert stats["mode"] == "dry-run"
    assert stats["would_update"] == 2   # price + semicolon
    assert stats["would_delete"] == 1   # force «1»
    # ничего не изменилось
    price_key = lookup("price")
    assert price_key is not None and price_key.endswith("priceMin=2700")
    assert lookup("force") == "1"


def test_apply_updates_and_deletes(tmp_db):
    _seed(tmp_db)
    stats = cleanup(apply=True)
    assert stats["updated"] == 2
    assert stats["deleted"] == 1

    assert lookup("good") == "https://www.avito.ru/msk?q=диван"
    assert lookup("price") == "https://www.avito.ru/msk?q=диван"
    assert lookup("semicolon") == "https://www.avito.ru/msk?q=диван"
    assert lookup("force") is None


def test_idempotent_second_run_is_noop(tmp_db):
    _seed(tmp_db)
    cleanup(apply=True)
    stats = cleanup(apply=True)
    assert stats["updated"] == 0
    assert stats["deleted"] == 0
