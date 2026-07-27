"""SMS gateway abstraction.

Конкретный провайдер выбирается через env `SMS_GATEWAY`:
- `stub` (default) — `StubSmsGateway`, логирует код в лог и хранит in-memory.
  Используется в dev/тестах. Реальная отправка не происходит.
- `smspilot` — `SmspilotGateway`, реальная отправка через SMSPILOT API-1
  (https://smspilot.ru/apikey.php). Требует env `SMSPILOT_APIKEY`.
- иные значения зарезервированы под будущие реальные провайдеры; пока вызов
  `get_gateway()` для них валится ValueError, чтобы случайная опечатка в env
  не уходила в продакшен под видом stub.

Singleton: `get_gateway()` кеширует первый созданный экземпляр. В тестах
используйте `_reset_for_tests()` (см. tests/unit/test_sms.py).
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

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


class SmspilotGateway:
    """Отправляет SMS через SMSPILOT API-1. См. https://smspilot.ru/apikey.php.

    Физлицо без ИП/ООО: собственное имя отправителя не полагается (кроме
    Билайн), поэтому `from` не передаём — используется то, что определит
    модерация вместе с одобренным сервисным шаблоном. Согласованный шаблон:
    "Code {код}" — менять формулировку без повторного согласования нельзя.
    """

    _ENDPOINT = "https://smspilot.ru/api.php"
    _TEMPLATE = "Code {code}"
    _TIMEOUT = 10.0

    def __init__(self) -> None:
        apikey = os.getenv("SMSPILOT_APIKEY")
        if not apikey:
            raise ValueError("SMSPILOT_APIKEY is not set")
        self._apikey = apikey

    def send_code(self, phone: str, code: str) -> None:
        to = phone.lstrip("+")
        text = self._TEMPLATE.format(code=code)
        try:
            resp = httpx.post(
                self._ENDPOINT,
                data={
                    "apikey": self._apikey,
                    "send": text,
                    "to": to,
                    "format": "json",
                    "charset": "utf-8",
                    "lang": "ru",
                },
                timeout=self._TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SMSPILOT request failed: {exc}") from exc

        payload = resp.json()
        error = payload.get("error")
        if error:
            description = error.get("description_ru") or error.get("description")
            logger.error(
                "SMSPILOT send failed for %s: code=%s description=%s",
                phone, error.get("code"), description,
            )
            raise RuntimeError(f"SMSPILOT error {error.get('code')}: {description}")


_singleton: SmsGateway | None = None


def get_gateway() -> SmsGateway:
    """Возвращает singleton SmsGateway согласно env SMS_GATEWAY (default=stub)."""
    global _singleton
    if _singleton is not None:
        return _singleton
    name = os.getenv("SMS_GATEWAY", "stub")
    if name == "stub":
        _singleton = StubSmsGateway()
    elif name == "smspilot":
        _singleton = SmspilotGateway()
    else:
        raise ValueError(
            f"unknown SMS_GATEWAY={name!r}. Реализуйте провайдер в services/sms.py"
        )
    return _singleton


def _reset_for_tests() -> None:
    """Сбрасывает singleton — нужен тестам, использующим monkeypatch на env."""
    global _singleton
    _singleton = None
