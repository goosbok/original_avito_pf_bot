"""Order status notifications service.

Materializes status-change events as durable rows in `notifications`
(consumed by the LK bell feed) and pushes them to Telegram (best-effort).
"""
from __future__ import annotations

import logging
import sqlite3

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


def _connect() -> sqlite3.Connection:
    """Open a sqlite3 connection with row factory; honors test path overrides."""
    from utils.sqlite3 import path_db
    con = sqlite3.connect(path_db)
    con.row_factory = sqlite3.Row
    return con


def list_notifications(user_id: int, limit: int = 50) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, kind, order_id, new_status, text, created_at, read_at "
            "FROM notifications WHERE user_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def unread_count(user_id: int) -> int:
    with _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM notifications "
            "WHERE user_id = ? AND read_at IS NULL",
            (user_id,),
        ).fetchone()
    return int(row["c"])


def mark_all_read(user_id: int) -> int:
    with _connect() as con:
        cur = con.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND read_at IS NULL",
            (user_id,),
        )
        con.commit()
        return cur.rowcount
