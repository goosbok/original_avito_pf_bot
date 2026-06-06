"""Email registration and login endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

logger = logging.getLogger(__name__)

from services import auth_email, auth_reset as _auth_reset
from services.exceptions import (
    EmailAlreadyRegistered,
    EmailSendError,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
)
from web.auth import create_jwt
from web.deps import require_user
from web.schemas import (
    ChangePasswordRequest,
    EmailLoginRequest,
    EmailRegisterRequest,
    EmailRegisterVerifyRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
)

router = APIRouter(prefix="/api/auth/email", tags=["auth"])
router_auth = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register-request", status_code=204, response_model=None)
async def register_request_endpoint(body: EmailRegisterRequest) -> Response:
    """Step 1: send verification code to email.

    Response is 204 No Content on success — the client should prompt for the code next.
    """
    try:
        auth_email.register_request(body.email, body.password, first_name=body.first_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except EmailSendError as exc:
        raise HTTPException(status_code=502, detail=f"email send failed: {exc}") from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/register-verify", response_model=TokenResponse)
async def register_verify_endpoint(body: EmailRegisterVerifyRequest) -> TokenResponse:
    """Step 2: verify code, create user, return JWT."""
    try:
        user_id = auth_email.register_verify(body.email, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))


@router.post("/login", response_model=TokenResponse)
async def login(body: EmailLoginRequest) -> TokenResponse:
    """Login with email and password."""
    try:
        user_id = auth_email.login(body.email, body.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))


@router.post("/forgot-password", response_model=None)
async def forgot_password(body: ForgotPasswordRequest) -> Response:
    """Send password reset link to email. Always returns 200 — never reveals registration status."""
    try:
        _auth_reset.forgot_password(body.email)
    except Exception:
        logger.exception("forgot_password error (returning 200 regardless)")
    return Response(status_code=200)


@router.post("/reset-password", status_code=204, response_model=None)
async def reset_password(body: ResetPasswordRequest) -> None:
    """Consume reset token and set a new password."""
    try:
        _auth_reset.reset_password(body.token, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router_auth.post("/change-password", status_code=204, response_model=None)
async def change_password(
    body: ChangePasswordRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Change password for authenticated user who has email linked."""
    try:
        auth_email.change_password(user_id, body.current_password, body.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
