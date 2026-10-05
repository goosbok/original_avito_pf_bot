"""Cleanup: чистка avito_ad_phrase_cache от невалидных ключей.

Одноразовый прогон после релиза sanitize-правил (заказчик, 2026-10-04):
  - ключи с фильтром цены (priceMin/priceMax) — подчищаем в месте
    (вырезаем price-параметры, строка остаётся);
  - «ключ;ссылка» — оставляем поисковую https-часть;
  - не-https («1», «#N/A») — удаляем: это форс-мажорные прямые запуски,
    не поисковые ключи. После удаления classifier возьмёт более старый
    валидный ключ из истории order_links или отправит ссылку в manual.

Идемпотентен: повторный прогон по уже чистому кэшу — no-op.
По умолчанию dry-run (только статистика). Запись — с флагом --apply.

Запуск:
    docker compose exec api python -m scripts.cleanup_phrase_cache --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from services.db import connect
from services.search_key import sanitize_search_key

logger = logging.getLogger(__name__)


def cleanup(*, apply: bool = False) -> dict[str, object]:
    """Прогнать sanitize по всем строкам кэша.

    apply=False — только считаем, ничего не пишем.
    Возвращает счётчики по action + updated/deleted (или would_* в dry-run).
    """
    with connect() as con:
        rows = con.execute(
            "SELECT ad_id, search_link FROM avito_ad_phrase_cache"
        ).fetchall()

        actions: Counter[str] = Counter()
        to_update: list[tuple[str, str]] = []   # (clean, ad_id)
        to_delete: list[str] = []

        for r in rows:
            ad_id = r["ad_id"]
            raw = r["search_link"]
            clean, action = sanitize_search_key(raw)
            actions[action] += 1
            if clean is None:
                to_delete.append(ad_id)
            elif clean != raw:
                to_update.append((clean, ad_id))

        if apply:
            for clean, ad_id in to_update:
                con.execute(
                    "UPDATE avito_ad_phrase_cache SET search_link=? "
                    "WHERE ad_id=?",
                    (clean, ad_id),
                )
            for ad_id in to_delete:
                con.execute(
                    "DELETE FROM avito_ad_phrase_cache WHERE ad_id=?",
                    (ad_id,),
                )
            con.commit()

    stats: dict[str, object] = dict(actions)
    stats["updated"] = len(to_update) if apply else 0
    stats["deleted"] = len(to_delete) if apply else 0
    stats["would_update"] = len(to_update)
    stats["would_delete"] = len(to_delete)
    stats["mode"] = "apply" if apply else "dry-run"
    return stats


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="записать изменения в БД (по умолчанию dry-run)",
    )
    args = parser.parse_args()

    stats = cleanup(apply=args.apply)
    for k, v in sorted(stats.items()):
        logger.info("cleanup.stat %s=%s", k, v)
    if not args.apply and (stats["would_update"] or stats["would_delete"]):
        logger.info("dry-run: перезапусти с --apply для записи изменений")
    return 0


if __name__ == "__main__":
    sys.exit(main())
