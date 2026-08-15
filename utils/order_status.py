"""Единая точка перевода orders.status в подпись для человека.

До этого перевод был размазан по трём местам (карточка бота, карточка админки,
StatusBadge в вебе) и разъехался: design.py остался на дореформенном значении
'Posted' и после переименования Posted→paid / Completed→done показывал клиенту
«✅ Выполнен» на любом заказе. Подписи держим здесь; JS-копия в
web/static/components/Cabinet.jsx должна совпадать по смыслу.

Жизненный цикл статусов описан в services/orders.py.
"""
from __future__ import annotations

ORDER_STATUS_LABELS: dict[str, str] = {
    "unpaid": "🕐 Ожидает оплаты",
    "paid": "🚀 В работе",
    "done": "✅ Выполнен",
    "failed": "❌ Ошибка накрутки",
    "payment_failed": "⌛ Не оплачен",
    "cancelled": "🚫 Отменён",
}


def order_status_label(status: str | None) -> str:
    """Подпись статуса заказа. Неизвестный статус возвращаем как есть —
    молчаливая подмена и привела к тому, что рассинхрон кода с БД жил месяцами."""
    if not status:
        return "—"
    return ORDER_STATUS_LABELS.get(status, status)
