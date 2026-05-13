"""/connect — opt-in phone linking so users can log in to the web SPA by phone.

Flow:
- /connect: bot shows a ReplyKeyboard with `request_contact=True` button.
- User taps button → Telegram sends a Contact message with `phone_number` + `user_id`.
- We verify the contact belongs to the sender and store provider=phone in auth_providers.
"""
from __future__ import annotations

import logging
import re

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
from services.exceptions import ProviderAlreadyLinked

logger = logging.getLogger(__name__)

_NON_DIGIT_RE = re.compile(r"[^\d]+")


def _normalize_phone(raw: str) -> str:
    """Telegram contact.phone_number может быть без '+'. Возвращает '+<digits>'."""
    digits = _NON_DIGIT_RE.sub("", raw or "")
    return f"+{digits}" if digits else ""


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

    phone = _normalize_phone(contact.phone_number or "")
    if not phone or len(phone) < 6:
        await message.answer(
            "Не удалось разобрать номер. Попробуйте ещё раз: /connect",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    try:
        identity.link_provider(user_id, "phone", phone, credential_hash=None)
    except ProviderAlreadyLinked as exc:
        logger.info(
            "phone %s already linked to user %s (current user %s)",
            phone, exc.existing_user_id, user_id,
        )
        await message.answer(
            "❌ Этот номер уже привязан к другому аккаунту. "
            "Если это вы — войдите по нему и отвяжите его в личном кабинете.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    except Exception:
        logger.exception("link_provider(phone) failed for user %s", user_id)
        await message.answer(
            "⚠️ Не удалось сохранить номер. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(
        "✅ Готово. Теперь на сайте введите этот номер для входа через Telegram.",
        reply_markup=ReplyKeyboardRemove(),
    )
