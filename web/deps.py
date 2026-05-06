"""FastAPI dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

from services import auth_api, identity
from services.exceptions import InvalidAPIKey
from web.auth import decode_jwt


@dataclass(frozen=True)
class CurrentCaller:
    """Кто сделал запрос. Может быть как залогиненный юзер (JWT), так и API-key call."""
    user_id: int
    source_type: str  # 'web' | 'telegram' | 'api'
    source_app_id: Optional[int]


async def current_caller(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_end_user_id: str | None = Header(None, alias="X-End-User-Id"),
) -> CurrentCaller:
    """Multi-method authentication.

    Priority:
    1. X-API-Key + X-End-User-Id → API call (source=api, source_app_id=<app>).
    2. Authorization: Bearer <jwt> → web call (source=web).
    """
    if x_api_key:
        if not x_end_user_id:
            raise HTTPException(
                status_code=400,
                detail="X-End-User-Id is required when using X-API-Key",
            )
        try:
            authz = auth_api.authorize(x_api_key, x_end_user_id)
        except InvalidAPIKey as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return CurrentCaller(
            user_id=authz.end_user_internal_id,
            source_type="api",
            source_app_id=authz.application_id,
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:].strip()
    try:
        user_id = decode_jwt(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    return CurrentCaller(user_id=user_id, source_type="web", source_app_id=None)


async def require_user(caller: CurrentCaller = Depends(current_caller)) -> int:
    """Convenience: возвращает только user_id, для роутеров, которым source неважен."""
    return caller.user_id
