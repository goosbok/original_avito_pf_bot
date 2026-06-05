"""Фоновая задача: перевод просроченных unpaid-заказов в payment_failed.

`expire_unpaid_orders()` — синхронная функция (легко тестируется).
`run_expiry_loop()` — asyncio-корутина, запускается на startup web/main.py.
"""
from __future__ import annotations

import asyncio
import logging

from services.db import connect
from services.orders import mark_payment_failed
from utils.dates import now_iso

logger = logging.getLogger(__name__)

EXPIRY_LOOP_INTERVAL_SECONDS = 60


def expire_unpaid_orders() -> int:
    """Найти все unpaid-заказы с истёкшим payment_expires_at и пометить payment_failed.

    Возвращает количество обработанных заказов.
    """
    now = now_iso()
    with connect() as con:
        rows = con.execute(
            "SELECT increment FROM orders "
            "WHERE status='unpaid' "
            "AND payment_expires_at IS NOT NULL "
            "AND payment_expires_at < ?",
            (now,),
        ).fetchall()
    order_ids = [row["increment"] for row in rows]
    for order_id in order_ids:
        try:
            mark_payment_failed(order_id)
        except Exception:  # noqa: BLE001 — best-effort, не валим всю партию
            logger.exception("expire_unpaid_orders: mark_payment_failed(%s) failed", order_id)
    return len(order_ids)


async def run_expiry_loop() -> None:
    """Периодически вызывать expire_unpaid_orders().

    Любые исключения подавляются и логируются — одна ошибка не должна убить цикл.
    """
    logger.info("payment expiry loop started (interval=%ss)", EXPIRY_LOOP_INTERVAL_SECONDS)
    while True:
        try:
            count = expire_unpaid_orders()
            if count:
                logger.info("payment expiry: marked %d orders as payment_failed", count)
        except Exception:  # noqa: BLE001
            logger.exception("payment expiry loop iteration failed")
        await asyncio.sleep(EXPIRY_LOOP_INTERVAL_SECONDS)
