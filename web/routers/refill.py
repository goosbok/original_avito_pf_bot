"""Эндпоинты пополнения баланса через веб.

POST /api/refill                     — создать инвойс, вернуть URL и payment_id.
GET  /api/refill/{payment_id}/status — узнать статус и (если оплачено) зачислить.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize_with_referral_bonus
from web.deps import get_current_user_id
from web.schemas import RefillRequest, RefillResponse, RefillStatusResponse

router = APIRouter(prefix="/api/refill", tags=["refill"])


def _yookassa_status(payment_id: str) -> str:
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    try:
        payment = Payment.find_one(payment_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"yookassa error: {exc}",
        ) from exc
    return payment.status


@router.post("", response_model=RefillResponse)
async def create_refill(
    payload: RefillRequest,
    user_id: int = Depends(get_current_user_id),
) -> RefillResponse:
    try:
        url, pid = create_invoice(user_id, payload.amount)
    except PaymentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return RefillResponse(payment_id=pid, payment_url=url)


@router.get("/{payment_id}/status", response_model=RefillStatusResponse)
async def refill_status(
    payment_id: str,
    user_id: int = Depends(get_current_user_id),
) -> RefillStatusResponse:
    yookassa_status = _yookassa_status(payment_id)

    if yookassa_status == "succeeded":
        Configuration.account_id = SHOP_ID
        Configuration.secret_key = SECRET_KEY
        payment = Payment.find_one(payment_id)
        amount = int(float(payment.amount.value))
        try:
            finalize_with_referral_bonus(user_id, amount, payment_id=payment_id)
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
