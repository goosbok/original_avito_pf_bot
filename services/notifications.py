"""Order status notifications service.

Materializes status-change events as durable rows in `notifications`
(consumed by the LK bell feed) and pushes them to Telegram (best-effort).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TEMPLATES: dict[tuple[str, str], str] = {
    ("order", "Posted"):    "📌 Заказ №{order_id} размещён.",
    ("order", "Completed"): "✅ Заказ №{order_id} выполнен.",
    ("order", "Cancelled"): "❌ Заказ №{order_id} отменён.",
    ("order_review", "Completed"):
        "🎉 Заказ №{order_id} на отзыв ({service}) выполнен.",
    ("order_delreview", "Completed"):
        "🎉 Заказ №{order_id} на удаление отзыва ({service}) выполнен.",
}


def _build_text(kind: str, new_status: str, **fields: object) -> str | None:
    tpl = _TEMPLATES.get((kind, new_status))
    if tpl is None:
        return None
    return tpl.format(**fields)
