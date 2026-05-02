"""Эндпоинты авторизации.

POST /api/auth/telegram — принимает Telegram Login data, возвращает JWT.
GET  /api/me           — возвращает профиль текущего пользователя.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.db import connect
from web.auth import AuthError, create_jwt, verify_telegram_auth
from web.config import BOT_TOKEN, JWT_SECRET
from web.deps import get_current_user_id
from web.schemas import AuthResponse, Profile, TelegramAuthRequest

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/telegram", response_model=AuthResponse)
async def telegram_login(payload: TelegramAuthRequest) -> AuthResponse:
    try:
        user_id = verify_telegram_auth(payload.to_widget_dict(), bot_token=BOT_TOKEN)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token = create_jwt(user_id=user_id, secret=JWT_SECRET)
    return AuthResponse(access_token=token)


@router.get("/me", response_model=Profile)
async def me(user_id: int = Depends(get_current_user_id)) -> Profile:
    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, first_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not registered in bot — please /start the bot first",
        )
    return Profile(
        user_id=row["id"],
        user_name=row["user_name"],
        first_name=row["first_name"],
        balance=int(row["balance"] or 0),
    )
