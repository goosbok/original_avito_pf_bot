"""/connect — opt-in phone linking so users can log in to the web SPA by phone.

Flow:
- /connect: bot shows a ReplyKeyboard with `request_contact=True` button.
- User taps button → Telegram sends a Contact message with `phone_number` + `user_id`.
- We verify the contact belongs to the sender and store provider=phone in auth_providers.
"""
from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import (
    ContentType,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from data.loader import dp
from services import identity
from services.exceptions import AccountMergeConflict
from utils.phones import normalize_phone

logger = logging.getLogger(__name__)


def _contact_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton(text="📱 Поделиться контактом", request_contact=True))
    return kb


async def prompt_for_contact(message: Message) -> None:
    """Send the share-contact prompt + keyboard. Reused by /connect AND
    /start connect deep-link from the web SPA."""
    await message.answer(
        "📱 Чтобы заходить на сайт по номеру телефона, "
        "поделитесь контактом кнопкой ниже.",
        reply_markup=_contact_keyboard(),
    )


@dp.message_handler(commands=["connect"], state="*")
async def cmd_connect(message: Message, state: FSMContext) -> None:
    """Prompt the user to share their phone number."""
    await state.finish()
    await prompt_for_contact(message)


@dp.message_handler(content_types=ContentType.CONTACT, state="*")
async def on_contact(message: Message, state: FSMContext, user_id: int) -> None:
    """Handle the Contact share sent in response to /connect."""
    contact = message.contact
    if contact is None:
        return

    # Only accept the sender's own contact.
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Можно делиться только своим контактом",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    phone = normalize_phone(contact.phone_number or "")
    if not phone:
        await message.answer(
            "Не удалось разобрать номер. Попробуйте ещё раз: /connect",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Telegram-shared контакт = подтверждённый владелец номера → verified=True.
    # link_phone_provider сам резолвит коллизию: если phone привязан к phone-only
    # юзеру (от быстрого заказа), его orders/refills/notifications/balance
    # автоматически мерджатся в текущего user'а. Конфликт (AccountMergeConflict)
    # бросается только если phone уже принадлежит полноценному чужому аккаунту.
    try:
        identity.link_phone_provider(user_id, phone, set_verified=True)
    except AccountMergeConflict as exc:
        logger.warning(
            "phone-merge conflict: phone=%s already on user_id=%s (current user_id=%s)",
            phone, exc.existing_user_id, user_id,
        )
        await message.answer(
            "⚠️ Этот номер уже привязан к другому аккаунту. "
            "Свяжитесь с поддержкой для слияния — мы поможем переехать.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    except Exception:
        logger.exception("link_phone_provider(%s) failed for user %s", phone, user_id)
        await message.answer(
            "⚠️ Не удалось сохранить номер. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    from data import config as bot_config
    site_url = getattr(bot_config, "SITE_URL", "")
    if site_url:
        await message.answer(
            f'✅ Готово. <a href="{site_url}">Вернитесь на сайт</a> '
            "и войдите по этому номеру телефона.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "✅ Готово. Теперь на сайте введите этот номер для входа через Telegram.",
            reply_markup=ReplyKeyboardRemove(),
        )
