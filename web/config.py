"""Конфигурация веб-приложения.

Берём secrets из env (если есть) либо из data/config.py. Это даёт два режима:
- prod: переменные окружения переопределяют значения из конфига;
- dev: достаточно прописать значения в data/config.py.
"""
from __future__ import annotations

import os

from data import config as bot_config


def _env_or_default(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


BOT_TOKEN: str = _env_or_default("BOT_TOKEN", bot_config.TOKEN) or ""

JWT_SECRET: str = _env_or_default(
    "JWT_SECRET",
    getattr(bot_config, "JWT_SECRET", None),
) or ""
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_HOURS: int = int(_env_or_default("JWT_EXPIRE_HOURS", "24") or "24")

WEB_HOST: str = _env_or_default("WEB_HOST", "127.0.0.1") or "127.0.0.1"
WEB_PORT: int = int(_env_or_default("WEB_PORT", "8000") or "8000")

TG_AUTH_MAX_AGE_SECONDS: int = 86_400


def assert_configured() -> None:
    """Падать рано, если запускаем без секретов."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty — set in env or data/config.py")
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError(
            "JWT_SECRET is empty or shorter than 32 chars — set a strong secret"
        )
