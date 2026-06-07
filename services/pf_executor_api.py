"""Клиент API исполнителя ПФ.

STUB: пока всегда отказывает (`ExecutorAPIRejected`). С таким стабом все
auto-ссылки в dispatcher'е fallback'ятся в manual delivery_mode — система
ведёт себя как до этого спека, только через новую модель данных.

Будущая реализация: HTTP-вызов к API. Контракт:
  - submit_link → возвращает external_id (str) при успехе
  - ExecutorAPIRejected — API не возьмёт эту ссылку (другой регион/тип),
    caller должен fallback в manual
  - ExecutorAPIError — временный сбой, caller должен ретраить позже
"""
from __future__ import annotations

from services.exceptions import ExecutorAPIRejected


def submit_link(url: str, order: dict) -> str:
    """Отправить ссылку исполнителю. Возвращает external_id при успехе.

    STUB: всегда raises ExecutorAPIRejected.
    """
    raise ExecutorAPIRejected("API client not implemented yet (stub)")
