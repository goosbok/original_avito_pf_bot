"""Pydantic-схемы для запросов и ответов веб-API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    """Данные, которые присылает Telegram Login Widget. Все поля опциональны
    кроме id/auth_date/hash, потому что first_name/last_name/username/photo_url
    могут отсутствовать в зависимости от настроек юзера в Telegram."""

    id: int
    auth_date: int
    hash: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None

    def to_widget_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Profile(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int = Field(ge=0)


class RefillRequest(BaseModel):
    amount: int = Field(gt=0)


class RefillResponse(BaseModel):
    payment_id: str
    payment_url: str


class RefillStatusResponse(BaseModel):
    payment_id: str
    status: str  # "pending" | "succeeded" | "failed"
