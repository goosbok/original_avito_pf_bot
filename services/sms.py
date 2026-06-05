"""SMS gateway abstraction.

Конкретный провайдер выбирается через env `SMS_GATEWAY`:
- `stub` (default) — `StubSmsGateway`, логирует код в лог и хранит in-memory.
  Используется в dev/тестах. Реальная отправка не происходит.
- иные значения зарезервированы под будущие реальные провайдеры
  (SMSC.ru, Smsaero и т.п.); пока вызов `get_gateway()` для них валится
  ValueError, чтобы случайная опечатка в env не уходила в продакшен под видом stub.

Singleton: `get_gateway()` кеширует первый созданный экземпляр. В тестах
используйте `_reset_for_tests()` (см. tests/unit/test_sms.py).
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class SmsGateway(Protocol):
    def send_code(self, phone: str, code: str) -> None: ...


class StubSmsGateway:
    """Логирует код вместо реальной отправки. Для разработки и тестов."""

    def __init__(self) -> None:
        self.last_codes: dict[str, str] = {}

    def send_code(self, phone: str, code: str) -> None:
        self.last_codes[phone] = code
        logger.info("STUB SMS to %s: code=%s", phone, code)


_singleton: SmsGateway | None = None


def get_gateway() -> SmsGateway:
    """Возвращает singleton SmsGateway согласно env SMS_GATEWAY (default=stub)."""
    global _singleton
    if _singleton is not None:
        return _singleton
    name = os.getenv("SMS_GATEWAY", "stub")
    if name == "stub":
        _singleton = StubSmsGateway()
    else:
        raise ValueError(
            f"unknown SMS_GATEWAY={name!r}. Реализуйте провайдер в services/sms.py"
        )
    return _singleton


def _reset_for_tests() -> None:
    """Сбрасывает singleton — нужен тестам, использующим monkeypatch на env."""
    global _singleton
    _singleton = None
