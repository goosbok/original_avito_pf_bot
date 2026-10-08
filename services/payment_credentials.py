"""Креды Юкассы: runtime-чтение из settings-таблицы, fallback — env.

До этого SHOP_ID/SECRET_KEY читались из env при импорте data.config —
смена кассы требовала правки .env и рестарта контейнеров. Теперь админ
может поменять Shop ID и секрет прямо из настроек бота: строки
`yookassa_shop_id` / `yookassa_secret_key` в settings приоритетнее env.
Пустая/отсутствующая строка → fallback на env (старое поведение).

Секрет в БД лежит открытым текстом — тот же уровень доверия, что .env
на этом же хосте; в UI показывается только маской (masked_secret).
"""
from __future__ import annotations

from data import config
from utils.sqlite3 import add_setting_to_base, get_setting

_SHOP_ID_KEY = "yookassa_shop_id"
_SECRET_KEY = "yookassa_secret_key"
_SHOP_ID_DESCR = "YooKassa Shop ID (касса)"
_SECRET_DESCR = "YooKassa secret key (касса)"


def shop_id() -> str:
    val = get_setting(_SHOP_ID_KEY)
    if val:
        return val
    return str(config.SHOP_ID) if config.SHOP_ID else ""


def secret_key() -> str:
    val = get_setting(_SECRET_KEY)
    if val:
        return val
    return config.SECRET_KEY or ""


def is_configured() -> bool:
    return bool(shop_id() and secret_key())


def source() -> str:
    """Откуда сейчас берутся креды: 'db' | 'env' | 'none'."""
    if get_setting(_SHOP_ID_KEY) and get_setting(_SECRET_KEY):
        return "db"
    if config.SHOP_ID and config.SECRET_KEY:
        return "env"
    return "none"


def set_shop_id(value: str) -> None:
    add_setting_to_base(_SHOP_ID_KEY, _SHOP_ID_DESCR, value.strip())


def set_secret_key(value: str) -> None:
    add_setting_to_base(_SECRET_KEY, _SECRET_DESCR, value.strip())


def masked_secret() -> str:
    """live_KG…DK8w — безопасно показывать в админке."""
    s = secret_key()
    if not s:
        return "—"
    if len(s) <= 13:
        return "***"
    return f"{s[:9]}…{s[-4:]}"
