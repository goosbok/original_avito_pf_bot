"""Provider linking/unlinking endpoints.

Allows authenticated users to:
- Link email with password to their account (2-step OTP)
- Link telegram via OTP code
- Unlink a provider (with guard against unlinking last provider)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services import auth_email, auth_telegram, identity
from services.exceptions import (
    BotCantReachUser,
    EmailSendError,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
    ProviderAlreadyLinked,
)
from web.deps import require_user
from web.schemas import (
    LinkEmailRequestStep1,
    LinkEmailVerifyRequest,
    OTPRequestBody,
    OTPVerifyBody,
)

router = APIRouter(prefix="/api/auth/link", tags=["auth-link"])


@router.post("/email/request", status_code=204, response_model=None)
async def link_email_request(
    body: LinkEmailRequestStep1,
    user_id: int = Depends(require_user),
) -> None:
    """Step 1: validate email/password, send OTP to the email address."""
    try:
        auth_email.link_email_request(user_id, body.email, body.password)
    except ProviderAlreadyLinked as exc:
        if exc.existing_user_id == user_id:
            raise HTTPException(status_code=400, detail="email already linked to your account") from exc
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


@router.post("/email/verify", status_code=204, response_model=None)
async def link_email_verify(
    body: LinkEmailVerifyRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Step 2: verify OTP, link email to the authenticated account."""
    try:
        auth_email.link_email_verify(user_id, body.email, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/telegram/request-code", status_code=204, response_model=None)
async def link_telegram_request(
    body: OTPRequestBody,
    user_id: int = Depends(require_user),
) -> None:
    """Request OTP code for linking telegram to current user."""
    try:
        auth_telegram.request_code(body.identifier, purpose="link", user_id_to_link=user_id)
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
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/telegram/verify-code", status_code=204, response_model=None)
async def link_telegram_verify(
    body: OTPVerifyBody,
    user_id: int = Depends(require_user),
) -> None:
    """Verify OTP code and link telegram to current user."""
    try:
        auth_telegram.verify_code_link(body.identifier, body.code, user_id)
    except OTPExpired:
        raise HTTPException(status_code=410, detail="code expired")
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{provider}/{identifier}", status_code=204, response_model=None)
async def unlink(
    provider: str,
    identifier: str,
    user_id: int = Depends(require_user),
) -> None:
    """Unlink a provider. Prevents unlinking the last provider."""
    providers = identity.list_providers(user_id)
    if len(providers) <= 1:
        raise HTTPException(status_code=400, detail="cannot unlink last provider")
    identity.unlink_provider(user_id, provider, identifier)
