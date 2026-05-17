"""Central error-handling utility for bot handlers.

Usage in a handler:
    except Exception as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "confirm_order", "user_id": user_id, "data": dict(data)},
            reply_target=call,   # Message or CallbackQuery
        )
        await state.finish()
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

_log = logging.getLogger(__name__)

ERROR_MSG = (
    "⚠️ К сожалению, во время операции произошла ошибка.\n\n"
    "Мы уже ведём работы по её устранению. "
    "Если с вас были списаны деньги, а услуга недоступна — "
    "напишите нам в поддержку."
)


def error_kb() -> InlineKeyboardMarkup:
    """Keyboard with Main Menu and Support buttons for error replies."""
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"),
        InlineKeyboardButton(text="💬 Поддержка", callback_data="info:support"),
    )
    return kb


async def report_handler_error(
    exc: Exception,
    *,
    logger: logging.Logger,
    context: dict[str, Any],
    reply_target: "types.Message | types.CallbackQuery | None" = None,
) -> None:
    """Log exc at ERROR with context vars, alert admins, reply to user.

    Never raises — all failures inside are caught and logged at WARNING.
    """
    ctx_str = " | ".join(f"{k}={v!r}" for k, v in context.items())
    logger.error("handler error: %s | %s", exc, ctx_str, exc_info=True)

    # Alert admins (best-effort)
    try:
        from utils.sender import send_admins  # lazy to avoid circular import at test time
        alert = (
            f"🚨 <b>Ошибка в боте</b>\n"
            f"<code>{type(exc).__name__}: {exc}</code>\n"
            f"<b>Контекст:</b> <code>{ctx_str[:300]}</code>"
        )
        await send_admins(alert)
    except Exception as alert_exc:
        _log.warning("report_handler_error: send_admins failed: %s", alert_exc)

    # Reply to user (best-effort)
    if reply_target is not None:
        try:
            kb = error_kb()
            # Detect CallbackQuery vs Message.
            # For real aiogram objects isinstance() is exact.
            # For duck-typed objects (e.g. test mocks) we check whether a
            # `.message` attribute was explicitly set on the object (stored in
            # __dict__) rather than lazily created by getattr/mock machinery.
            is_callback = isinstance(reply_target, types.CallbackQuery) or (
                not isinstance(reply_target, types.Message)
                and "message" in getattr(reply_target, "__dict__", {})
            )
            if is_callback:
                await reply_target.message.answer(ERROR_MSG, reply_markup=kb)
            else:
                await reply_target.answer(ERROR_MSG, reply_markup=kb)
        except Exception as reply_exc:
            _log.warning("report_handler_error: failed to reply to user: %s", reply_exc)
