"""CRUD кэша известных объявлений (ad_id → search_link).

Используется classifier'ом в hot-path'е: один SELECT, никаких внешних HTTP.
Заполняется bulk-скрейпом dashboard'а исполнителя (см.
services.avito_phrase_cache_refresh).
"""
from __future__ import annotations

import logging
from typing import Iterable

from services.db import connect
from utils.dates import now_iso

logger = logging.getLogger(__name__)


def lookup(ad_id: str) -> str | None:
    """Вернуть last-used search_link для ad_id, или None."""
    if not ad_id:
        return None
    with connect() as con:
        row = con.execute(
            "SELECT search_link FROM avito_ad_phrase_cache WHERE ad_id=?",
            (ad_id,),
        ).fetchone()
    if row is None:
        return None
    return row["search_link"] if hasattr(row, "keys") else row[0]


def upsert_many(rows: Iterable[dict]) -> int:
    """Апсёрт пачки записей. Latest-created_at-wins по конфликту.

    Возвращает количество successful upsert'ов.
    """
    now = now_iso()
    affected = 0
    with connect() as con:
        for r in rows:
            ad_id = r.get("ad_id")
            phrase = r.get("search_link")
            created = r.get("created_at")
            if not ad_id or not phrase or not created:
                logger.warning(
                    "phrase_cache.upsert.skip_invalid ad_id=%r search_link=%r created_at=%r",
                    ad_id, phrase, created,
                )
                continue
            cur = con.execute(
                "INSERT INTO avito_ad_phrase_cache"
                "(ad_id, search_link, created_at, cached_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ad_id) DO UPDATE SET "
                "  search_link=excluded.search_link, "
                "  created_at=excluded.created_at, "
                "  cached_at=excluded.cached_at "
                "WHERE excluded.created_at > avito_ad_phrase_cache.created_at",
                (ad_id, phrase, created, now),
            )
            affected += cur.rowcount
        con.commit()
    return affected


def last_refreshed_at() -> str | None:
    """ISO-метка последнего апсёрта. Используется в health-check."""
    with connect() as con:
        row = con.execute(
            "SELECT MAX(cached_at) AS m FROM avito_ad_phrase_cache"
        ).fetchone()
    if row is None:
        return None
    return row["m"] if hasattr(row, "keys") else row[0]
