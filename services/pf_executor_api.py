"""Клиент API исполнителя ПФ (https://biznesklondaik.ru/.../api/).

Используется dispatcher'ом для auto-режима. Авторизация — X-API-KEY.
Чтение из dashboard'а (cookie-auth) — отдельно, в biznesklondaik_client.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import requests

from data import config
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_session = requests.Session()


def _now_msk() -> datetime:
    """Текущее время в МСК (UTC+3). Hookable из тестов через patch."""
    return datetime.now(timezone.utc).astimezone(_MSK)


def _effective_start_msk(now_msk: datetime) -> date:
    """Дата начала запуска задачи в biza с учётом cutoff 04:00 МСК.

    Бизнес-сутка биза начинается в 04:00 МСК (start_hour=10 идёт следом).
    Заказы до 04:00 МСК **включительно** запускаются в эту же дату;
    заказы строго после 04:00 МСК переносятся на следующий календарный
    день. Все заказы интервала (T-1).04:01 .. T.04:00 МСК попадают в одну
    партию запуска — T в 10:00 МСК.

    Пример: оплата 11.12 в 23:53 МСК → effective_start = 12.12.
    """
    if now_msk.tzinfo is None:
        raise ValueError("now_msk must be timezone-aware (МСК)")
    if now_msk.time() > time(4, 0):
        return now_msk.date() + timedelta(days=1)
    return now_msk.date()


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
    raw = order.get("position_name")
    if not raw:
        raise ExecutorAPIRejected(
            f"order has no position_name (order_id={order.get('increment')})"
        )
    try:
        parts = str(raw).split("/")
        days = int(parts[0])
        fix_count = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError) as exc:
        raise ExecutorAPIRejected(
            f"invalid position_name={raw!r}: {exc}"
        ) from exc
    if fix_count <= 0:
        raise ExecutorAPIRejected(
            f"invalid fix_count from position_name={raw!r}"
        )

    # Cutoff 04:00 МСК: всё, что оформлено после 04:00 — стартует с
    # завтрашней даты в 10:00 МСК. Иначе биза не успевает за остаток дня
    # и закрывает task'и как `ostanovleno` с 0 просмотрами (issue
    # обнаружен после рейда по бизе 19.06: 14 заказов на 4800₽ так
    # потерялись).
    effective_start = _effective_start_msk(_now_msk())
    start_str = order.get("start_date")
    start = effective_start
    if start_str:
        try:
            start = date.fromisoformat(str(start_str))
        except ValueError:
            logger.warning("biza.payload.bad_start_date %r → effective_start",
                           start_str)
            start = effective_start
    # Юзерский start_date не может быть раньше effective_start — иначе
    # биза не успеет в свою бизнес-сутку и задача провалится.
    start = max(start, effective_start)

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
            "start_hour": int(config.PF_DEFAULT_START_HOUR),
            "enable_pauses": False,
        }],
    }


def _fmt_date(d: date) -> str:
    return f"{d.year}_{d.month}_{d.day}"
