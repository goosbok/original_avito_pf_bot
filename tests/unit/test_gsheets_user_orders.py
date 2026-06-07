"""'Заказы юзера' показывает статусы ссылок (Спек §7.2)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts, user_name) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1')",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url-a", "url-b"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done' WHERE url='url-a'")
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='manual', deadline_at='2026-06-30T00:00:00+00:00' "
                    "WHERE url='url-b'")
        con.commit()


def test_user_orders_includes_link_statuses_in_cell(tmp_db):
    from utils import googlesheets as gs
    _seed(tmp_db)

    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        return "https://example.test/sheet"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets._resolve_user_scope",
               return_value=(None, [1])), \
         patch("utils.googlesheets.get_user",
               return_value={"id": 1, "user_name": "user1"}), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        gs.create_orders_report(1)
    links_col = captured["columns"][3]
    text = "\n".join(str(x) for x in links_col)
    assert "url-a" in text and "done" in text
    assert "url-b" in text and "in_work" in text
