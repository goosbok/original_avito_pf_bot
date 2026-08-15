"""Единый справочник orders.status → человекочитаемая подпись."""
import pytest


@pytest.mark.parametrize("status,expected", [
    ("unpaid", "🕐 Ожидает оплаты"),
    ("paid", "🚀 В работе"),
    ("done", "✅ Выполнен"),
    ("failed", "❌ Ошибка накрутки"),
    ("payment_failed", "⌛ Не оплачен"),
    ("cancelled", "🚫 Отменён"),
])
def test_known_statuses_have_russian_labels(status, expected):
    from utils.order_status import order_status_label
    assert order_status_label(status) == expected


def test_unknown_status_passes_through_verbatim():
    """Неизвестный статус лучше показать как есть, чем спрятать за прочерком —
    иначе рассинхрон кода и БД снова останется незамеченным."""
    from utils.order_status import order_status_label
    assert order_status_label("something_new") == "something_new"


def test_empty_status_renders_dash():
    from utils.order_status import order_status_label
    assert order_status_label(None) == "—"
    assert order_status_label("") == "—"


def test_paid_is_not_labelled_as_done():
    """Регрессия: заказ в работе показывался клиенту как «Выполнен»."""
    from utils.order_status import order_status_label
    assert "Выполнен" not in order_status_label("paid")
