"""FastAPI-зависимости для извлечения текущего пользователя из JWT."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from web.auth import AuthError, decode_jwt
from web.config import JWT_SECRET


async def get_current_user_id(
    authorization: str | None = Header(default=None),
) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_jwt(token, secret=JWT_SECRET)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
