"""Авторизация веб-клиента: Telegram Login Widget + JWT.

verify_telegram_auth — валидирует данные виджета по HMAC от bot token.
create_jwt / decode_jwt — выдают и проверяют наш собственный сессионный токен.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt

from web.config import (
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    TG_AUTH_MAX_AGE_SECONDS,
)


class AuthError(Exception):
    """Не удалось проверить подпись или токен истёк."""


def verify_telegram_auth(data: dict[str, Any], bot_token: str) -> int:
    """Проверить подпись Telegram Login Widget и вернуть user_id.

    Бросает AuthError если подпись неверна или auth_date устарел.
    """
    if "hash" not in data:
        raise AuthError("missing 'hash'")

    received_hash = data["hash"]
    payload = {k: v for k, v in data.items() if k != "hash"}

    if "auth_date" not in payload:
        raise AuthError("missing 'auth_date'")
    try:
        auth_date = int(payload["auth_date"])
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'auth_date'") from exc

    if time.time() - auth_date > TG_AUTH_MAX_AGE_SECONDS:
        raise AuthError("auth_date is too old")

    data_check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise AuthError("hash mismatch")

    if "id" not in payload:
        raise AuthError("missing 'id'")
    try:
        return int(payload["id"])
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'id'") from exc


def create_jwt(user_id: int, secret: str, expires_hours: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours or JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": exp}
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str, secret: str) -> int:
    try:
        payload = pyjwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    sub = payload.get("sub")
    if sub is None:
        raise AuthError("missing 'sub'")
    try:
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'sub'") from exc
