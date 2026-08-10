"""SMS-OTP логин по номеру телефона.

POST /api/auth/phone/request-code — выпускает SMS-код, шлёт через SmsGateway.
POST /api/auth/phone/verify — проверяет код, создаёт user если нужно
(через identity.find_or_create_user_by_phone(phone, verified=True)) и возвращает JWT.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from data import config
from services import identity, otp, sms
from services.exceptions import OTPCooldown, OTPExpired
from services.sms import SmspilotGateway
from utils.phones import normalize_phone
from utils.sqlite3 import edit_setting, get_setting
from web.auth import create_jwt
from web.schemas import TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/phone", tags=["auth"])

OTP_TTL_SECONDS = 300         # 5 min
RESEND_COOLDOWN_SECONDS = 60  # 1 запрос в минуту

_LOW_BALANCE_ALERT_SETTING = "sms_balance_alert_last_sent"
_SEND_FAILURE_ALERT_SETTING = "sms_send_failure_alert_last_sent"


class RequestCodeBody(BaseModel):
    phone: str


class VerifyBody(BaseModel):
    phone: str
    code: str
    ref_code: str | None = Field(None, max_length=64)


def _mask_phone(phone: str) -> str:
    """+79991234567 → +799***4567. Не светим номер целиком в служебном чате."""
    if len(phone) <= 8:
        return phone
    return f"{phone[:4]}***{phone[-4:]}"


def _cooldown_elapsed(setting_key: str, cooldown_minutes: int) -> bool:
    last = get_setting(setting_key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - last_dt).total_seconds() >= cooldown_minutes * 60


def _mark_alert_sent(setting_key: str) -> None:
    edit_setting(setting_key, datetime.now(timezone.utc).isoformat())


async def _maybe_alert_low_balance(balance: float) -> None:
    if balance >= config.SMS_BALANCE_ALERT_THRESHOLD_RUB:
        return
    if not _cooldown_elapsed(_LOW_BALANCE_ALERT_SETTING, config.SMS_BALANCE_ALERT_COOLDOWN_MIN):
        logger.info("sms balance alert suppressed by cooldown, balance=%.2f", balance)
        return
    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"⚠️ <b>Баланс SMSPILOT заканчивается</b>\n\n"
            f"Остаток: <code>{balance:.2f} ₽</code> "
            f"(порог: {config.SMS_BALANCE_ALERT_THRESHOLD_RUB} ₽)\n"
            f"Регистрация по SMS — единственный способ входа, скоро перестанет работать.\n"
            f"Пополнить: https://smspilot.ru/\n\n"
            f"Время: {ts}",
            "errors",
        )
        _mark_alert_sent(_LOW_BALANCE_ALERT_SETTING)
    except Exception:
        logger.warning("sms balance alert: send_admins failed", exc_info=True)


async def _maybe_alert_send_failure(phone: str, exc: Exception) -> None:
    if not _cooldown_elapsed(_SEND_FAILURE_ALERT_SETTING, config.SMS_BALANCE_ALERT_COOLDOWN_MIN):
        logger.info("sms send-failure alert suppressed by cooldown")
        return
    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"🚨 <b>Отправка SMS не работает</b>\n\n"
            f"Ошибка: <code>{str(exc)[:400]}</code>\n"
            f"Телефон: <code>{_mask_phone(phone)}</code> "
            f"(регистрация не удалась, юзер получил 502)\n\n"
            f"Время: {ts}",
            "errors",
        )
        _mark_alert_sent(_SEND_FAILURE_ALERT_SETTING)
    except Exception:
        logger.warning("sms send-failure alert: send_admins failed", exc_info=True)


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
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    try:
        gateway = sms.get_gateway()
        await asyncio.to_thread(gateway.send_code, phone, code)
    except Exception as exc:
        logger.exception("SMS send failed for %s", phone)
        await _maybe_alert_send_failure(phone, exc)
        raise HTTPException(status_code=502, detail="Не удалось отправить SMS, попробуйте позже")

    if isinstance(gateway, SmspilotGateway) and gateway.last_balance is not None:
        await _maybe_alert_low_balance(gateway.last_balance)

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
    existing = identity.find_user_id_by_provider("phone", phone)
    user_id = identity.find_or_create_user_by_phone(phone, verified=True)
    if existing is None and body.ref_code:
        # Атрибуция ТОЛЬКО для реально нового юзера. Любой сбой (битый код,
        # залоченная БД) не должен ронять регистрацию: OTP уже сожжен, и 500
        # здесь оставил бы юзера без JWT при созданном аккаунте.
        try:
            from services import referral
            referral.attribute(user_id, body.ref_code)
        except Exception:
            logger.exception("referral attribution failed: user_id=%s", user_id)
    return TokenResponse(access_token=create_jwt(user_id))
