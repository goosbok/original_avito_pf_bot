"""Унифицированные эндпоинты заказов: гость и авторизованный — один путь.

GET  /api/orders/pf/price              — публичная цена за юнит.
GET  /api/orders                       — пагинация по заказам залогиненного юзера.
POST /api/orders/pf                    — создать unpaid (гость с phone или авторизованный).
POST /api/orders/pf/{id}/pay           — оплатить: balance или yookassa.
GET  /api/orders/pf/{id}               — карточка заказа (используется как return_url).
GET  /api/orders/pf/{id}/payment-status— polling статуса (probes YooKassa если нужно).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from services import orders as svc
from services import identity
from services.balance import get_balance
from services.exceptions import (
    InsufficientBalance,
    OrderNotFound,
    OrderStatusConflict,
    PaymentError,
    PaymentExpired,
    UserNotFound,
)
from services.payment_methods import is_enabled as method_enabled
from services.payment_probe import is_yookassa_enabled
from utils.phones import normalize_phone
from web.deps import get_current_user_optional, require_user
from web.schemas import (
    OrderDetailResponse,
    OrderItem,
    OrderListResponse,
    OrderPayBalanceResponse,
    OrderPayRequest,
    OrderPayYookassaResponse,
    OrderPaymentStatusResponse,
    PFOrderRequest,
    PFOrderResponse,
    PFPriceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _available_methods(user_id: Optional[int], price: int) -> list[str]:
    """Список методов оплаты доступных для актора этого заказа.

    Гость (user_id is None) — только yookassa.
    Авторизованный — balance (если хватает) и yookassa (если включён).
    """
    methods: list[str] = []
    if user_id is not None:
        try:
            if get_balance(user_id) >= price:
                methods.append("balance")
        except UserNotFound:
            pass
    if method_enabled("yookassa") and is_yookassa_enabled():
        methods.append("yookassa")
    return methods


@router.get("/pf/price", response_model=PFPriceResponse)
async def get_pf_price() -> PFPriceResponse:
    return PFPriceResponse(price_per_unit=svc.get_pf_price_per_unit())


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 20,
    user_id: int = Depends(require_user),
) -> OrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    items, total = svc.list_orders(user_id, page=page, page_size=page_size)
    return OrderListResponse(
        items=[
            OrderItem(
                order_id=o["increment"],
                price=int(o["price"] or 0),
                position_name=str(o["position_name"] or ""),
                status=str(o["status"] or ""),
                links=str(o["links"] or ""),
                date=str(o["date"] or ""),
                contacts=bool(o["contacts"]),
            )
            for o in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/pf", response_model=PFOrderResponse, status_code=201)
async def create_pf(
    body: PFOrderRequest,
    user_id: Optional[int] = Depends(get_current_user_optional),
) -> PFOrderResponse:
    if not (body.agreed_privacy and body.agreed_offer):
        raise HTTPException(400, "Необходимо принять политику конфиденциальности и оферту")

    is_guest = user_id is None
    if is_guest:
        if not body.phone:
            raise HTTPException(400, "phone обязателен для гостевого заказа")
        phone = normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(400, "невалидный формат телефона")
        order_user_id = identity.find_or_create_user_by_phone(phone)
    else:
        phone = None
        order_user_id = user_id

    order_id = svc.create_unpaid(
        user_id=order_user_id,
        links=body.links,
        days=body.days,
        fix_count=body.fix_count,
        contacts=body.contacts,
        phone=phone,
    )
    order = svc.get_order(order_id)
    # Доступные методы — с точки зрения АКТОРА: гость никогда не платит балансом,
    # даже если phone-only-user внезапно имеет ненулевой баланс.
    actor_user_id = None if is_guest else order_user_id
    methods = _available_methods(user_id=actor_user_id, price=int(order["price"]))
    if not methods:
        raise HTTPException(503, "Нет доступных способов оплаты")
    return PFOrderResponse(
        order_id=order_id,
        price=int(order["price"]),
        available_methods=methods,
    )


@router.post("/pf/{order_id}/pay")
async def pay(
    order_id: int,
    body: OrderPayRequest,
    request: Request,
    user_id: Optional[int] = Depends(get_current_user_optional),
):
    try:
        order = svc.get_order(order_id)
    except OrderNotFound:
        raise HTTPException(404, "order not found")

    if body.method == "balance":
        if user_id is None or user_id != int(order["user_id"]):
            raise HTTPException(403, "balance доступен только владельцу заказа")
        try:
            svc.pay_with_balance(order_id=order_id, user_id=user_id)
        except OrderNotFound:
            raise HTTPException(404, "order not found")
        except UserNotFound:
            raise HTTPException(404, "user not found")
        except InsufficientBalance:
            raise HTTPException(400, "Недостаточно средств на балансе")
        except OrderStatusConflict as exc:
            raise HTTPException(409, str(exc))
        except PaymentExpired:
            raise HTTPException(409, "Срок оплаты истёк")
        return OrderPayBalanceResponse(status="paid", order_id=order_id)

    if body.method == "yookassa":
        try:
            return_url = str(request.url_for("get_order_detail", order_id=order_id))
        except Exception:
            return_url = f"/api/orders/pf/{order_id}"
        try:
            confirm_url, _ = svc.pay_with_yookassa(order_id=order_id, return_url=return_url)
        except OrderNotFound:
            raise HTTPException(404, "order not found")
        except UserNotFound:
            raise HTTPException(404, "user not found")
        except OrderStatusConflict as exc:
            raise HTTPException(409, str(exc))
        except PaymentExpired:
            raise HTTPException(409, "Срок оплаты истёк")
        except PaymentError as exc:
            raise HTTPException(502, f"Ошибка платёжной системы: {exc}")
        order = svc.get_order(order_id)
        return OrderPayYookassaResponse(
            confirmation_url=confirm_url,
            expires_at=str(order["payment_expires_at"] or ""),
        )

    raise HTTPException(400, f"unknown method: {body.method}")


@router.get("/pf/{order_id}", name="get_order_detail", response_model=OrderDetailResponse)
async def get_order_detail(order_id: int) -> OrderDetailResponse:
    """Карточка заказа. Эндпоинт ПУБЛИЧНЫЙ (используется как return_url YooKassa
    для гостей без сессии), поэтому отдаёт строгий whitelist — без phone,
    payment_id, user_id, user_name.
    """
    try:
        order = svc.get_order(order_id)
    except OrderNotFound:
        raise HTTPException(404, "order not found")
    return OrderDetailResponse(
        order_id=int(order["increment"]),
        status=str(order["status"] or ""),
        price=int(order["price"] or 0),
        position_name=str(order["position_name"] or ""),
        links=str(order["links"] or ""),
        contacts=bool(order["contacts"]),
        date=str(order["date"]) if order["date"] else None,
        payment_method=str(order["payment_method"]) if order["payment_method"] else None,
        payment_expires_at=str(order["payment_expires_at"]) if order["payment_expires_at"] else None,
    )


@router.get("/pf/{order_id}/payment-status", response_model=OrderPaymentStatusResponse)
async def payment_status(order_id: int) -> OrderPaymentStatusResponse:
    try:
        order = svc.get_order(order_id)
    except OrderNotFound:
        raise HTTPException(404, "order not found")

    status_val = str(order["status"] or "")
    if status_val != "unpaid":
        return OrderPaymentStatusResponse(status=status_val, order_id=order_id)

    # Заказ в unpaid: если выбран yookassa и payment_id — спрашиваем у YooKassa.
    if order["payment_method"] == "yookassa" and order["payment_id"]:
        try:
            from data.config import SECRET_KEY, SHOP_ID
            from yookassa import Configuration, Payment

            Configuration.account_id = SHOP_ID
            Configuration.secret_key = SECRET_KEY
            p = Payment.find_one(order["payment_id"])
            if p.status == "succeeded":
                svc.mark_paid(order_id)
                return OrderPaymentStatusResponse(status="paid", order_id=order_id)
            if p.status == "canceled":
                svc.mark_payment_failed(order_id)
                return OrderPaymentStatusResponse(status="payment_failed", order_id=order_id)
        except Exception:
            logger.warning("yookassa probe failed for order %s", order_id)

    rem: Optional[int] = None
    if order["payment_expires_at"]:
        try:
            delta = datetime.fromisoformat(order["payment_expires_at"]) - datetime.now(timezone.utc)
            rem = max(0, int(delta.total_seconds()))
        except Exception:
            rem = None
    return OrderPaymentStatusResponse(
        status="unpaid",
        order_id=order_id,
        time_remaining_seconds=rem,
    )
