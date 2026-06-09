"""Уведомления об успешном пополнении: юзеру, админам, рефералу.

Выделены из handlers/refill.py чтобы и TG-handler, и web-flow, и крон-reconciler
отправляли консистентные сообщения. Все функции async, идемпотентны (можно
вызывать повторно), и НЕ ПАДАЮТ, если получатель недоступен.
"""
from __future__ import annotations

import logging

from data.loader import bot
from services.db import connect
from utils.other import format_decimal, get_user_string_without_first_name
from utils.sender import send_admins
from utils.sqlite3 import get_user, get_string

logger = logging.getLogger(__name__)


def _get_tg_chat_id(user_id: int) -> int | None:
    """Возвращает chat_id юзера в Telegram через auth_providers, или None если web-only."""
    with connect() as con:
        row = con.execute(
            "SELECT identifier FROM auth_providers "
            "WHERE user_id = ? AND provider = 'telegram' LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        return int(row["identifier"])
    except (TypeError, ValueError):
        logger.warning("auth_providers.identifier non-int for user_id=%s: %r",
                       user_id, row["identifier"])
        return None


async def notify_user_success(user_id: int, amount: int, new_balance: int) -> None:
    """STR2 — личное сообщение юзеру об успешном пополнении.

    No-op для web-only юзеров без telegram auth_provider.
    Не падает при send_message exception (юзер заблокировал бота и т.п.).
    """
    chat_id = _get_tg_chat_id(user_id)
    if chat_id is None:
        logger.info("notify_user_success: skip user_id=%s (no telegram provider)", user_id)
        return
    f_amount = format_decimal(amount)
    f_balance = format_decimal(new_balance)
    text = get_string("str_usr_pay_success").format(f_amount, f_balance)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("notify_user_success: send_message failed user_id=%s chat_id=%s",
                       user_id, chat_id, exc_info=True)


async def notify_admins_success(user_id: int, amount: int, new_balance: int) -> None:
    """STR3 — пост в админский топик 'orders' об успешном пополнении."""
    usr = get_user(id=user_id)
    if usr is None:
        logger.warning("notify_admins_success: user not found user_id=%s", user_id)
        return
    user_string = await get_user_string_without_first_name(usr)
    f_amount = format_decimal(amount)
    f_balance = format_decimal(new_balance)
    text = get_string("str_adm_pay_success").format(f_amount, user_string, f_balance)
    try:
        await send_admins(text, "orders")
    except Exception:
        logger.warning("notify_admins_success: send_admins failed user_id=%s",
                       user_id, exc_info=True)


async def notify_referrer(referrer_id: int, bonus: int, new_balance: int) -> None:
    """STR4 — личное сообщение рефералу о начисленном бонусе."""
    chat_id = _get_tg_chat_id(referrer_id)
    if chat_id is None:
        logger.info("notify_referrer: skip referrer_id=%s (no telegram provider)",
                    referrer_id)
        return
    f_bonus = format_decimal(bonus)
    f_balance = format_decimal(new_balance)
    text = get_string("str_ref_balance_refil").format(f_bonus, f_balance)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("notify_referrer: send_message failed referrer_id=%s chat_id=%s",
                       referrer_id, chat_id, exc_info=True)
