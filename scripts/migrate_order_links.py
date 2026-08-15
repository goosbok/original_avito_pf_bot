"""Backfill: переносит legacy orders.links → order_links.

Запускать вручную один раз после деплоя. Идемпотентен — повторный запуск
не трогает заказы, у которых уже есть строки в order_links.

Парсит три формата: json, ast.literal_eval, CSV/whitespace.
"""
from __future__ import annotations

import ast
import json
import logging
import re

from services.db import connect
from utils.dates import now_iso

logger = logging.getLogger(__name__)

# Маппинг orders.status → начальный link.status (Спек §6.2).
STATUS_MAP = {
    "done": "done",
    "failed": "failed",
    "cancelled": "failed",
    "paid": "pending",
    "unpaid": "pending",
    "payment_failed": "pending",
}


def parse_links_text(raw: str | None) -> list[str]:
    """Толерантный парсер. Пустой → пустой список."""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    # 1. JSON
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, TypeError):
        pass
    # 2. Python repr (str(list))
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    # 3. Split по запятой / whitespace
    tokens = re.split(r"[,\s]+", s)
    return [t.strip() for t in tokens if t.strip()]


def backfill() -> int:
    """Пробежать по всем заказам с непустым orders.links и без строк в
    order_links — создать недостающие. Возвращает количество обработанных
    заказов.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT o.increment, o.status, o.links, o.date "
            "FROM orders o "
            "WHERE o.links IS NOT NULL AND o.links != '' "
            "AND NOT EXISTS (SELECT 1 FROM order_links ol "
            "                WHERE ol.order_id = o.increment)"
        ).fetchall()
    if not rows:
        return 0

    handled = 0
    for row in rows:
        order_id = int(row["increment"])
        order_status = row["status"]
        order_date = row["date"]
        urls = parse_links_text(row["links"])
        if not urls:
            logger.warning(
                "backfill: order %s has unparseable links: %r",
                order_id, row["links"],
            )
            continue

        link_status = STATUS_MAP.get(order_status, "pending")
        timestamp_field, reason = None, None
        if link_status == "done":
            timestamp_field = "done_at"
        elif link_status == "failed":
            timestamp_field = "failed_at"
            reason = (
                "legacy: order cancelled"
                if order_status == "cancelled"
                else "legacy: order failed"
            )

        with connect() as con:
            for url in urls:
                if timestamp_field == "done_at":
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "done_at, created_at) VALUES (?, ?, ?, ?, ?)",
                        (order_id, url, link_status, order_date, now_iso()),
                    )
                elif timestamp_field == "failed_at":
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "failed_at, failure_reason, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (order_id, url, link_status, order_date, reason,
                         now_iso()),
                    )
                else:
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "created_at) VALUES (?, ?, ?, ?)",
                        (order_id, url, link_status, now_iso()),
                    )
            con.commit()
        handled += 1
    logger.info("backfill: processed %d orders", handled)
    return handled


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    count = backfill()
    print(f"backfill: processed {count} orders")
