"""Разовый backfill: зачисление 7 известных stuck YooKassa-платежей (на 2026-06-09).

Запуск:
    docker compose exec bot python -m scripts.backfill_stuck_payments

Безопасен к повторному запуску: для каждого payment_id проверяет, что:
  1) В YK всё ещё status='succeeded'.
  2) В refills нет уже succeeded строки с этим payment_id.
Если оба условия — вызывает finalize_with_referral_bonus (ветка backfill
INSERT succeeded напрямую) и шлёт уведомление в TG (если у юзера есть TG-привязка).

Web-only юзеры (Никита 8794553642, Дмитрий 8794553640, 8794553630) без
auth_providers.telegram — TG-уведомление пропускается; им ответим вручную
через support-чат, в котором они уже жалуются.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.db import connect
from services.exceptions import UserNotFound
from services.payment_notifications import (
    notify_admins_success, notify_referrer, notify_user_success,
)
from services.refill import finalize_with_referral_bonus

logger = logging.getLogger("backfill_stuck_payments")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# (payment_id, user_id, amount, source_type)
STUCK = [
    ("31ba1e1a-000f-5000-b000-1934f8b49a52", 8794553642, 300,  "web"),       # Никита
    ("31ba1d6c-000f-5000-b000-18ed29b434ee", 8794553640, 500,  "web"),       # Дмитрий
    ("31b76e2e-000f-5001-8000-137bad08104d", 8794553630, 500,  "web"),
    ("31b76c4f-000f-5000-8000-1b0b50f48647", 2137600714, 1000, "telegram"),  # staleksfoto
    ("31af5380-000f-5001-9000-1571d32e7c8f", 468390610,  1260, "telegram"),  # horusgor
    ("31ad3b38-000f-5001-8000-1d0e2d17940d", 6741171042, 1900, "telegram"),  # 24shina
    ("31abe6d3-000f-5000-8000-165673068025", 996225380,  300,  "telegram"),  # kochevnik15
]


async def main() -> int:
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    skipped = 0
    credited = 0
    errored = 0

    for pid, uid, amount, src in STUCK:
        logger.info("--- pid=%s user_id=%s amount=%s src=%s ---", pid, uid, amount, src)

        # 1) Проверка статуса в YK.
        try:
            p = Payment.find_one(pid)
        except Exception:
            logger.exception("YK find_one failed pid=%s — skipped", pid)
            errored += 1
            continue
        if p.status != "succeeded":
            logger.warning("YK status=%r (expected succeeded) pid=%s — skipped",
                           p.status, pid)
            skipped += 1
            continue

        yk_amount = int(float(p.amount.value))
        if yk_amount != amount:
            logger.warning("YK amount=%s != script amount=%s pid=%s — skipped",
                           yk_amount, amount, pid)
            skipped += 1
            continue

        # 2) Проверка нашей БД: нет ли уже succeeded строки с этим payment_id.
        with connect() as con:
            existing = con.execute(
                "SELECT status FROM refills WHERE payment_id=?", (pid,)
            ).fetchone()
        if existing and existing["status"] == "succeeded":
            logger.info("already credited (refills.status=succeeded) pid=%s — skipped", pid)
            skipped += 1
            continue

        # 3) finalize.
        try:
            result = finalize_with_referral_bonus(
                uid, amount, payment_id=pid, source_type=src,
            )
        except UserNotFound:
            logger.error("user not in DB user_id=%s pid=%s — skipped", uid, pid)
            errored += 1
            continue
        except Exception:
            logger.exception("finalize failed pid=%s — skipped", pid)
            errored += 1
            continue

        logger.info("CREDITED pid=%s user_id=%s amount=%s new_balance=%s "
                    "was_newly_finalized=%s",
                    pid, uid, amount, result.user_balance, result.was_newly_finalized)
        credited += 1

        # 4) Уведомления.
        if result.was_newly_finalized:
            await notify_user_success(uid, amount, result.user_balance)
            await notify_admins_success(uid, amount, result.user_balance)
            if result.referrer_bonus > 0 and result.referrer_id is not None:
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)

    logger.info("=== DONE: credited=%d skipped=%d errored=%d ===",
                credited, skipped, errored)
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
