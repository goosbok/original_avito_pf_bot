"""Pydantic-схемы для запросов и ответов веб-API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class RefillRequest(BaseModel):
    amount: int = Field(gt=0)
    agreed_privacy: bool
    agreed_offer: bool


class RefillResponse(BaseModel):
    payment_id: str
    payment_url: str


class RefillStatusResponse(BaseModel):
    payment_id: str
    status: str  # "pending" | "succeeded" | "failed"


class EmailRegisterRequest(BaseModel):
    """Registration via email. No password confirm field — the form has a
    single password input, mistypes are recovered through password reset."""
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


class LinkEmailRequestStep1(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'LinkEmailRequestStep1':
        if self.password != self.password_confirm:
            raise ValueError('passwords do not match')
        return self


class LinkEmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'ChangePasswordRequest':
        if self.new_password != self.new_password_confirm:
            raise ValueError('passwords do not match')
        return self


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'ResetPasswordRequest':
        if self.new_password != self.new_password_confirm:
            raise ValueError('passwords do not match')
        return self


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
    """Запрос на создание unpaid PF-заказа. phone обязателен для гостей."""
    links: list[str] = Field(..., min_length=1, max_length=20)
    days: int = Field(..., ge=1, le=90)
    fix_count: int = Field(..., ge=1, le=200)
    contacts: bool = False
    agreed_privacy: bool
    agreed_offer: bool
    phone: Optional[str] = None
    start_date: Optional[str] = None  # ISO "YYYY-MM-DD"; default = today

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v: list[str]) -> list[str]:
        for link in v:
            if not _re.match(r'^https?://((?:www|m)\.)?avito\.ru/', link):
                raise ValueError(f"invalid avito link: {link}")
        return v


class PFOrderResponse(BaseModel):
    order_id: int
    price: int
    available_methods: list[Literal["balance", "yookassa"]]


class LinkPreviewRequest(BaseModel):
    """Batch request: parse preview meta for up to 20 Avito URLs."""
    urls: list[str] = Field(..., min_length=1, max_length=20)

    @field_validator("urls")
    @classmethod
    def urls_must_be_avito(cls, v: list[str]) -> list[str]:
        for u in v:
            if not _re.match(r'^https?://((?:www|m)\.)?avito\.ru/', u):
                raise ValueError(f"invalid avito link: {u}")
        return v


class LinkPreviewItem(BaseModel):
    url: str
    status: Literal["ok", "not_found", "fetch_failed"]
    image_url: Optional[str] = None
    title: Optional[str] = None


class LinkPreviewResponse(BaseModel):
    previews: list[LinkPreviewItem]


class OrderPayRequest(BaseModel):
    method: Literal["balance", "yookassa"]


class OrderPayBalanceResponse(BaseModel):
    status: Literal["paid"]
    order_id: int


class OrderPayYookassaResponse(BaseModel):
    confirmation_url: str
    expires_at: str  # ISO timestamp


class OrderPaymentStatusResponse(BaseModel):
    status: Literal["unpaid", "paid", "payment_failed", "done", "failed", "cancelled"]
    order_id: int
    time_remaining_seconds: Optional[int] = None


class OrderDetailResponse(BaseModel):
    """Narrow response for GET /api/orders/pf/{id}.

    UNAUTHENTICATED endpoint (YooKassa redirects guests back here without a session),
    so the protection is the *whitelist*: only non-sensitive fields are exposed.

    EXCLUDED on purpose: phone, payment_id, user_id, user_name.
    """
    order_id: int
    status: str
    price: int
    position_name: str
    links: list[str] = []
    contacts: bool
    date: Optional[str] = None
    start_date: Optional[str] = None
    payment_method: Optional[str] = None
    payment_expires_at: Optional[str] = None


class OrderItem(BaseModel):
    order_id: int
    price: int
    position_name: str
    status: str
    links: list[str] = []
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
    user_id: int | None
    user_name: str | None
    price: int
    position_name: str
    status: str
    links: list[str] = []
    date: str
    contacts: bool
    is_guest: bool = False
    guest_phone: str | None = None


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderItem]
    total: int
    page: int
    page_size: int


_ORDER_STATUSES = ("unpaid", "paid", "done", "failed", "payment_failed", "cancelled")


class AdminOrderStatusChange(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, v: str) -> str:
        if v not in _ORDER_STATUSES:
            raise ValueError(f"status must be one of {_ORDER_STATUSES}")
        return v


class AdminSupportThread(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    last_message_text: str
    last_message_at: str
    last_direction: str
    has_unanswered: bool
    message_count: int


class AdminSupportThreadsResponse(BaseModel):
    threads: list[AdminSupportThread]


class AdminSupportReply(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AdminStatsResponse(BaseModel):
    users_total: int
    users_registered_today: int
    orders_today: int
    revenue_today: int
    open_support_threads: int


class NotificationItem(BaseModel):
    id: int
    kind: str
    order_id: int | None
    new_status: str | None
    text: str
    created_at: str
    read_at: str | None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked: int
