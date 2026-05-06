"""Pydantic-схемы для запросов и ответов веб-API."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RefillRequest(BaseModel):
    amount: int = Field(gt=0)


class RefillResponse(BaseModel):
    payment_id: str
    payment_url: str


class RefillStatusResponse(BaseModel):
    payment_id: str
    status: str  # "pending" | "succeeded" | "failed"


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=64)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OTPRequestBody(BaseModel):
    identifier: str = Field(min_length=2, max_length=64)


class OTPVerifyBody(BaseModel):
    identifier: str = Field(min_length=2, max_length=64)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ProfileResponse(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int


class ProviderInfo(BaseModel):
    provider: str
    identifier: str
    created_at: str
    last_used_at: str | None


class ApplicationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ApplicationCreateResponse(BaseModel):
    id: int
    name: str
    api_key: str  # plaintext, only shown once
    api_key_prefix: str
    created_at: str


class ApplicationInfo(BaseModel):
    id: int
    name: str
    api_key_prefix: str
    created_at: str
    revoked_at: str | None
