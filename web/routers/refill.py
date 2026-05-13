"""Эндпоинты пополнения баланса через веб.

POST /api/refill                     — создать инвойс, вернуть URL и payment_id.
GET  /api/refill/{payment_id}/status — узнать статус и (если оплачено) зачислить.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize_with_referral_bonus
from web.deps import CurrentCaller, current_caller
from web.schemas import RefillRequest, RefillResponse, RefillStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/refill", tags=["refill"])


# Client-facing message — intentionally generic; technical details go to
# logs + admin Telegram alert via _notify_refill_error().
_CLIENT_REFILL_ERROR = (
    "Не удалось создать платёж. Попробуйте позже или обратитесь в поддержку."
)


async def _notify_refill_error(user_id: int, amount: int, error: str) -> None:
    """Log refill failure and ping admins in Telegram. Best-effort: any
    exception here is swallowed so the client error path is unaffected."""
    logger.error(
        "refill failed user_id=%s amount=%s error=%s", user_id, amount, error
    )
    try:
        from services import identity as identity_svc
        from utils.sender import send_admins
        from utils.sqlite3 import get_tg_id_for_user

        try:
            user = identity_svc.get_user(user_id)
            user_name = user.user_name
        except Exception:
            user_name = None

        tg_id = get_tg_id_for_user(user_id)
        if tg_id and user_name:
            who = f"@{user_name} | <a href='tg://user?id={tg_id}'>{tg_id}</a>"
        elif tg_id:
            who = f"<a href='tg://user?id={tg_id}'>{tg_id}</a>"
        elif user_name:
            who = f"@{user_name}"
        else:
            who = f"user_id={user_id}"

        msg = (
            f"⚠️ <b>Ошибка пополнения (веб)</b>\n"
            f"👤 {who}\n"
            f"💰 Сумма: <b>{amount} ₽</b>\n"
            f"❌ {error}"
        )
        await send_admins(msg)
    except Exception:
        logger.exception("failed to notify admins about refill error")


def _yookassa_status(payment_id: str, *, user_id: int) -> str:
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    try:
        payment = Payment.find_one(payment_id)
    except Exception as exc:
        # Log + alert admins; surface only a generic error to the client.
        asyncio.create_task(
            _notify_refill_error(user_id, 0, f"yookassa status check failed: {exc}")
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_CLIENT_REFILL_ERROR,
        ) from exc
    return payment.status


@router.post("", response_model=RefillResponse)
async def create_refill(
    payload: RefillRequest,
    caller: CurrentCaller = Depends(current_caller),
) -> RefillResponse:
    try:
        url, pid = create_invoice(caller.user_id, payload.amount)
    except PaymentError as exc:
        # Log + alert admins; surface only a generic error to the client.
        asyncio.create_task(
            _notify_refill_error(caller.user_id, payload.amount, str(exc))
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_CLIENT_REFILL_ERROR,
        ) from exc
    return RefillResponse(payment_id=pid, payment_url=url)


@router.get("/{payment_id}/status", response_model=RefillStatusResponse)
async def refill_status(
    payment_id: str,
    caller: CurrentCaller = Depends(current_caller),
) -> RefillStatusResponse:
    yookassa_status = _yookassa_status(payment_id, user_id=caller.user_id)

    if yookassa_status == "succeeded":
        Configuration.account_id = SHOP_ID
        Configuration.secret_key = SECRET_KEY
        payment = Payment.find_one(payment_id)
        amount = int(float(payment.amount.value))
        try:
            finalize_with_referral_bonus(
                caller.user_id,
                amount,
                payment_id=payment_id,
                source_type=caller.source_type,
                source_app_id=caller.source_app_id,
            )
        except UserNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not in bot DB; /start the bot first",
            )
        simplified = "succeeded"
    elif yookassa_status in {"canceled", "expired", "rejected"}:
        simplified = "failed"
    else:
        simplified = "pending"

    return RefillStatusResponse(payment_id=payment_id, status=simplified)
