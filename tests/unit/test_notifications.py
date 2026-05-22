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
