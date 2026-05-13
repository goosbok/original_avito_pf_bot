"""Email registration and login endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from services import auth_email
from services.exceptions import (
    EmailAlreadyRegistered,
    EmailSendError,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
)
from web.auth import create_jwt
from web.schemas import (
    EmailLoginRequest,
    EmailRegisterRequest,
    EmailRegisterVerifyRequest,
    TokenResponse,
)

router = APIRouter(prefix="/api/auth/email", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: EmailRegisterRequest) -> TokenResponse:
    """Register a new user with email and password (legacy: immediate registration).

    Kept for backwards compatibility. New flow is /register-request → /register-verify.
    """
    try:
        user_id = auth_email.register(body.email, body.password, first_name=body.first_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))


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
