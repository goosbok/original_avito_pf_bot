"""Cron-задача: закрывать in_work-ссылки по истечении deadline.

Спек §5.3.
"""
from __future__ import annotations

import asyncio
import logging

from services.db import connect
from services.notifications import notify_order_status_changed
from services.order_links import mark_done
from utils.dates import now_iso

logger = logging.getLogger(__name__)

DEADLINE_LOOP_INTERVAL_SECONDS = 15 * 60  # 15 минут


def close_expired_links() -> tuple[int, list[tuple[int, int, str, str]]]:
    """Найти все in_work-ссылки с истёкшим deadline_at, перевести в done.

    Возвращает (count, transitions) — caller (run_deadline_loop) обязан
    вызвать notify_order_status_changed для каждого transition'а.
    """
    now = now_iso()
    with connect() as con:
        rows = con.execute(
            "SELECT id, order_id FROM order_links "
            "WHERE status='in_work' "
            "AND deadline_at IS NOT NULL "
            "AND deadline_at < ?",
            (now,),
        ).fetchall()
    if not rows:
        return 0, []

    expired = [(r["id"], r["order_id"]) for r in rows]
    order_ids_set = {oid for _, oid in expired}
    placeholders = ','.join('?' * len(order_ids_set))
    with connect() as con:
        user_rows = con.execute(
            f"SELECT increment, user_id FROM orders WHERE increment IN "
            f"({placeholders})",
            tuple(order_ids_set),
        ).fetchall()
    order_user = {r["increment"]: r["user_id"] for r in user_rows}

    closed_count = 0
    transitions: list[tuple[int, int, str, str]] = []
    for link_id, order_id in expired:
        try:
            t = mark_done(link_id)
            closed_count += 1
            if t is not None:
                old, new = t
                user_id = order_user.get(order_id)
                if user_id is not None:
                    transitions.append((int(order_id), int(user_id), old, new))
        except Exception:  # noqa: BLE001
            logger.exception(
                "close_expired_links: mark_done(%s) failed", link_id
            )

    return closed_count, transitions


async def run_deadline_loop() -> None:
    """Периодический вызов close_expired_links() с await notify."""
    logger.info(
        "deadline loop started (interval=%ss)",
        DEADLINE_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            count, transitions = close_expired_links()
            if count:
                logger.info("deadline: closed %d links", count)
            for order_id, user_id, old, new in transitions:
                try:
                    await notify_order_status_changed(
                        user_id=int(user_id),
                        kind="order",
                        order_id=int(order_id),
                        old_status=old,
                        new_status=new,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "deadline loop: notify failed for order %s", order_id
                    )
        except Exception:  # noqa: BLE001
            logger.exception("deadline loop iteration failed")
        await asyncio.sleep(DEADLINE_LOOP_INTERVAL_SECONDS)
