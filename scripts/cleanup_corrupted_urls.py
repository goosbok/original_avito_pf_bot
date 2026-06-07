"""Очистка order_links.url от мусора (literal \\n, \\r, \\t, пробелы).

Возникло из-за legacy данных — старый код писал ссылки через str(list),
и иногда URL содержал реальный перенос строки. После backfill эти
переносы остались внутри url-поля + породили duplicate-строки на одном
URL.

Использование:
    python -m scripts.cleanup_corrupted_urls          # dry-run, отчёт
    python -m scripts.cleanup_corrupted_urls --apply  # реальная правка

Дедуп внутри order_id: keep earliest id с нормализованным URL, остальные
дубликаты с тем же normalized url удаляются. Приоритет статуса
done > failed > in_work > pending для выбора финального статуса
keep-строки.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from collections import defaultdict

from services.db import connect

logger = logging.getLogger(__name__)

# Статусы по убыванию приоритета — при склейке дублей оставляем лучший.
_STATUS_PRIORITY = ["done", "failed", "in_work", "pending"]


def normalize_url(raw: str) -> str:
    """Убирает literal control chars и trim'ит. Не трогает % escape sequences."""
    if raw is None:
        return ""
    # Удалить literal \n \r \t и пробелы по краям, схлопнуть множественные пробелы
    cleaned = re.sub(r"[\s]+", "", raw)
    return cleaned.strip()


def _best_status(statuses: list[str]) -> str:
    """Вернуть наиболее продвинутый по lifecycle статус."""
    for s in _STATUS_PRIORITY:
        if s in statuses:
            return s
    return statuses[0]  # fallback (не должен срабатывать)


def scan_and_clean(apply: bool = False) -> dict:
    """Сканирует order_links, нормализует URLs, дедуплицирует в рамках одного
    заказа. Возвращает отчёт.
    """
    report = {
        "rows_scanned": 0,
        "rows_with_dirty_url": 0,
        "rows_updated": 0,
        "rows_deleted": 0,
        "orders_affected": set(),
    }

    with connect() as con:
        rows = con.execute(
            "SELECT id, order_id, url, status, delivery_mode, deadline_at, "
            "  started_at, done_at, failed_at, failure_reason, external_id, "
            "  created_at "
            "FROM order_links ORDER BY order_id, id"
        ).fetchall()
        report["rows_scanned"] = len(rows)

        # Группируем по order_id для дедупа
        by_order: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            by_order[int(r["order_id"])].append(dict(r))

        for order_id, links in by_order.items():
            # Normalize, group by normalized url
            groups: dict[str, list[dict]] = defaultdict(list)
            for ln in links:
                norm = normalize_url(ln["url"])
                if norm != ln["url"]:
                    report["rows_with_dirty_url"] += 1
                groups[norm].append(ln)

            for norm_url, dups in groups.items():
                if len(dups) == 1 and dups[0]["url"] == norm_url:
                    continue  # clean and unique, nothing to do

                # Either dirty url or duplicates
                keep = min(dups, key=lambda d: d["id"])
                discard = [d for d in dups if d["id"] != keep["id"]]

                # Merge best status from all
                all_statuses = [d["status"] for d in dups]
                best = _best_status(all_statuses)

                # Merge non-NULL timestamps/fields, prefer the row that has the best status
                def pick(field: str) -> object:
                    candidates = [d[field] for d in dups if d.get(field) is not None]
                    return candidates[0] if candidates else None

                merged = {
                    "id": keep["id"],
                    "url": norm_url,
                    "status": best,
                    "delivery_mode": pick("delivery_mode"),
                    "deadline_at": pick("deadline_at"),
                    "started_at": pick("started_at"),
                    "done_at": pick("done_at"),
                    "failed_at": pick("failed_at"),
                    "failure_reason": pick("failure_reason"),
                    "external_id": pick("external_id"),
                }

                logger.info(
                    "order=%s: keep id=%s url=%r status=%s; delete ids=%s",
                    order_id, keep["id"],
                    norm_url[:50] + ("..." if len(norm_url) > 50 else ""),
                    best, [d["id"] for d in discard],
                )
                report["orders_affected"].add(order_id)

                if apply:
                    con.execute(
                        "UPDATE order_links SET "
                        "  url=?, status=?, delivery_mode=?, deadline_at=?, "
                        "  started_at=?, done_at=?, failed_at=?, "
                        "  failure_reason=?, external_id=? "
                        "WHERE id=?",
                        (merged["url"], merged["status"], merged["delivery_mode"],
                         merged["deadline_at"], merged["started_at"], merged["done_at"],
                         merged["failed_at"], merged["failure_reason"],
                         merged["external_id"], merged["id"]),
                    )
                    report["rows_updated"] += 1
                    if discard:
                        placeholders = ",".join("?" * len(discard))
                        con.execute(
                            f"DELETE FROM order_links WHERE id IN ({placeholders})",
                            tuple(d["id"] for d in discard),
                        )
                        report["rows_deleted"] += len(discard)

        if apply:
            con.commit()

    report["orders_affected"] = sorted(report["orders_affected"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Очистка order_links.url от мусора + дедуп."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Реальная правка БД. Без флага — dry-run (только отчёт)."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("cleanup_corrupted_urls: %s", mode)

    report = scan_and_clean(apply=args.apply)

    logger.info("=" * 60)
    logger.info("Report:")
    logger.info("  rows scanned:         %d", report["rows_scanned"])
    logger.info("  rows with dirty url:  %d", report["rows_with_dirty_url"])
    logger.info("  rows updated:         %d", report["rows_updated"])
    logger.info("  rows deleted:         %d", report["rows_deleted"])
    logger.info("  orders affected:      %d (%s)",
                len(report["orders_affected"]),
                report["orders_affected"][:20])

    if not args.apply and report["rows_with_dirty_url"]:
        logger.info("Run again with --apply to commit changes.")


if __name__ == "__main__":
    main()
