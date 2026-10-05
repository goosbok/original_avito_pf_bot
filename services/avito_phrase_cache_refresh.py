"""Bulk-refresh кэша известных объявлений.

Один раз в сутки тянем dashboard'у биза за последние `days` дней, парсим,
апсёртим в локальный кэш. Гейтится `PF_PHRASE_CACHE_REFRESH_ENABLED`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from data import config
from services.avito_phrase_cache import upsert_many
from services.biznesklondaik_client import (
    BiznesklondaikError, fetch_dashboard, login, parse_dashboard_html,
)
from services.search_key import sanitize_search_key

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))


def _today() -> date:
    return datetime.now(timezone.utc).astimezone(_MSK).date()


def refresh_recent(days: int = 2) -> int:
    """Один заход refresh-цикла. Возвращает число upsert'ов.

    Skip когда feature flag выключен — вернёт 0, ничего не делает.
    """
    if not config.PF_PHRASE_CACHE_REFRESH_ENABLED:
        logger.info("biza.refresh.skip feature_off")
        return 0

    today = _today()
    date_from = today - timedelta(days=days)
    date_to = today

    logger.info("biza.refresh.start window=%s..%s", date_from, date_to)
    try:
        session = login(config.BIZA_LOGIN, config.BIZA_PASSWORD)
        html = fetch_dashboard(session, date_from=date_from, date_to=date_to)
        rows = parse_dashboard_html(html)
    except BiznesklondaikError as exc:
        logger.exception("biza.refresh.failed err=%s", exc)
        return 0

    # Фильтруем мусорные ключи ДО группировки latest-wins: иначе форс-мажорный
    # запуск («1», ключ с фильтром цены, «ключ;ссылка») перезапишет хороший
    # ключ в кэше. Правила — services/search_key.sanitize_search_key.
    clean_rows = []
    for r in rows:
        clean, action = sanitize_search_key(r.get("search_link"))
        if clean is None:
            logger.warning(
                "biza.refresh.skip_invalid_key ad_id=%s reason=%s raw=%r",
                r.get("ad_id"), action, str(r.get("search_link"))[:120],
            )
            continue
        if action != "ok":
            logger.info(
                "biza.refresh.key_fixed ad_id=%s action=%s",
                r.get("ad_id"), action,
            )
            r = {**r, "search_link": clean}
        clean_rows.append(r)

    # Группируем by ad_id, оставляем latest по created_at
    by_ad: dict[str, dict] = {}
    for r in clean_rows:
        prev = by_ad.get(r["ad_id"])
        if prev is None or r["created_at"] > prev["created_at"]:
            by_ad[r["ad_id"]] = r

    affected = upsert_many(by_ad.values())
    logger.info(
        "biza.refresh.done window=%s..%s rows=%d skipped_invalid=%d unique_ads=%d upserted=%d",
        date_from, date_to, len(rows), len(rows) - len(clean_rows),
        len(by_ad), affected,
    )
    return affected


async def run_refresh_loop() -> None:
    interval_sec = config.PF_PHRASE_CACHE_REFRESH_INTERVAL_H * 3600
    logger.info("biza.refresh.loop start interval=%ss", interval_sec)
    # Boot-time refresh: deploy в 23:59 не должен оставлять кэш stale
    # на сутки. refresh_recent сам гейтится feature-flag'ом, так что
    # при выключенном флаге это бесплатный no-op.
    try:
        refresh_recent(days=2)
    except Exception:  # noqa: BLE001
        logger.exception("biza.refresh.boot_refresh_failed")
    while True:
        await asyncio.sleep(interval_sec)
        try:
            refresh_recent(days=2)
        except Exception:  # noqa: BLE001
            logger.exception("biza.refresh.loop_iter_failed")
