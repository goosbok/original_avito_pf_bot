"""Provider linking/unlinking endpoints.

Allows authenticated users to:
- Link email with password to their account
- Link telegram via OTP code
- Unlink a provider (with guard against unlinking last provider)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services import auth_email, auth_telegram, identity
from services.exceptions import (
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
    ProviderAlreadyLinked,
)
from web.deps import require_user
from web.schemas import (
    EmailRegisterRequest,
    OTPRequestBody,
    OTPVerifyBody,
)

router = APIRouter(prefix="/api/auth/link", tags=["auth-link"])


@router.post("/email", status_code=204)
async def link_email(
    body: EmailRegisterRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Link email with password to current user."""
    email_norm = auth_email.normalize_email(body.email)
    from services.auth_password import hash_password
    cred = hash_password(body.password)
    try:
        identity.link_provider(user_id, "email", email_norm, credential_hash=cred)
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/telegram/request-code", status_code=204)
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
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/telegram/verify-code", status_code=204)
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


@router.delete("/{provider}/{identifier}", status_code=204)
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
