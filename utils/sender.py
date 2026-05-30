"""Send admin notifications routed by category to forum topics."""
from __future__ import annotations

from typing import Literal, Optional

from aiogram.types import Message

import data.config as config
from data.loader import bot

Category = Literal["questions", "orders", "errors", "new_users"]

_CATEGORY_TO_CONFIG_ATTR: dict[str, str] = {
    "questions": "SUPPORT_THREAD_QUESTIONS",
    "orders":    "SUPPORT_THREAD_ORDERS",
    "errors":    "SUPPORT_THREAD_ERRORS",
    "new_users": "SUPPORT_THREAD_NEW_USERS",
}


def _resolve_thread_id(category: str) -> int:
    attr = _CATEGORY_TO_CONFIG_ATTR.get(category)
    if attr is None:
        raise ValueError(f"unknown category: {category!r}")
    return int(getattr(config, attr, 0) or 0)


async def send_admins(
    msg: str,
    category: Category,
    *,
    parse_mode: Optional[str] = None,
) -> Optional[Message]:
    """Send `msg` to the support group's forum topic for `category`.

    Returns the sent Message, or None if the topic is not configured
    (so callers like support.py can decide whether to persist message_id).
    """
    thread_id = _resolve_thread_id(category)
    if thread_id == 0:
        return None
    return await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=msg,
        message_thread_id=thread_id,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )


async def validate_support_topics() -> None:
    """Validate forum-topic configuration at bot startup.

    Raises SystemExit if SUPPORT_THREAD_ERRORS is unset — without it we have no
    place to surface other misconfiguration alerts. For any other unset category,
    emit a single ⚠️ warning into the errors topic and continue: the corresponding
    send_admins() calls will then be silent no-ops.
    """
    errors_thread = int(getattr(config, "SUPPORT_THREAD_ERRORS", 0) or 0)
    if errors_thread == 0:
        raise SystemExit(
            "SUPPORT_THREAD_ERRORS must be configured (forum topic id) — "
            "without it the bot has no channel for runtime alerts."
        )

    for category, attr in _CATEGORY_TO_CONFIG_ATTR.items():
        if category == "errors":
            continue
        if int(getattr(config, attr, 0) or 0) == 0:
            await send_admins(
                f"⚠️ <b>{attr} не задан</b>\n"
                f"Сообщения категории {category} не будут отправляться в группу.",
                "errors",
                parse_mode="HTML",
            )
