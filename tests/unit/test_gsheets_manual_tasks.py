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


def test_get_pending_manual_links_query_uses_msk_04h_cutoff():
    """Фильтр в manual-выгрузке использует те же три модификатора,
    что и `_effective_start_msk` в pf_executor_api: +3h (UTC→MSK), -4h
    (отступ к 04:00 МСК), -1s (граница 04:00:00 принадлежит вчера)."""
    import inspect
    from utils import sqlite3 as u
    source = inspect.getsource(u.get_pending_manual_links_due_today)
    assert "'+3 hours'" in source
    assert "'-4 hours'" in source
    assert "'-1 seconds'" in source


def test_get_pending_manual_links_cutoff_behavior_at_business_day_boundary(tmp_db):
    """Поведенческая проверка cutoff 04:00 МСК на боевых данных.

    Помещаем 3 ссылки со start_date {вчера, сегодня, завтра} относительно
    ТЕКУЩЕЙ бизнес-сутки (а не календарной), и проверяем, что фильтр
    возвращает только вчера + сегодня, без завтра.
    """
    import sqlite3 as _sql
    from datetime import datetime, timedelta, timezone
    from utils.sqlite3 import get_pending_manual_links_due_today

    _MSK = timezone(timedelta(hours=3))
    now_msk = datetime.now(timezone.utc).astimezone(_MSK)
    # business_date: дата, чей 04:00 МСК cutoff уже прошёл.
    cutoff_today = now_msk.replace(hour=4, minute=0, second=0, microsecond=0)
    if now_msk <= cutoff_today:
        business_date = now_msk.date() - timedelta(days=1)
    else:
        business_date = now_msk.date()

    yesterday = (business_date - timedelta(days=1)).isoformat()
    today = business_date.isoformat()
    tomorrow = (business_date + timedelta(days=1)).isoformat()

    oid_y = _seed(tmp_db, start_date=yesterday)
    oid_t = _seed(tmp_db, start_date=today)
    oid_f = _seed(tmp_db, start_date=tomorrow)
    from services.db import connect
    from services.order_links import create_links
    with connect() as con:
        create_links(con, order_id=oid_y, urls=["yest"])
        create_links(con, order_id=oid_t, urls=["today"])
        create_links(con, order_id=oid_f, urls=["tomr"])
        con.commit()
    with _sql.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' "
                    "WHERE url IN ('yest', 'today', 'tomr')")
        con.commit()

    urls = {r["url"] for r in get_pending_manual_links_due_today()}
    assert "yest" in urls, "вчерашняя бизнес-сутка должна быть видна"
    assert "today" in urls, "сегодняшняя бизнес-сутка должна быть видна"
    assert "tomr" not in urls, "завтрашняя бизнес-сутка НЕ должна быть видна"
