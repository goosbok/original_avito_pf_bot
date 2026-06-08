"""Клиент API исполнителя ПФ (https://biznesklondaik.ru/.../api/).

Используется dispatcher'ом для auto-режима. Авторизация — X-API-KEY.
Чтение из dashboard'а (cookie-auth) — отдельно, в biznesklondaik_client.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import requests

from data import config
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_session = requests.Session()


def submit_link(
    url: str,
    order: dict,
    *,
    search_phrase: str,
) -> str:
    """POST add-tasks.php → возвращает external_id (str) при успехе.

    Маппинг ошибок:
      400 → ExecutorAPIRejected (won't retry, fallback в manual)
      401/403 → ExecutorAPIError (config issue, retry бессмыслен,
                                  но логируем CRITICAL)
      422 → ExecutorAPIError (наш bug, лог critical)
      429 → ExecutorAPIError (retry)
      5xx / network → ExecutorAPIError (retry)
    """
    if not config.BIZA_API_KEY:
        raise ExecutorAPIError("BIZA_API_KEY not configured")

    payload = _build_avito_payload(url, order, search_phrase)
    api_url = config.BIZA_API_BASE_URL + "/add-tasks.php"
    headers = {
        "X-API-KEY": config.BIZA_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = _session.post(api_url, json=payload, headers=headers,
                             timeout=20.0)
    except requests.RequestException as exc:
        raise ExecutorAPIError(f"network: {exc}") from exc

    status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = {}

    if status == 200 and body.get("success"):
        task_ids = body.get("data", {}).get("task_ids") or []
        if not task_ids:
            raise ExecutorAPIError(
                f"200 OK но нет task_ids: {body}")
        external_id = str(task_ids[0])
        logger.info("biza.submit.ok ad=%s external_id=%s",
                    payload["tasks"][0]["ad_link"], external_id)
        return external_id

    err_text = body.get("error") or resp.text[:200]
    if status == 400:
        logger.warning("biza.submit.rejected ad=%s err=%s",
                       payload["tasks"][0]["ad_link"], err_text)
        raise ExecutorAPIRejected(f"400: {err_text}")
    if status in (401, 403):
        logger.critical("biza.submit.auth_error status=%s err=%s",
                        status, err_text)
        raise ExecutorAPIError(f"{status}: {err_text}")
    if status == 422:
        logger.critical("biza.submit.invalid_json payload=%s body=%s",
                        payload, body)
        raise ExecutorAPIError(f"422: {err_text}")
    if status == 429:
        logger.warning("biza.submit.rate_limited")
        raise ExecutorAPIError("429: rate limited")
    raise ExecutorAPIError(f"{status}: {err_text}")


# === Payload builder ===


def _build_avito_payload(
    url: str, order: dict, search_phrase: str
) -> dict:
    """Сформировать JSON для POST add-tasks.php (module=avito_pf)."""
    parts = str(order["position_name"]).split("/")
    days = int(parts[0])
    fix_count = int(parts[1]) if len(parts) > 1 else 0
    if fix_count <= 0:
        raise ExecutorAPIError(
            f"invalid fix_count from position_name={order['position_name']!r}"
        )

    today = datetime.now(timezone.utc).astimezone(_MSK).date()
    start_str = order.get("start_date")
    start = today
    if start_str:
        try:
            start = date.fromisoformat(str(start_str))
        except ValueError:
            logger.warning("biza.payload.bad_start_date %r → today",
                           start_str)
            start = today
    start = max(start, today)

    dates = [_fmt_date(start + timedelta(days=i)) for i in range(days)]

    return {
        "module": "avito_pf",
        "tasks": [{
            "search_link": search_phrase,
            "ad_link": url,
            "views_per_day": fix_count,
            "dates": dates,
            "device": "desktop",
            "mode": "polnyj",
            "request_contact": bool(order.get("contacts")),
            "add_favorite": True,
            "direct_if_not_found": True,
            "start_hour": 0,
            "enable_pauses": False,
        }],
    }


def _fmt_date(d: date) -> str:
    return f"{d.year}_{d.month}_{d.day}"
