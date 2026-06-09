"""Сервис пополнения баланса.

create_invoice — создаёт счёт в Yookassa.
finalize — после подтверждения оплаты атомарно зачисляет баланс и пишет в refills.
"""
from __future__ import annotations

from services.balance import credit, get_balance
from services.db import connect
from services.exceptions import PaymentError
from utils.other import get_date
from utils.yookassa_refil import create_invoice as _yookassa_create_invoice


def create_invoice(
    user_id: int,
    amount: int,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> tuple[str, str]:
    """Создаёт инвойс в YK и сразу пишет pending в refills.

    Возвращает (payment_url, payment_id). Бросает PaymentError при сбое YK
    или БД (INSERT pending). При сбое INSERT платёж в YK уже создан —
    шлём admin alert с payment_id для ручного восстановления.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    from services.source import normalize
    src_type, src_app = normalize(source_type, source_app_id)

    try:
        url, pid = _yookassa_create_invoice(user_id, amount)
    except Exception as exc:
        raise PaymentError(f"yookassa create_invoice failed: {exc}") from exc

    try:
        with connect() as con:
            con.execute(
                "INSERT INTO refills(amount, date, user_id, payment_id, "
                "source_type, source_app_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (amount, get_date(), user_id, pid, src_type, src_app),
            )
            con.commit()
    except Exception as exc:
        # Платёж в YK создан, но в нашей БД нет следа — крон не подберёт.
        # Логируем + алерт админам с payment_id для ручного backfill.
        import logging
        logging.getLogger(__name__).exception(
            "INSERT pending failed: payment_id=%s user_id=%s amount=%s",
            pid, user_id, amount,
        )
        try:
            import asyncio
            from utils.sender import send_admins
            msg = (
                f"⚠️ Платёж в YK создан, но pending row не записалась.\n"
                f"payment_id=<code>{pid}</code>\n"
                f"user_id={user_id}, amount={amount} ₽\n"
                f"Восстановить руками через scripts/backfill_stuck_payments."
            )
            # create_invoice вызывается из async-handler'ов (TG + web), но сам он sync.
            # Проверяем наличие running loop, чтобы не упасть с RuntimeError если когда-то
            # будут sync-вызовы (например, из скриптов).
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(send_admins(msg, "errors", parse_mode="HTML"))
            except RuntimeError:
                # Нет running loop — алерт пропустим, основная ошибка PaymentError всё равно поднимется.
                pass
        except Exception:
            pass  # лучшее усилие; PaymentError ниже всё равно поднимется
        raise PaymentError(f"refills INSERT pending failed: {exc}") from exc

    return url, pid


def finalize(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> tuple[int, bool]:
    """State machine: переводит pending→succeeded атомарно. Возвращает (new_balance, was_newly_finalized).

    was_newly_finalized=True ровно для одного победителя гонки за payment_id.
    Повторные вызовы для уже-succeeded → was_newly_finalized=False, баланс не меняется.
    Если pending row нет (backfill / legacy без payment_id) — INSERT succeeded напрямую.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    from services.source import normalize
    src_type, src_app = normalize(source_type, source_app_id)

    # Legacy path: вызов без payment_id (например, до релиза этого фикса).
    # Просто INSERT succeeded + credit, без state machine.
    if payment_id is None:
        new_balance = credit(user_id, amount)
        with connect() as con:
            con.execute(
                "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
                "VALUES (?, ?, ?, NULL, ?, ?, 'succeeded')",
                (amount, get_date(), user_id, src_type, src_app),
            )
            con.commit()
        return new_balance, True

    # State machine path: атомарный UPDATE...WHERE status='pending'.
    with connect() as con:
        cur = con.execute(
            "UPDATE refills SET status='succeeded' WHERE payment_id=? AND status='pending'",
            (payment_id,),
        )
        won_race = cur.rowcount == 1
        con.commit()

    if won_race:
        # Edge case: if credit() raises UserNotFound here, the row is left
        # status='succeeded' but balance was not credited. We don't roll back
        # because (a) we never delete users in this product, so the race is
        # vanishingly rare; (b) the reconciler won't retry succeeded rows.
        # If this fires in production, it requires admin intervention.
        # Same edge applies to the backfill INSERT-then-credit path below.
        new_balance = credit(user_id, amount)
        return new_balance, True

    # rowcount=0: либо уже succeeded (идемпотентность), либо нет строки, либо неожиданный статус.
    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", (payment_id,)
        ).fetchone()

    if row is None:
        # Backfill: pending row отсутствует. INSERT first to win the uniqueness
        # race (UNIQUE INDEX on payment_id catches a concurrent backfill),
        # THEN credit. Reversing this order would let two concurrent callers
        # both credit before either INSERT failed — double-credit bug.
        import sqlite3 as _sqlite3
        try:
            with connect() as con:
                con.execute(
                    "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'succeeded')",
                    (amount, get_date(), user_id, payment_id, src_type, src_app),
                )
                con.commit()
        except _sqlite3.IntegrityError:
            # Кто-то опередил нас на backfill (UNIQUE на payment_id).
            # Не кредитим повторно — он уже это сделал.
            return get_balance(user_id), False
        new_balance = credit(user_id, amount)
        return new_balance, True

    if row["status"] == "succeeded":
        return get_balance(user_id), False

    raise ValueError(
        f"refill {payment_id!r} cannot transition to succeeded from status={row['status']!r}"
    )


from dataclasses import dataclass

from services.exceptions import UserNotFound


@dataclass(frozen=True)
class RefillResult:
    user_balance: int
    referrer_id: int | None
    referrer_bonus: int
    referrer_new_balance: int | None
    was_newly_finalized: bool = False


def _is_first_refill(user_id: int) -> bool:
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? AND status = 'succeeded' LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is None


def _get_user_for_referral(user_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT id, ref_id, is_vip FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return row


def finalize_with_referral_bonus(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> RefillResult:
    """Финализирует refill + (на первой успешной) начисляет реф-бонус 30% реферу.

    was_newly_finalized пробрасывается из finalize() — крон/web-flow используют его,
    чтобы не задваивать уведомления при гонках.
    """
    user = _get_user_for_referral(user_id)
    is_first_before = _is_first_refill(user_id)  # снимок ДО finalize

    new_balance, was_newly_finalized = finalize(
        user_id, amount, payment_id=payment_id,
        source_type=source_type, source_app_id=source_app_id,
    )

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    # Бонус начисляется ТОЛЬКО при реальном переходе pending→succeeded,
    # И только если это был первый refill у юзера, И юзер не VIP.
    if was_newly_finalized and is_first_before and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            referrer_new_balance = (
                finalize(int(referrer_id), bonus,
                         source_type=source_type, source_app_id=source_app_id)[0]
                if bonus > 0 else None
            )
        except UserNotFound:
            referrer_new_balance = None
            bonus = 0

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_balance=referrer_new_balance,
        was_newly_finalized=was_newly_finalized,
    )
