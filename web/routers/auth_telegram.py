"""Telegram OTP login/link endpoints.

POST /api/auth/telegram/request-code — send OTP code via bot
POST /api/auth/telegram/verify-code — verify code and return JWT
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services import auth_telegram
from services.exceptions import BotCantReachUser, OTPCooldown, OTPExpired, OTPInvalid
from web.auth import create_jwt
from web.schemas import OTPRequestBody, OTPVerifyBody, TokenResponse

router = APIRouter(prefix="/api/auth/telegram", tags=["auth"])


@router.post("/request-code", status_code=204, response_model=None)
async def request_code(body: OTPRequestBody) -> None:
    try:
        auth_telegram.request_code(body.identifier)
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BotCantReachUser as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"could not deliver code: {exc}") from exc


@router.post("/verify-code", response_model=TokenResponse)
async def verify_code(body: OTPVerifyBody) -> TokenResponse:
    try:
        user_id = auth_telegram.verify_code_login(body.identifier, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail="code expired") from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))
