"""Guest orders API — public endpoints, no auth required.

GET  /api/guest-orders/payment-available   — is YooKassa accepting payments?
POST /api/guest-orders/pf                  — create guest order + YooKassa payment
GET  /api/guest-orders/{guest_order_id}/status — poll payment status
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from services import guest_orders as svc
from services.exceptions import PaymentError
from services.payment_probe import is_yookassa_enabled
from services.orders import get_pf_price_per_unit
from web.schemas import (
    GuestOrderStatusResponse,
    GuestPFOrderRequest,
    GuestPFOrderResponse,
    PaymentAvailableResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guest-orders", tags=["guest-orders"])


@router.get("/payment-available", response_model=PaymentAvailableResponse)
async def payment_available() -> PaymentAvailableResponse:
    return PaymentAvailableResponse(available=is_yookassa_enabled())


@router.post("/pf", response_model=GuestPFOrderResponse, status_code=201)
async def create_guest_pf_order(body: GuestPFOrderRequest) -> GuestPFOrderResponse:
    if not is_yookassa_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Онлайн-оплата временно недоступна",
        )

    price_per_unit = get_pf_price_per_unit()
    price = body.fix_count * body.days * len(body.links) * price_per_unit

    guest_order_id = svc.create_guest_order(
        phone=body.phone,
        links=body.links,
        days=body.days,
        fix_count=body.fix_count,
        contacts=body.contacts,
        price=price,
        price_per_unit=price_per_unit,
    )

    try:
        payment_url, payment_id = svc.create_payment(guest_order_id, price, body.phone)
    except PaymentError as exc:
        logger.error("guest order %s payment creation failed: %s", guest_order_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось создать платёж. Попробуйте позже или обратитесь в поддержку.",
        ) from exc

    svc.set_payment_id(guest_order_id, payment_id)

    return GuestPFOrderResponse(guest_order_id=guest_order_id, payment_url=payment_url)


@router.get("/{guest_order_id}/status", response_model=GuestOrderStatusResponse)
async def get_guest_order_status(guest_order_id: int) -> GuestOrderStatusResponse:
    order = svc.get_guest_order(guest_order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="guest order not found")

    if order["status"] == "paid":
        return GuestOrderStatusResponse(status="paid", order_id=guest_order_id)

    if order["status"] == "failed":
        return GuestOrderStatusResponse(status="failed")

    if not order["payment_id"]:
        return GuestOrderStatusResponse(status="pending")

    # Check YooKassa
    from data.config import SHOP_ID, SECRET_KEY
    from yookassa import Configuration, Payment

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    try:
        payment = Payment.find_one(order["payment_id"])
    except Exception as exc:
        logger.warning("guest order %s yookassa check failed: %s", guest_order_id, exc)
        return GuestOrderStatusResponse(status="pending")

    if payment.status == "succeeded":
        svc.update_status(guest_order_id, "paid")
        asyncio.create_task(_notify_guest_order_paid(order))
        return GuestOrderStatusResponse(status="paid", order_id=guest_order_id)

    if payment.status in {"canceled", "expired", "rejected"}:
        svc.update_status(guest_order_id, "failed")
        return GuestOrderStatusResponse(status="failed")

    return GuestOrderStatusResponse(status="pending")


async def _notify_guest_order_paid(order: dict) -> None:
    """Fire-and-forget Telegram admin notification."""
    try:
        from utils.other import format_decimal
        from utils.sender import send_admins

        import json
        links = json.loads(order["links"]) if order["links"] else []
        links_str = "".join(f"\n<code>{l}</code>" for l in links)

        msg = (
            f"🌐 <b>Новый гостевой заказ #{order['id']}</b>\n"
            f"💰 Сумма: <b>{format_decimal(order['price'])} ₽</b>\n"
            f"📞 Телефон: {order['phone']}\n"
            f"📋 Авито ПФ · {order['fix_count']} просм./д · {order['days']} дн.\n"
            f"📞 Контакты: {'Да' if order['contacts'] else 'Нет'}\n"
            f"🔗 Объявлений: {len(links)}{links_str}"
        )
        await send_admins(msg)
    except Exception:
        logger.exception("_notify_guest_order_paid failed for order id=%s", order.get("id"))
