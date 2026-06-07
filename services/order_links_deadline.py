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


def close_expired_links() -> int:
    """Найти все in_work-ссылки с истёкшим deadline_at, перевести в done.

    Если переход последней ссылки заказа закрывает его (paid→done/failed) —
    шлёт notify юзеру (best-effort).

    Возвращает количество переведённых в done ссылок.
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
        return 0

    expired = [(r["id"], r["order_id"]) for r in rows]
    order_user: dict[int, int] = {}
    if expired:
        with connect() as con:
            order_ids_set = {oid for _, oid in expired}
            placeholders = ','.join('?' * len(order_ids_set))
            user_rows = con.execute(
                f"SELECT increment, user_id FROM orders WHERE increment IN "
                f"({placeholders})",
                tuple(order_ids_set),
            ).fetchall()
        order_user = {r["increment"]: r["user_id"] for r in user_rows}

    closed_count = 0
    status_transitions: list[tuple[int, str, str]] = []  # (order_id, old, new)
    for link_id, order_id in expired:
        try:
            transition = mark_done(link_id)
            closed_count += 1
            if transition is not None:
                old, new = transition
                status_transitions.append((order_id, old, new))
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "close_expired_links: mark_done(%s) failed", link_id
            )

    for order_id, old, new in status_transitions:
        user_id = order_user.get(order_id)
        if user_id is None:
            continue
        try:
            asyncio.run(
                notify_order_status_changed(
                    user_id=int(user_id),
                    kind="order",
                    order_id=int(order_id),
                    old_status=old,
                    new_status=new,
                )
            )
        except RuntimeError:
            # Если уже внутри event loop (тесты или вызов из coroutine) —
            # передаём планирование наружу через create_task.
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(notify_order_status_changed(
                    user_id=int(user_id), kind="order",
                    order_id=int(order_id),
                    old_status=old, new_status=new,
                ))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "close_expired_links: notify scheduling failed for %s",
                    order_id,
                )
        except Exception:  # noqa: BLE001 — notify best-effort
            logger.exception(
                "close_expired_links: notify failed for order %s", order_id
            )

    return closed_count


async def run_deadline_loop() -> None:
    """Периодический вызов close_expired_links()."""
    logger.info(
        "deadline loop started (interval=%ss)",
        DEADLINE_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            count = close_expired_links()
            if count:
                logger.info("deadline: closed %d links", count)
        except Exception:  # noqa: BLE001
            logger.exception("deadline loop iteration failed")
        await asyncio.sleep(DEADLINE_LOOP_INTERVAL_SECONDS)
