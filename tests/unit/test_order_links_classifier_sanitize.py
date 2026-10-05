"""Classifier: sanitize ключа из кэша + fallback в историю order_links.

Правила заказчика (2026-10-04): невалидный ключ (не-https форс-мажор)
не уходит в автозапуск — ищем другой ключ в БД или отправляем в manual.
Ключи с фильтром цены и «ключ;ссылка» нормализуются, а не отбрасываются.
"""
import sqlite3

from services.avito_phrase_cache import upsert_many
from services.order_links_classifier import classify, resolve_phrase
from utils.dates import now_iso

AD = "1234567890"
URL = f"https://avito.ru/moskva/divan_{AD}"
GOOD_KEY = "https://www.avito.ru/moskva?q=диван"


def _order():
    return {"position_name": "3/10"}


def _seed_cache(ad_id=AD, key=GOOD_KEY):
    upsert_many([{"ad_id": ad_id, "search_link": key,
                  "created_at": "2026-06-01 12:00"}])


def _seed_history(tmp_db, ad_id=AD, search_link=GOOD_KEY):
    """Одна отправленная ранее ссылка этого же объявления с search_link."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, '3/10', 'paid', ?, 0, 'user1')",
            (now_iso(),),
        )
        oid = int(cur.lastrowid)
        con.execute(
            "INSERT INTO order_links(order_id, url, status, delivery_mode, "
            "search_link, created_at) VALUES (?, ?, 'in_work', 'auto', ?, ?)",
            (oid, f"https://avito.ru/moskva/divan_{ad_id}", search_link,
             now_iso()),
        )
        con.commit()


# === sanitize в classifier ===

def test_cache_key_with_price_filter_is_stripped(tmp_db):
    _seed_cache(key=GOOD_KEY + "&priceMax=3300&priceMin=2700")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "auto"
    assert phrase == GOOD_KEY


def test_cache_key_with_semicolon_is_split(tmp_db):
    _seed_cache(key=GOOD_KEY + f";https://www.avito.ru/moskva/divan_{AD}")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "auto"
    assert phrase == GOOD_KEY


def test_invalid_cache_key_without_history_goes_manual(tmp_db):
    """Кэш держит форс-мажорную «1», истории нет → ручной запуск."""
    _seed_cache(key="1")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "manual"
    assert phrase is None


# === fallback в историю ===

def test_invalid_cache_key_falls_back_to_history(tmp_db):
    """Кэш битый («1»), но в истории есть валидный ключ → auto с ним."""
    _seed_cache(key="1")
    _seed_history(tmp_db)
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "auto"
    assert phrase == GOOD_KEY


def test_cache_miss_falls_back_to_history(tmp_db):
    _seed_history(tmp_db)
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "auto"
    assert phrase == GOOD_KEY


def test_history_key_with_price_is_stripped(tmp_db):
    _seed_history(tmp_db, search_link=GOOD_KEY + "&priceMin=100")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "auto"
    assert phrase == GOOD_KEY


def test_history_with_only_invalid_keys_goes_manual(tmp_db):
    _seed_history(tmp_db, search_link="1")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "manual"
    assert phrase is None


def test_history_of_other_ad_is_not_used(tmp_db):
    _seed_history(tmp_db, ad_id="9999999999")
    mode, phrase = classify(URL, _order(), link_id=1, force=True)
    assert mode == "manual"
    assert phrase is None


# === resolve_phrase source codes ===

def test_resolve_phrase_reports_cache_hit(tmp_db):
    _seed_cache()
    phrase, source = resolve_phrase(AD)
    assert phrase == GOOD_KEY
    assert source == "cache_hit"


def test_resolve_phrase_reports_history_hit(tmp_db):
    _seed_history(tmp_db)
    phrase, source = resolve_phrase(AD)
    assert phrase == GOOD_KEY
    assert source == "history_hit"


def test_resolve_phrase_reports_cache_miss(tmp_db):
    phrase, source = resolve_phrase(AD)
    assert phrase is None
    assert source == "cache_miss"
