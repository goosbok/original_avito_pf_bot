"""Вкладка 'Авто запуски': запрос выборки и сборка колонок."""
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from utils.dates import now_iso


def _iso_days_ago(days: int) -> str:
    """UTC ISO — тот же формат, что пишет utils.dates.now_iso в проде."""
    return (datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(days=days)).isoformat()


def _iso_evening_days_ago(days: int) -> str:
    """UTC ISO на 23:30 конкретных суток — вечерний запуск.

    В МСК (UTC+3) это уже 02:30 СЛЕДУЮЩЕГО календарного дня. Нужен тесту
    на конверсию колонки «Старт»: если бы дата бралась сырым срезом ISO
    без перевода в МСК, она бы совпала с UTC-датой, а не ушла на день
    вперёд — тест должен ловить именно эту регрессию.
    """
    base_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    return datetime(base_date.year, base_date.month, base_date.day, 23, 30,
                    tzinfo=timezone.utc).isoformat()


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


def _capture_sheet():
    """Патчит Sheets API и возвращает (context manager, captured dict)."""
    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["tab"] = tab
        captured["columns"] = cols
        captured["widths"] = widths
        return "https://example.test/auto"

    ctx = [
        patch("utils.googlesheets._init", return_value=None),
        patch("utils.googlesheets._require_target", return_value=None),
        patch("utils.googlesheets._get_or_create_tab", return_value=7),
        patch("utils.googlesheets._write_tab", side_effect=_fake_write),
    ]
    return ctx, captured


def _run_export():
    from utils import googlesheets as gs
    ctx, captured = _capture_sheet()
    for c in ctx:
        c.start()
    try:
        url = gs.create_auto_tasks_sheet()
    finally:
        for c in ctx:
            c.stop()
    return url, captured


def test_create_auto_tasks_sheet_headers_and_order(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               deadline_at='2026-09-01T00:00:00+03:00', contacts=1,
               position_name='5/20', external_id='biza-42',
               search_link='фраза-1')

    url, captured = _run_export()

    assert url == "https://example.test/auto"
    assert captured["tab"] == "Авто запуски"
    headers = [col[0] for col in captured["columns"]]
    assert headers == [
        'Ссылка с поисковым запросом', 'Ссылка на объявление', 'Контакты',
        'ПФ в день', 'Старт', 'Крутим до', 'Номер заказа', 'Задача в биза',
        'ID клиента', 'Статус ссылки',
    ]
    assert captured["columns"][0][1] == 'фраза-1'
    assert captured["columns"][2][1] == 'Да'
    assert captured["columns"][3][1] == '20'
    assert captured["columns"][5][1] == '01.09.2026'
    assert captured["columns"][7][1] == 'biza-42'
    assert captured["columns"][8][1] == 1
    assert captured["columns"][9][1] == 'in_work'


def test_start_column_converts_to_msk_not_raw_utc_slice(tmp_db):
    """Регрессия: «Старт» обязан идти через _fmt_msk_date, а не сырой срез ISO.

    Вечерний UTC-запуск (23:30 UTC) в московском времени — это уже
    следующие сутки. Если бы колонка «Старт» строилась срезом первых 10
    символов started_at без конверсии в МСК, она показала бы UTC-дату —
    тест бы этого не заметил в другом сценарии, а тут ловит явно.
    """
    started_at = _iso_evening_days_ago(1)
    started_dt = datetime.fromisoformat(started_at)
    expected_msk_date = (started_dt + timedelta(hours=3)).strftime('%d.%m.%Y')
    raw_utc_date = started_dt.strftime('%d.%m.%Y')
    assert expected_msk_date != raw_utc_date  # sanity: сценарий действительно пересекает полночь

    _seed_link(tmp_db, delivery_mode='auto', started_at=started_at)

    _, captured = _run_export()

    assert captured["columns"][4][1] == expected_msk_date


def test_contacts_no_and_broken_position_name(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               contacts=0, position_name='мусор')

    _, captured = _run_export()

    assert captured["columns"][2][1] == 'Нет'
    assert captured["columns"][3][1] == ''


def test_missing_phrase_renders_empty_cell(tmp_db):
    _seed_link(tmp_db, delivery_mode='auto', started_at=_iso_days_ago(1),
               search_link=None)

    _, captured = _run_export()

    assert captured["columns"][0][1] == ''


def test_empty_selection_writes_headers_only(tmp_db):
    _, captured = _run_export()

    for col in captured["columns"]:
        assert len(col) == 1
