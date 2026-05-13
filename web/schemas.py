"""Pydantic-схемы для запросов и ответов веб-API."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    # Login intentionally relaxed: any non-empty password is accepted at the schema
    # layer so the auth service can return a single "wrong password" 401 instead of
    # leaking the 8-char minimum (also avoids a confusing Pydantic 422 for end users).
    password: str = Field(min_length=1, max_length=128)


class EmailRegisterVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


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
    is_admin: bool = False


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


import re as _re


class PFPriceResponse(BaseModel):
    price_per_unit: int


class PFOrderRequest(BaseModel):
    links: list[str] = Field(min_length=1)
    days: int = Field(gt=0)
    fix_count: int = Field(ge=5)
    contacts: bool

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v: list[str]) -> list[str]:
        for link in v:
            if not _re.search(r'avito\.ru', link):
                raise ValueError(f"invalid avito link: {link}")
        return v


class PFOrderResponse(BaseModel):
    order_id: int
    total_price: int
    status: str


class OrderItem(BaseModel):
    order_id: int
    price: int
    position_name: str
    status: str
    links: str
    date: str
    contacts: bool


class OrderListResponse(BaseModel):
    items: list[OrderItem]
    total: int
    page: int
    page_size: int


class SupportMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class SupportMessageItem(BaseModel):
    id: int
    direction: str
    text: str
    created_at: str


class AdminUserSummary(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int
    is_vip: bool
    reg_date: str | None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int
    page: int
    page_size: int


class AdminUserDetail(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int
    is_vip: bool
    reg_date: str | None
    providers: list[ProviderInfo]
    recent_orders: list[OrderItem]


class AdminBalanceAdjust(BaseModel):
    delta: int = Field(gt=0, le=1_000_000, description="Positive integer; manual credit")
    reason: str = Field(min_length=1, max_length=200)


class AdminBalanceAdjustResponse(BaseModel):
    user_id: int
    balance_before: int
    balance_after: int


class AdminVipToggle(BaseModel):
    is_vip: bool


class AdminOrderItem(BaseModel):
    order_id: int
    user_id: int
    user_name: str | None
    price: int
    position_name: str
    status: str
    links: str
    date: str
    contacts: bool


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderItem]
    total: int
    page: int
    page_size: int


_ORDER_STATUSES = ("Posted", "Completed", "Cancelled", "Pending")


class AdminOrderStatusChange(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, v: str) -> str:
        if v not in _ORDER_STATUSES:
            raise ValueError(f"status must be one of {_ORDER_STATUSES}")
        return v
