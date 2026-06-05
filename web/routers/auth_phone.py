"""SMS-OTP логин по номеру телефона.

POST /api/auth/phone/request-code — выпускает SMS-код, шлёт через SmsGateway.
POST /api/auth/phone/verify — проверяет код, создаёт user если нужно
(через identity.find_or_create_user_by_phone(phone, verified=True)) и возвращает JWT.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import identity, otp, sms
from services.exceptions import OTPCooldown, OTPExpired
from utils.phones import normalize_phone
from web.auth import create_jwt
from web.schemas import TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/phone", tags=["auth"])

OTP_TTL_SECONDS = 300         # 5 min
RESEND_COOLDOWN_SECONDS = 60  # 1 запрос в минуту


class RequestCodeBody(BaseModel):
    phone: str


class VerifyBody(BaseModel):
    phone: str
    code: str


@router.post("/request-code")
async def request_code(body: RequestCodeBody) -> dict:
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=400, detail="невалидный формат телефона")
    try:
        code = otp.issue(
            channel='sms', destination=phone,
            purpose='phone_login',
            ttl_seconds=OTP_TTL_SECONDS,
            cooldown_seconds=RESEND_COOLDOWN_SECONDS,
        )
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком частые запросы. Подождите {exc.retry_after_seconds} сек.",
        )
    try:
        sms.get_gateway().send_code(phone, code)
    except Exception:
        logger.exception("SMS send failed for %s", phone)
        raise HTTPException(status_code=502, detail="Не удалось отправить SMS, попробуйте позже")
    return {"ok": True}


@router.post("/verify", response_model=TokenResponse)
async def verify(body: VerifyBody) -> TokenResponse:
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=400, detail="невалидный формат телефона")
    try:
        ok = otp.verify(
            channel='sms', destination=phone,
            code=body.code, purpose='phone_login',
        )
    except OTPExpired:
        raise HTTPException(status_code=400, detail="Код истёк, запросите новый")
    if not ok:
        raise HTTPException(status_code=400, detail="Неверный код")

    # Phone verified via SMS-OTP → создаём user с verified=True или находим существующего.
    user_id = identity.find_or_create_user_by_phone(phone, verified=True)
    return TokenResponse(access_token=create_jwt(user_id))
