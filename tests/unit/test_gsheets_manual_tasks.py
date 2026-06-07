"""Новый таб 'Manual задачи' (Спек §7.2)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed(tmp_db, start_date=None):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name, start_date) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1', ?)",
            (now_iso(), start_date),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    return order_id


def test_get_pending_manual_links_due_today_filters_correctly(tmp_db):
    from utils.sqlite3 import get_pending_manual_links_due_today

    # 1. pending+manual, start=today → попадёт
    oid_due = _seed(tmp_db, start_date=None)
    # 2. pending+manual, start=tomorrow → НЕ попадёт
    oid_future = _seed(tmp_db, start_date="2099-12-31")
    # 3. pending+auto → НЕ попадёт
    oid_auto = _seed(tmp_db, start_date=None)
    # 4. in_work+manual → НЕ попадёт (уже в работе)
    oid_in_work = _seed(tmp_db, start_date=None)

    with connect() as con:
        create_links(con, order_id=oid_due, urls=["due"])
        create_links(con, order_id=oid_future, urls=["future"])
        create_links(con, order_id=oid_auto, urls=["auto"])
        create_links(con, order_id=oid_in_work, urls=["inwork"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' "
                    "WHERE url IN ('due', 'future', 'inwork')")
        con.execute("UPDATE order_links SET delivery_mode='auto' WHERE url='auto'")
        con.execute("UPDATE order_links SET status='in_work' WHERE url='inwork'")
        con.commit()

    rows = get_pending_manual_links_due_today()
    urls = [r["url"] for r in rows]
    assert urls == ["due"]


def test_create_manual_tasks_sheet_writes_columns(tmp_db):
    from utils import googlesheets as gs
    oid = _seed(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["url-x"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE url='url-x'")
        con.commit()

    captured = {}
    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        captured["tab"] = tab
        return "https://example.test/manual"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        url = gs.create_manual_tasks_sheet()
    assert url == "https://example.test/manual"
    assert captured["tab"] == "Manual задачи"
    links_col = captured["columns"][3]
    assert "url-x" in links_col


def test_get_pending_manual_links_query_uses_msk_anchored_date():
    import inspect
    from utils import sqlite3 as u
    source = inspect.getsource(u.get_pending_manual_links_due_today)
    assert "'+3 hours'" in source
