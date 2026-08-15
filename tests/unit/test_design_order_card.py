"""Карточка заказа в боте: статус, дата, срок работы.

Регрессия: design.listord_array сверялся со старым значением статуса 'Posted',
которого после переименования (Posted→paid, Completed→done) в БД нет. Любой
заказ проваливался в else и показывался клиенту как «✅ Выполнен».
"""
import sqlite3

import pytest

from utils.dates import now_iso

# 09:08 UTC == 12:08 МСК — проверяем и конверсию таймзоны, и срез микросекунд.
_ORDER_DATE = "2026-08-11T09:08:21.959208+00:00"
_ORDER_DATE_DISPLAY = "11.08.2026 12:08"


def _seed_order(tmp_db, *, status="paid", date=_ORDER_DATE, links=()):
    """links — список (url, link_status, deadline_at)."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 100, 'tester')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) "
            "VALUES (1, 100, '7/50', ?, ?, 0, 'tester')",
            (status, date),
        )
        order_id = int(cur.lastrowid)
        for url, link_status, deadline_at in links:
            con.execute(
                "INSERT INTO order_links(order_id, url, status, deadline_at, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (order_id, url, link_status, deadline_at, now_iso()),
            )
        con.commit()
    return order_id


def _read_order(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        return dict(con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone())


def _card(tmp_db, **kwargs):
    from design import listord_array
    oid = _seed_order(tmp_db, **kwargs)
    return listord_array([_read_order(tmp_db, oid)])[0]


# ── статус ────────────────────────────────────────────────────────────────

def test_paid_order_shows_in_progress(tmp_db):
    card = _card(tmp_db, status="paid")
    assert "🔰 Статус: 🚀 В работе" in card
    assert "Выполнен" not in card


@pytest.mark.parametrize("status,expected", [
    ("done", "✅ Выполнен"),
    ("unpaid", "🕐 Ожидает оплаты"),
    ("failed", "❌ Ошибка накрутки"),
    ("payment_failed", "⌛ Не оплачен"),
    ("cancelled", "🚫 Отменён"),
])
def test_other_statuses_render_own_label(tmp_db, status, expected):
    assert f"🔰 Статус: {expected}" in _card(tmp_db, status=status)


# ── дата ──────────────────────────────────────────────────────────────────

def test_date_rendered_in_moscow_time_without_iso_noise(tmp_db):
    card = _card(tmp_db)
    assert f"🗓 Дата: {_ORDER_DATE_DISPLAY}" in card
    assert "T09:08" not in card
    assert "959208" not in card


# ── срок работы ───────────────────────────────────────────────────────────

def test_paid_order_shows_latest_deadline(tmp_db):
    card = _card(tmp_db, status="paid", links=[
        ("https://avito.ru/a", "in_work", "2026-08-16T05:00:00+00:00"),
        ("https://avito.ru/b", "in_work", "2026-08-18T05:00:00+00:00"),
    ])
    assert "⏳ Работает до: 18.08.2026" in card


def test_paid_order_without_deadlines_shows_awaiting_start(tmp_db):
    """Все ссылки ещё pending — накрутка стартует утром, это не аномалия."""
    card = _card(tmp_db, status="paid", links=[
        ("https://avito.ru/a", "pending", None),
    ])
    assert "⏳ Ожидает запуска" in card
    assert "Работает до" not in card


def test_done_order_has_no_deadline_line(tmp_db):
    card = _card(tmp_db, status="done", links=[
        ("https://avito.ru/a", "done", "2026-08-18T05:00:00+00:00"),
    ])
    assert "⏳" not in card


# ── order_text (карточка при удалении заказа) ─────────────────────────────

def test_order_text_translates_status_and_date(tmp_db):
    from design import order_text
    oid = _seed_order(tmp_db, status="paid")
    msg = order_text(_read_order(tmp_db, oid))
    assert "🚀 В работе" in msg
    assert _ORDER_DATE_DISPLAY in msg
    assert "959208" not in msg
