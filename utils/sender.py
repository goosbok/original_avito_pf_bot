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


def assert_errors_topic_configured() -> None:
    """Verify SUPPORT_THREAD_ERRORS is set before starting the bot.

    Raises SystemExit when the errors topic id is 0 — without it the bot has no
    channel to surface runtime alerts. Synchronous so it can be called from
    `__main__` *before* `executor.start_polling`, which would otherwise swallow
    a SystemExit raised inside an async on_startup hook.
    """
    if int(getattr(config, "SUPPORT_THREAD_ERRORS", 0) or 0) == 0:
        raise SystemExit(
            "SUPPORT_THREAD_ERRORS must be configured (forum topic id) — "
            "without it the bot has no channel for runtime alerts."
        )


async def warn_missing_support_topics() -> None:
    """For each non-errors category whose thread id is 0, send a ⚠️ warning to the
    errors topic. Failures are logged and swallowed so a transient startup network
    blip cannot crash the bot into a restart loop.
    """
    import logging

    log = logging.getLogger(__name__)

    for category, attr in _CATEGORY_TO_CONFIG_ATTR.items():
        if category == "errors":
            continue
        if int(getattr(config, attr, 0) or 0) == 0:
            try:
                await send_admins(
                    f"⚠️ <b>{attr} не задан</b>\n"
                    f"Сообщения категории {category} не будут отправляться в группу.",
                    "errors",
                    parse_mode="HTML",
                )
            except Exception:
                log.warning(
                    "warn_missing_support_topics: failed to send warning for %s",
                    attr,
                    exc_info=True,
                )
