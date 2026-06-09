"""One-shot backfill кэша известных объявлений за N последних дней.

Использование:
    docker compose exec bot python -m scripts.backfill_avito_phrase_cache --days 90

Идемпотентен: можно прогонять повторно. Кэш апсёртится с latest-created_at-wins.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from data import config
from services.avito_phrase_cache import upsert_many
from services.biznesklondaik_client import (
    BiznesklondaikError, fetch_dashboard, login, parse_dashboard_html,
)

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))


def iter_chunks(today: date, *, days_back: int,
                chunk_size: int) -> Iterator[tuple[date, date]]:
    """Разбить интервал [today-days_back, today] на чанки по chunk_size дней."""
    start = today - timedelta(days=days_back)
    cur = start
    while cur < today:
        nxt = min(cur + timedelta(days=chunk_size), today)
        yield (cur, nxt)
        cur = nxt


def backfill(*, days: int, chunk_size: int = None,
             today: date = None, delay_sec: int = None) -> int:
    """Прогнать backfill. Возвращает суммарное число upsert'ов."""
    chunk_size = chunk_size or config.PF_PHRASE_CACHE_CHUNK_DAYS
    delay_sec = (delay_sec if delay_sec is not None
                 else config.PF_DASHBOARD_REQUEST_DELAY_SEC)
    today = today or datetime.now(timezone.utc).astimezone(_MSK).date()

    try:
        session = login(config.BIZA_LOGIN, config.BIZA_PASSWORD)
    except BiznesklondaikError as exc:
        logger.exception("backfill.login_failed err=%s", exc)
        return 0
    chunks = list(iter_chunks(today, days_back=days, chunk_size=chunk_size))
    total_upserted = 0
    for i, (df, dt) in enumerate(chunks, 1):
        logger.info("backfill.chunk %d/%d %s..%s", i, len(chunks), df, dt)
        try:
            html = fetch_dashboard(session, date_from=df, date_to=dt)
            rows = parse_dashboard_html(html)
        except BiznesklondaikError as exc:
            logger.exception("backfill.chunk_failed %d/%d err=%s",
                             i, len(chunks), exc)
            continue

        by_ad: dict[str, dict] = {}
        for r in rows:
            prev = by_ad.get(r["ad_id"])
            if prev is None or r["created_at"] > prev["created_at"]:
                by_ad[r["ad_id"]] = r

        affected = upsert_many(by_ad.values())
        total_upserted += affected
        logger.info("backfill.chunk_done rows=%d ads=%d upserted=%d",
                    len(rows), len(by_ad), affected)

        if i < len(chunks) and delay_sec > 0:
            time.sleep(delay_sec)

    logger.info("backfill.complete chunks=%d total_upserted=%d",
                len(chunks), total_upserted)
    return total_upserted


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--delay", type=int, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    backfill(days=args.days, chunk_size=args.chunk_size,
             delay_sec=args.delay)


if __name__ == "__main__":
    sys.exit(main())
