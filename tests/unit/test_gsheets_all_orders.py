"""Экспорт 'Все заказы' джойнит orders + order_links (Спек §6.1, §7.1)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_order_with_links(tmp_db, urls, status="paid", link_status="in_work"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts, user_name) "
            "VALUES (1, 100, '3/100', ?, ?, 0, 'user1')",
            (status, now_iso()),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status=? WHERE order_id=?",
                    (link_status, order_id))
        con.commit()
    return order_id


def test_get_orders_with_links_batch_returns_join_rows(tmp_db):
    from utils.sqlite3 import get_orders_with_links_batch
    _seed_order_with_links(tmp_db, urls=["a", "b"])
    rows = get_orders_with_links_batch(limit=100, offset=0)
    urls = [r["url"] for r in rows]
    assert "a" in urls and "b" in urls
    # Поля заказа должны быть тоже:
    assert all("order_status" in r for r in rows)
    assert all("link_status" in r for r in rows)


def test_get_orders_with_links_batch_uses_live_users_username(tmp_db):
    """Если orders.user_name NULL (новый unpaid→paid flow), берём users.user_name.

    Воспроизводит баг: в чат-уведомлении username виден (там get_user из users),
    а в GSheets-выгрузке колонка username пустая, потому что SQL читает
    orders.user_name, а в новом flow services.orders.create_unpaid пишет туда NULL.
    """
    from utils.sqlite3 import get_orders_with_links_batch

    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (6122375249, 0, 'bragincpa')")
        # NB: user_name НЕ передан → колонка останется NULL (как делает create_unpaid)
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts) "
            "VALUES (6122375249, 300, '1/50', 'paid', ?, 1)",
            (now_iso(),),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://www.avito.ru/odintsovo/vakansii/x"])
        con.commit()

    rows = get_orders_with_links_batch(limit=100, offset=0)
    target = [r for r in rows if r["order_id"] == order_id]
    assert target, "тестовый заказ должен быть в выгрузке"
    assert target[0]["user_name"] == "bragincpa", (
        f"username должен подтянуться из users, а не из NULL-snapshot в orders; "
        f"получено: {target[0]['user_name']!r}"
    )


def test_create_sheet_uses_joined_rows(tmp_db):
    """Smoke-test: create_sheet не падает с новым backend'ом, передаёт ссылки в шит."""
    from utils import googlesheets as gs
    _seed_order_with_links(tmp_db, urls=["a", "b"])

    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        return "https://example.test/sheet"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets.get_report_exclude", return_value=[]), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        url = gs.create_sheet()
    assert url == "https://example.test/sheet"
    links_col = captured["columns"][3]  # 4-я колонка — Ссылки (см. порядок)
    assert "a" in links_col and "b" in links_col
