"""Hourly метрика auto_rate — для слежения за качеством работы classifier'а.

Лог формата:
    metric.auto_rate auto=N total=M rate=0.XX
"""
from __future__ import annotations

import asyncio
import logging

from data import config
from services.db import connect

logger = logging.getLogger(__name__)


def compute_recent_auto_rate(hours: int = 1) -> dict:
    sql = """
        SELECT
            SUM(CASE WHEN delivery_mode='auto'   THEN 1 ELSE 0 END) AS n_auto,
            SUM(CASE WHEN delivery_mode IS NOT NULL THEN 1 ELSE 0 END) AS n_total
        FROM order_links
        WHERE created_at >= datetime('now', ?)
    """
    with connect() as con:
        row = con.execute(sql, (f"-{hours} hours",)).fetchone()
    n_auto = int(row["n_auto"] or 0)
    n_total = int(row["n_total"] or 0)
    rate = n_auto / n_total if n_total else 0.0
    return {"auto": n_auto, "total": n_total, "rate": rate}


async def run_metric_loop() -> None:
    interval_sec = config.PF_AUTO_RATE_METRIC_INTERVAL_H * 3600
    logger.info("metric.auto_rate.loop start interval=%ss", interval_sec)
    while True:
        await asyncio.sleep(interval_sec)
        # Skip when auto-dispatch is off — иначе rate=0.0 каждый час
        # выглядит как поломанный classifier, хотя это by design (всё → manual).
        if not config.PF_AUTO_DISPATCH_ENABLED:
            logger.info("metric.auto_rate.skip feature_off")
            continue
        try:
            m = compute_recent_auto_rate(
                hours=config.PF_AUTO_RATE_METRIC_INTERVAL_H,
            )
            logger.info("metric.auto_rate auto=%d total=%d rate=%.3f",
                        m["auto"], m["total"], m["rate"])
        except Exception:  # noqa: BLE001
            logger.exception("metric.auto_rate.failed")
