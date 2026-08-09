"""Вкладка 'Авто запуски': запрос выборки и сборка колонок."""
import sqlite3
from datetime import datetime, timedelta, timezone

from utils.dates import now_iso


def _iso_days_ago(days: int) -> str:
    """UTC ISO — тот же формат, что пишет utils.dates.now_iso в проде."""
    return (datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(days=days)).isoformat()


def _seed_link(tmp_db, *, delivery_mode, started_at, status='in_work',
               url='https://www.avito.ru/a/x_1234567890', search_link='фраза',
               external_id='ext-1', deadline_at=None, position_name='3/100',
               contacts=0):
    """Создаёт заказ с одной ссылкой. Возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) VALUES (1, 100, ?, 'paid', ?, ?, 'user1')",
            (position_name, now_iso(), contacts),
        )
        oid = int(cur.lastrowid)
        con.execute(
            "INSERT INTO order_links(order_id, url, status, delivery_mode, "
            "started_at, deadline_at, external_id, search_link, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, url, status, delivery_mode, started_at, deadline_at,
             external_id, search_link, now_iso()),
        )
        con.commit()
    return oid


def test_returns_only_auto_started_links(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    auto_oid = _seed_link(tmp_db, delivery_mode='auto',
                          started_at=_iso_days_ago(1))
    _seed_link(tmp_db, delivery_mode='manual', started_at=_iso_days_ago(1))
    _seed_link(tmp_db, delivery_mode='auto', started_at=None, status='pending')

    rows = get_auto_launched_links(days=30)

    assert len(rows) == 1
    assert rows[0]['order_id'] == auto_oid


def test_window_boundary(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    inside = _seed_link(tmp_db, delivery_mode='auto',
                        started_at=_iso_days_ago(29))
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(45))

    rows = get_auto_launched_links(days=30)

    assert [r['order_id'] for r in rows] == [inside]


def test_newest_first(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    old = _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(10))
    fresh = _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(2))

    rows = get_auto_launched_links(days=30)

    assert [r['order_id'] for r in rows] == [fresh, old]


def test_row_carries_all_export_fields(tmp_db):
    from utils.sqlite3 import get_auto_launched_links

    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               deadline_at='2026-09-01T00:00:00+03:00', contacts=1,
               position_name='5/20', external_id='biza-42',
               search_link='https://avito.ru/search?q=шкаф')

    row = get_auto_launched_links(days=30)[0]

    assert row['user_id'] == 1
    assert row['position_name'] == '5/20'
    assert row['contacts'] == 1
    assert row['url'] == 'https://www.avito.ru/a/x_1234567890'
    assert row['search_link'] == 'https://avito.ru/search?q=шкаф'
    assert row['link_status'] == 'in_work'
    assert row['deadline_at'] == '2026-09-01T00:00:00+03:00'
    assert row['external_id'] == 'biza-42'
