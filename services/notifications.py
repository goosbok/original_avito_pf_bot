"""Order status notifications service.

Materializes status-change events as durable rows in `notifications`
(consumed by the LK bell feed) and pushes them to Telegram (best-effort).
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

_TEMPLATES: dict[tuple[str, str], str] = {
    ("order", "paid"):           "📌 Заказ №{order_id} оплачен и принят в работу.",
    ("order", "done"):           "✅ Заказ №{order_id} выполнен.",
    ("order", "failed"):         "❌ Заказ №{order_id} не выполнен. Свяжитесь с поддержкой.",
    ("order", "payment_failed"): "⏱ Заказ №{order_id} не оплачен в срок.",
    ("order", "cancelled"):      "🚫 Заказ №{order_id} отменён.",
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


# === Admin "new order" push ===

_NEW_ORDER_SOURCE_LABEL: dict[str, str] = {
    "telegram": "🤖 Бот",
    "web": "🌐 Веб",
    "api": "🔌 API",
}


async def notify_new_order(order_id: int, *, source: str) -> None:
    """Push a 'new order placed' message to the admin orders chat.

    `source` ∈ {'telegram', 'web', 'api'} — appended as a postfix line so the
    admin chat can tell where the order came from. Not persisted; known at the
    call site (TG handler vs web route).

    Best-effort: any exception is logged and swallowed — callers should not
    block on this. Schedule AFTER the order has flipped to 'paid'.
    """
    from utils.sender import send_admins
    from utils.other import (
        format_decimal,
        get_user_string_without_first_name,
        split_messages,
    )
    from utils.dates import format_display
    from utils.sqlite3 import get_user, get_string
    from services.orders import get_order
    from services.order_links import list_links as _list_links

    try:
        order = get_order(order_id)
        user = get_user(id=int(order["user_id"]))
        if not user:
            logger.warning(
                "notify_new_order: user %s not found for order %s",
                order["user_id"], order_id,
            )
            return

        ord_id = order["increment"]
        f_price = format_decimal(order["price"])
        user_str = await get_user_string_without_first_name(user)
        pos_name = order["position_name"]
        status = order["status"]
        con_str = "Да" if order["contacts"] else "Нет"
        ord_date = format_display(order["date"])
        link_rows = _list_links(ord_id)
        links_cnt = len(link_rows)
        links_str = "".join(f"\n<code>{ln['url']}</code>" for ln in link_rows)

        tpl = get_string("str_new_order_text")
        msg = tpl.format(
            ord_id, f_price, user_str, pos_name, status,
            con_str, ord_date, links_cnt, links_str,
        )
        msg += f"\n📍 Источник: {_NEW_ORDER_SOURCE_LABEL.get(source, source)}"

        if len(msg) < 4096:
            await send_admins(msg, "orders")
        else:
            for chunk in split_messages(msg.split("\n"), "\n"):
                await send_admins(chunk, "orders")
    except Exception:
        logger.warning(
            "notify_new_order failed for order=%s source=%s",
            order_id, source, exc_info=True,
        )
