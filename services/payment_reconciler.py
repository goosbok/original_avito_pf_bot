"""Reconciliation крон для YooKassa-платежей.

Раз в 60 сек (см. __main__.py) забирает все pending refills за последние 24ч,
опрашивает YK по каждому, и переводит status согласно ответу YK. Уведомления
отправляются только при реальном переходе pending→succeeded (защита от
двойных пингов, если синхронный TG-пуллинг или web-/status успели раньше).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.db import connect
from services.exceptions import UserNotFound
from services.payment_notifications import (
    notify_admins_success, notify_referrer, notify_user_success,
)
from services.refill import finalize_with_referral_bonus

logger = logging.getLogger(__name__)


async def reconcile_pending() -> None:
    """Один тик крона: опросить все наши pending за 24h и финализировать succeeded."""
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with connect() as con:
        rows = con.execute(
            "SELECT payment_id, user_id, amount, source_type, source_app_id "
            "FROM refills WHERE status='pending' AND date >= ?",
            (cutoff,),
        ).fetchall()

    if not rows:
        return

    logger.info("reconciler tick: %d pending payments to check", len(rows))

    for row in rows:
        pid = row["payment_id"]
        try:
            # YK SDK синхронный — в отдельный поток, чтобы не блокировать event loop.
            p = await asyncio.to_thread(Payment.find_one, pid)
        except Exception:
            logger.exception("reconciler: Payment.find_one failed pid=%s", pid)
            continue

        try:
            await _handle_yk_status(row, p)
        except Exception:
            logger.exception("reconciler: handle_yk_status failed pid=%s", pid)
            # Не валим весь тик из-за одной плохой строки.


async def _handle_yk_status(row: dict, p) -> None:
    pid = row["payment_id"]
    status = getattr(p, "status", None)

    if status == "succeeded":
        try:
            result = finalize_with_referral_bonus(
                user_id=row["user_id"],
                amount=row["amount"],
                payment_id=pid,
                source_type=row["source_type"] or "telegram",
                source_app_id=row["source_app_id"],
            )
        except UserNotFound:
            logger.warning("reconciler: user not found user_id=%s pid=%s",
                           row["user_id"], pid)
            return
        if result.was_newly_finalized:
            logger.info("reconciler: finalized pid=%s user_id=%s amount=%s",
                        pid, row["user_id"], row["amount"])
            await notify_user_success(row["user_id"], row["amount"], result.user_balance)
            await notify_admins_success(row["user_id"], row["amount"], result.user_balance)
            if result.referrer_bonus > 0 and result.referrer_id is not None:
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_referral_balance or 0)
        else:
            logger.info("reconciler: pid=%s already finalized (no-op)", pid)

    elif status == "waiting_for_capture":
        # Двухстадийный платёж — захватываем. Следующий тик увидит succeeded.
        try:
            await asyncio.to_thread(Payment.capture, pid)
            logger.info("reconciler: captured pid=%s (waiting_for_capture)", pid)
        except Exception:
            logger.exception("reconciler: Payment.capture failed pid=%s", pid)

    elif status in ("canceled", "rejected"):
        with connect() as con:
            con.execute(
                "UPDATE refills SET status='canceled' WHERE payment_id=?", (pid,)
            )
            con.commit()
        logger.info("reconciler: pid=%s -> canceled", pid)

    elif status == "expired":
        with connect() as con:
            con.execute(
                "UPDATE refills SET status='expired' WHERE payment_id=?", (pid,)
            )
            con.commit()
        logger.info("reconciler: pid=%s -> expired", pid)

    elif status == "pending":
        return  # ждём следующий тик

    else:
        logger.warning("reconciler: unknown YK status %r for pid=%s", status, pid)
