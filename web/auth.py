"""JWT-helpers для веб-аутентификации.

Telegram Login Widget verify удалён — теперь логин через OTP (см. routers/auth_telegram.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from web.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_SECRET


def create_jwt(user_id: int, *, secret: str | None = None, expire_hours: int | None = None) -> str:
    """Сгенерировать JWT с internal user_id."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expire_hours or JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, secret or JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str, *, secret: str | None = None) -> int:
    """Декодировать JWT и вернуть user_id. Бросает jwt.InvalidTokenError."""
    payload = jwt.decode(token, secret or JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
