"""Backfill: восстанавливает order_links.search_link из avito_ad_phrase_cache.

Одноразовый прогон после релиза колонки search_link. Идемпотентен: трогает
только строки с delivery_mode='auto' и search_link IS NULL, уже заполненные
не перезаписывает.

Фраза берётся из кэша по ad_id, то есть это last-used фраза объявления, а не
гарантированно та, что реально ушла в биза. Для строк, отправленных до
релиза, точнее взять неоткуда.

Устойчив к падению на отдельной строке: ошибка на одной ссылке (например,
временная проблема с БД) логируется и учитывается в счётчике errors, проход
продолжается дальше.

Запуск:
    docker compose exec api python -m scripts.backfill_order_links_search_link
"""
from __future__ import annotations

import logging
import sys

from services.avito_phrase_cache import lookup
from services.avito_url import extract_ad_id
from services.db import connect

logger = logging.getLogger(__name__)


def backfill() -> dict[str, int]:
    """Проставить search_link всем auto-ссылкам без фразы.

    Возвращает счётчики: processed / filled / no_ad_id / cache_miss / errors.
    """
    stats = {"processed": 0, "filled": 0, "no_ad_id": 0, "cache_miss": 0,
             "errors": 0}
    with connect() as con:
        rows = con.execute(
            "SELECT id, url FROM order_links "
            "WHERE delivery_mode='auto' AND search_link IS NULL"
        ).fetchall()
        candidates = [(int(r["id"]), r["url"]) for r in rows]

        for link_id, url in candidates:
            stats["processed"] += 1
            try:
                ad_id = extract_ad_id(url)
                if not ad_id:
                    stats["no_ad_id"] += 1
                    continue
                phrase = lookup(ad_id)
                if not phrase:
                    stats["cache_miss"] += 1
                    continue
                # Guard search_link IS NULL защищает от гонки с dispatcher'ом,
                # который мог успеть записать актуальную фразу между нашим
                # SELECT и этим UPDATE — тогда чужую запись не перетираем.
                con.execute(
                    "UPDATE order_links SET search_link=? "
                    "WHERE id=? AND search_link IS NULL",
                    (phrase, link_id),
                )
                con.commit()
                stats["filled"] += 1
            except Exception:
                logger.exception(
                    "backfill.search_link.row_failed link_id=%d", link_id,
                )
                stats["errors"] += 1
                continue

    logger.info(
        "backfill.search_link.done processed=%d filled=%d no_ad_id=%d "
        "cache_miss=%d errors=%d",
        stats["processed"], stats["filled"], stats["no_ad_id"],
        stats["cache_miss"], stats["errors"],
    )
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    stats = backfill()
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
