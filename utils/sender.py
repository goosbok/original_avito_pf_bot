"""Send admin notifications routed by category to forum topics."""
from __future__ import annotations

from typing import Literal, Optional

from aiogram.types import Message

import data.config as config
from data.loader import bot

Category = Literal["questions", "orders", "orders_web", "errors", "new_users"]

_CATEGORY_TO_CONFIG_ATTR: dict[str, str] = {
    "questions":  "SUPPORT_THREAD_QUESTIONS",
    "orders":     "SUPPORT_THREAD_ORDERS",
    "orders_web": "SUPPORT_THREAD_ORDERS_WEB",
    "errors":     "SUPPORT_THREAD_ERRORS",
    "new_users":  "SUPPORT_THREAD_NEW_USERS",
}

# Transparent (no prefix) fallback chain when a category's topic is unset.
# orders_web → orders → errors (the final errors fallback is handled below).
_CATEGORY_FALLBACK: dict[str, str] = {
    "orders_web": "orders",
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

    Fallback chain when the primary topic is unset (thread id == 0):
    1. If the category has a transparent fallback (see _CATEGORY_FALLBACK), try
       that category's topic silently — no warning prefix.
    2. Otherwise reroute into the errors topic with an explanatory prefix so
       admins can still see it.
    Returns the sent Message, or None if no usable topic was found.
    """
    thread_id = _resolve_thread_id(category)
    if thread_id != 0:
        return await bot.send_message(
            chat_id=config.SUPPORT_CHAT_ID,
            text=msg,
            message_thread_id=thread_id,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    # Step 1: transparent intermediate fallback (e.g. orders_web → orders).
    if category in _CATEGORY_FALLBACK:
        intermediate = _CATEGORY_FALLBACK[category]
        intermediate_thread = _resolve_thread_id(intermediate)
        if intermediate_thread != 0:
            return await bot.send_message(
                chat_id=config.SUPPORT_CHAT_ID,
                text=msg,
                message_thread_id=intermediate_thread,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )

    # Step 2: final fallback — errors topic with prefix.
    if category == "errors":
        return None  # cannot fall back to ourselves
    errors_thread = int(getattr(config, "SUPPORT_THREAD_ERRORS", 0) or 0)
    if errors_thread == 0:
        return None  # nothing to fall back to
    fallback_msg = (
        f"⚠️ Не задан топик для {category}, вот текст уведомления:\n\n"
        f"{msg}"
    )
    return await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=fallback_msg,
        message_thread_id=errors_thread,
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
        if category in _CATEGORY_FALLBACK:
            continue  # optional — silently uses fallback when unset
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
