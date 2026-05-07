"""Telegram OTP login/link flow.

request_code:
- identifier: либо numeric telegram_id, либо @username (ищем в users.user_name).
- Генерируем код через services.otp, отправляем юзеру через Telegram Bot HTTP API.

verify_code:
- Юзер вводит идентификатор + код. Сверяем. На успех — get_or_create_user_by_telegram.
"""
from __future__ import annotations

import re

import httpx

from services import identity, otp
from services.db import connect
from services.exceptions import BotCantReachUser, OTPInvalid


# Telegram's official minimum is 5, but we relax to 1 to support short test usernames
# (e.g. "bob") and avoid false rejects for names stored in our own DB.
_USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{1,32})$")


def resolve_telegram_id(identifier: str) -> int:
    """Превратить введённое юзером в telegram_id.

    Поддерживается:
    - numeric ID (как-есть)
    - @username или username (ищем в users.user_name; если не нашли — OTPInvalid).
    """
    identifier = identifier.strip()
    if identifier.isdigit():
        return int(identifier)
    m = _USERNAME_RE.match(identifier)
    if not m:
        raise OTPInvalid(f"unknown identifier format: {identifier!r}")
    username = m.group(1)
    with connect() as con:
        # users.user_name из бота хранится без @
        row = con.execute(
            "SELECT id FROM users WHERE LOWER(user_name) = LOWER(?)",
            (username,),
        ).fetchone()
    if row is None:
        raise OTPInvalid("telegram user not found in our system; start the bot first")
    return int(row["id"])


def _send_telegram_message(bot_token: str, telegram_id: int, text: str) -> None:
    """Отправить сообщение через Bot HTTP API. На сетевые ошибки — RuntimeError."""
    from data import config
    base = getattr(config, "BOT_HTTP_API_BASE", "https://api.telegram.org")
    url = f"{base}/bot{bot_token}/sendMessage"
    try:
        resp = httpx.post(url, json={"chat_id": telegram_id, "text": text}, timeout=10.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"bot send failed: {exc}") from exc
    if resp.status_code == 200:
        return
    error_text = resp.text.lower()
    if "chat not found" in error_text or "bot was blocked" in error_text or resp.status_code == 403:
        raise BotCantReachUser(
            f"Не удалось отправить код: бот не может написать пользователю {telegram_id}. "
            f"Убедитесь, что вы начали диалог с ботом."
        )
    raise RuntimeError(f"bot send returned {resp.status_code}: {resp.text}")


def request_code(
    identifier: str,
    *,
    purpose: str = "login",
    user_id_to_link: int | None = None,
) -> int:
    """Resolve identifier → telegram_id, generate code, send via bot. Return telegram_id."""
    from web.config import BOT_TOKEN

    tg_id = resolve_telegram_id(identifier)
    code = otp.request_code(purpose, tg_id, user_id_to_link=user_id_to_link)
    text = f"Ваш код подтверждения: {code}\n\nДействителен 5 минут."
    _send_telegram_message(BOT_TOKEN, tg_id, text)
    return tg_id


def verify_code_login(identifier: str, code: str) -> int:
    """Проверить код для логина. Возвращает internal user_id (создаёт юзера, если нужно)."""
    tg_id = resolve_telegram_id(identifier)
    otp.verify_code("login", tg_id, code)

    user_name = _lookup_username(tg_id)
    return identity.get_or_create_user_by_telegram(tg_id, user_name=user_name)


def verify_code_link(identifier: str, code: str, current_user_id: int) -> None:
    """Проверить код для привязки telegram к current_user_id."""
    tg_id = resolve_telegram_id(identifier)
    expected = otp.verify_code("link", tg_id, code)
    if expected is not None and expected != current_user_id:
        raise OTPInvalid("code was issued for a different user")
    identity.link_provider(current_user_id, "telegram", str(tg_id))


def _lookup_username(tg_id: int) -> str | None:
    with connect() as con:
        row = con.execute("SELECT user_name FROM users WHERE id = ?", (tg_id,)).fetchone()
    return row["user_name"] if row else None
