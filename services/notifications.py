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
    try:
        return tpl.format(**fields)
    except KeyError:
        logger.warning(
            "notifications: missing template field for kind=%s status=%s fields=%s",
            kind, new_status, sorted(fields.keys()),
        )
        return None


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


def _get_tg_id(user_id: int) -> int | None:
    """Test seam — wraps utils.sqlite3.get_tg_id_for_user."""
    from utils.sqlite3 import get_tg_id_for_user
    return get_tg_id_for_user(user_id)


async def _send_tg(*, tg_id: int, text: str, reply_markup) -> None:
    """Test seam — wraps data.loader.bot.send_message."""
    from data.loader import bot
    await bot.send_message(chat_id=tg_id, text=text, reply_markup=reply_markup)


def record_order_status_change(
    *,
    user_id: int,
    kind: str,
    order_id: int,
    old_status: str,
    new_status: str,
    **fields: object,
) -> str | None:
    """Sync: write durable notification row. Returns the rendered text, or None
    if the (kind, status) is not in the whitelist or status didn't change.
    Callers schedule push_tg_notification(user_id=, text=) for TG delivery."""
    if old_status == new_status:
        return None
    text = _build_text(kind, new_status, order_id=order_id, **fields)
    if text is None:
        return None
    with _connect() as con:
        con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, order_id, new_status, text),
        )
        con.commit()
    return text


async def push_tg_notification(*, user_id: int, text: str) -> None:
    """Best-effort: send text to user's Telegram with a 'Main menu' inline button."""
    try:
        tg_id = _get_tg_id(user_id)
        if tg_id is None:
            return
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"))
        await _send_tg(tg_id=tg_id, text=text, reply_markup=kb)
    except Exception:
        logger.exception("TG notify failed for user_id=%s", user_id)


async def notify_order_status_changed(
    *,
    user_id: int,
    kind: str,
    order_id: int,
    old_status: str,
    new_status: str,
    **fields: object,
) -> None:
    """High-level: sync DB row + async TG push, in that order."""
    text = record_order_status_change(
        user_id=user_id, kind=kind, order_id=order_id,
        old_status=old_status, new_status=new_status, **fields,
    )
    if text is None:
        return
    await push_tg_notification(user_id=user_id, text=text)
