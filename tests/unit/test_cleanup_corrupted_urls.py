"""Очистка URL от \\n/\\r/\\t/пробелов и дедуп внутри order_id."""
import sqlite3

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_order(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        con.commit()
        return int(cur.lastrowid)


def test_normalize_url_strips_whitespace():
    from scripts.cleanup_corrupted_urls import normalize_url
    assert normalize_url("  https://avito.ru/a  ") == "https://avito.ru/a"
    assert normalize_url("https://avito.ru/\nb") == "https://avito.ru/b"
    assert normalize_url("https://avito.ru/\r\nc") == "https://avito.ru/c"
    assert normalize_url("https://avito.ru/\td") == "https://avito.ru/d"


def test_normalize_url_handles_none_and_empty():
    from scripts.cleanup_corrupted_urls import normalize_url
    assert normalize_url(None) == ""
    assert normalize_url("") == ""


def test_dry_run_does_not_modify_db(tmp_db):
    from scripts.cleanup_corrupted_urls import scan_and_clean

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/x\n", "https://avito.ru/y"])
        con.commit()

    before = list_links(order_id)
    report = scan_and_clean(apply=False)
    after = list_links(order_id)

    assert before == after
    assert report["rows_with_dirty_url"] == 1
    assert report["rows_updated"] == 0
    assert report["rows_deleted"] == 0


def test_apply_normalizes_url(tmp_db):
    from scripts.cleanup_corrupted_urls import scan_and_clean

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/dirty\n"])
        con.commit()

    scan_and_clean(apply=True)
    links = list_links(order_id)
    assert len(links) == 1
    assert links[0]["url"] == "https://avito.ru/dirty"


def test_apply_deduplicates_within_order_keeping_earliest(tmp_db):
    """Две ссылки одного заказа с одинаковым нормализованным URL ->
    остаётся одна с наименьшим id."""
    from scripts.cleanup_corrupted_urls import scan_and_clean

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=[
            "https://avito.ru/abc\n",  # dirty version, gets id=1
            "https://avito.ru/abc",    # clean, id=2
            "https://avito.ru/abc",    # clean dupe, id=3
        ])
        con.commit()

    report = scan_and_clean(apply=True)
    links = list_links(order_id)
    assert len(links) == 1
    assert links[0]["url"] == "https://avito.ru/abc"
    assert report["rows_deleted"] == 2
    assert report["rows_updated"] == 1


def test_dedup_preserves_best_status(tmp_db):
    """При склейке выбираем done > failed > in_work > pending."""
    from scripts.cleanup_corrupted_urls import scan_and_clean

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=[
            "https://avito.ru/q\n",
            "https://avito.ru/q",
        ])
        con.commit()
    # Один сделаем done, другой оставим pending
    with sqlite3.connect(tmp_db) as con:
        first_id = con.execute(
            "SELECT MIN(id) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
        second_id = con.execute(
            "SELECT MAX(id) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
        con.execute("UPDATE order_links SET status='done' WHERE id=?",
                    (second_id,))
        con.commit()

    scan_and_clean(apply=True)
    links = list_links(order_id)
    assert len(links) == 1
    assert links[0]["status"] == "done"


def test_does_not_touch_clean_urls(tmp_db):
    from scripts.cleanup_corrupted_urls import scan_and_clean

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/clean1", "https://avito.ru/clean2"])
        con.commit()

    report = scan_and_clean(apply=True)
    links = list_links(order_id)
    assert len(links) == 2
    assert report["rows_updated"] == 0
    assert report["rows_deleted"] == 0
