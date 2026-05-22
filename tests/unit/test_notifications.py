"""Tests for services.notifications."""
from __future__ import annotations

import pytest


def test_build_text_order_posted():
    from services.notifications import _build_text
    assert _build_text("order", "Posted", order_id=5) == "📌 Заказ №5 размещён."


def test_build_text_order_completed():
    from services.notifications import _build_text
    assert _build_text("order", "Completed", order_id=42) == "✅ Заказ №42 выполнен."


def test_build_text_order_cancelled():
    from services.notifications import _build_text
    assert _build_text("order", "Cancelled", order_id=7) == "❌ Заказ №7 отменён."


def test_build_text_order_review_completed():
    from services.notifications import _build_text
    assert _build_text(
        "order_review", "Completed", order_id=3, service="Avito",
    ) == "🎉 Заказ №3 на отзыв (Avito) выполнен."


def test_build_text_order_delreview_completed():
    from services.notifications import _build_text
    assert _build_text(
        "order_delreview", "Completed", order_id=9, service="Yandex",
    ) == "🎉 Заказ №9 на удаление отзыва (Yandex) выполнен."


def test_build_text_unknown_status_returns_none():
    from services.notifications import _build_text
    assert _build_text("order", "Pending", order_id=1) is None
    assert _build_text("order", "In progress", order_id=1) is None


def test_build_text_unknown_kind_returns_none():
    from services.notifications import _build_text
    assert _build_text("guest_order", "Completed", order_id=1) is None


def test_build_text_review_with_cancelled_not_supported():
    from services.notifications import _build_text
    assert _build_text("order_review", "Cancelled", order_id=1, service="x") is None


def _insert_notification(tmp_db, *, user_id: int, kind: str = "order",
                        order_id: int = 1, new_status: str = "Completed",
                        text: str = "test", read_at: str | None = None) -> int:
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text, read_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kind, order_id, new_status, text, read_at),
        )
        con.commit()
        return cur.lastrowid


def test_list_notifications_empty(tmp_db):
    from services.notifications import list_notifications
    assert list_notifications(user_id=42) == []


def test_list_notifications_orders_desc_by_id(tmp_db):
    from services.notifications import list_notifications
    a = _insert_notification(tmp_db, user_id=1, text="first")
    b = _insert_notification(tmp_db, user_id=1, text="second")
    rows = list_notifications(user_id=1)
    assert [r["id"] for r in rows] == [b, a]
    assert rows[0]["text"] == "second"


def test_list_notifications_filters_by_user(tmp_db):
    from services.notifications import list_notifications
    _insert_notification(tmp_db, user_id=1, text="alice")
    _insert_notification(tmp_db, user_id=2, text="bob")
    rows = list_notifications(user_id=1)
    assert len(rows) == 1
    assert rows[0]["text"] == "alice"


def test_list_notifications_respects_limit(tmp_db):
    from services.notifications import list_notifications
    for i in range(5):
        _insert_notification(tmp_db, user_id=1, text=f"n{i}")
    assert len(list_notifications(user_id=1, limit=3)) == 3


def test_unread_count_excludes_read(tmp_db):
    from services.notifications import unread_count
    _insert_notification(tmp_db, user_id=1, text="unread1")
    _insert_notification(tmp_db, user_id=1, text="unread2")
    _insert_notification(tmp_db, user_id=1, text="read",
                        read_at="2026-05-22 10:00:00")
    assert unread_count(user_id=1) == 2


def test_unread_count_filters_by_user(tmp_db):
    from services.notifications import unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=2)
    assert unread_count(user_id=1) == 1


def test_mark_all_read_sets_timestamp(tmp_db):
    import sqlite3
    from services.notifications import mark_all_read, unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=1)
    assert mark_all_read(user_id=1) == 2
    assert unread_count(user_id=1) == 0
    with sqlite3.connect(tmp_db) as con:
        read_ats = [r[0] for r in con.execute(
            "SELECT read_at FROM notifications WHERE user_id = 1"
        )]
    assert all(t is not None for t in read_ats)


def test_mark_all_read_idempotent(tmp_db):
    from services.notifications import mark_all_read
    _insert_notification(tmp_db, user_id=1)
    assert mark_all_read(user_id=1) == 1
    assert mark_all_read(user_id=1) == 0


def test_mark_all_read_only_current_user(tmp_db):
    from services.notifications import mark_all_read, unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=2)
    assert mark_all_read(user_id=1) == 1
    assert unread_count(user_id=2) == 1
