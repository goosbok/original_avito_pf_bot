"""Бэкфилл order_links.search_link из avito_ad_phrase_cache."""
import sqlite3
from unittest.mock import patch

from utils.dates import now_iso


def _seed(tmp_db, rows):
    """rows: список (url, delivery_mode, search_link). Возвращает список link_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1')",
            (now_iso(),),
        )
        oid = int(cur.lastrowid)
        ids = []
        for url, mode, phrase in rows:
            c = con.execute(
                "INSERT INTO order_links(order_id, url, status, delivery_mode, "
                "search_link, created_at) VALUES (?, ?, 'in_work', ?, ?, ?)",
                (oid, url, mode, phrase, now_iso()),
            )
            ids.append(int(c.lastrowid))
        con.commit()
    return ids


def _seed_cache(tmp_db, ad_id, search_link):
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO avito_ad_phrase_cache(ad_id, search_link, created_at, "
            "cached_at) VALUES (?, ?, ?, ?)",
            (ad_id, search_link, now_iso(), now_iso()),
        )
        con.commit()


def test_backfill_fills_auto_links_with_null_phrase(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "1234567890", "https://avito.ru/search?q=диван")
    ids = _seed(tmp_db, [
        ("https://www.avito.ru/moskva/mebel/divan_1234567890", "auto", None),
    ])

    stats = backfill()

    assert stats["filled"] == 1
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (ids[0],)).fetchone()
    assert row[0] == "https://avito.ru/search?q=диван"


def test_backfill_skips_manual_and_already_filled(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "1111111111", "новая-фраза")
    _seed_cache(tmp_db, "2222222222", "новая-фраза-2")
    ids = _seed(tmp_db, [
        ("https://www.avito.ru/a/x_1111111111", "manual", None),
        ("https://www.avito.ru/a/x_2222222222", "auto", "старая-фраза"),
    ])

    stats = backfill()

    assert stats["filled"] == 0
    with sqlite3.connect(tmp_db) as con:
        manual = con.execute("SELECT search_link FROM order_links WHERE id=?",
                             (ids[0],)).fetchone()
        filled = con.execute("SELECT search_link FROM order_links WHERE id=?",
                             (ids[1],)).fetchone()
    assert manual[0] is None
    assert filled[0] == "старая-фраза"


def test_backfill_is_idempotent(tmp_db):
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "3333333333", "фраза")
    _seed(tmp_db, [("https://www.avito.ru/a/x_3333333333", "auto", None)])

    first = backfill()
    second = backfill()

    assert first["filled"] == 1
    assert second["filled"] == 0


def test_backfill_does_not_overwrite_concurrent_write(tmp_db):
    """Guard search_link IS NULL в UPDATE защищает от гонки с dispatcher'ом:
    если между нашим SELECT и UPDATE кто-то параллельно уже проставил
    search_link (например, dispatcher отправил задачу в биза прямо сейчас),
    бэкфилл не должен затирать это значение фразой из кэша."""
    from scripts.backfill_order_links_search_link import backfill

    _seed_cache(tmp_db, "4444444444", "фраза-из-кэша")
    ids = _seed(tmp_db, [
        ("https://www.avito.ru/a/x_4444444444", "auto", None),
    ])
    link_id = ids[0]

    def racing_lookup(ad_id):
        # Имитируем конкурента: он пишет в БД до того, как lookup() вернёт
        # результат бэкфиллу.
        with sqlite3.connect(tmp_db) as con:
            con.execute(
                "UPDATE order_links SET search_link=? WHERE id=?",
                ("фраза-от-конкурента", link_id),
            )
            con.commit()
        return "фраза-из-кэша"

    with patch("scripts.backfill_order_links_search_link.lookup",
               side_effect=racing_lookup):
        backfill()

    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT search_link FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row[0] == "фраза-от-конкурента"


def test_backfill_counts_misses_without_crashing(tmp_db):
    """Ссылка без ad_id и промах кэша не роняют проход."""
    from scripts.backfill_order_links_search_link import backfill

    _seed(tmp_db, [
        ("совсем-не-ссылка", "auto", None),
        ("https://www.avito.ru/a/x_9999999999", "auto", None),
    ])

    stats = backfill()

    assert stats["filled"] == 0
    assert stats["no_ad_id"] == 1
    assert stats["cache_miss"] == 1
    assert stats["processed"] == 2
