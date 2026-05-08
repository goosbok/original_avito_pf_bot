"""Orders API router.

GET  /api/orders/pf/price  — public: current price per unit
GET  /api/orders            — paginated order history for current user
POST /api/orders/pf         — create Avito PF order, deduct balance, notify
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from services import orders as orders_svc
from services.exceptions import UserNotFound
from services.orders import InsufficientBalance
from web.deps import require_user
from web.schemas import (
    OrderItem,
    OrderListResponse,
    PFOrderRequest,
    PFOrderResponse,
    PFPriceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/pf/price", response_model=PFPriceResponse)
async def get_pf_price() -> PFPriceResponse:
    return PFPriceResponse(price_per_unit=orders_svc.get_pf_price_per_unit())


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 20,
    user_id: int = Depends(require_user),
) -> OrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    items, total = orders_svc.list_orders(user_id, page=page, page_size=page_size)
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
async def create_pf_order(
    body: PFOrderRequest,
    user_id: int = Depends(require_user),
) -> PFOrderResponse:
    try:
        result = orders_svc.create_pf_order(
            user_id=user_id,
            links=body.links,
            days=body.days,
            fix_count=body.fix_count,
            contacts=body.contacts,
        )
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientBalance as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    asyncio.create_task(_notify_new_order(user_id, result.order_id, result.total_price))

    return PFOrderResponse(
        order_id=result.order_id,
        total_price=result.total_price,
        status=result.status,
    )


async def _notify_new_order(user_id: int, order_id: int, total_price: int) -> None:
    try:
        from data.loader import bot
        from services import identity as identity_svc
        from utils.other import format_decimal
        from utils.sender import send_admins
        from utils.sqlite3 import get_tg_id_for_user, get_users_last_order

        order = get_users_last_order(user_id)
        if order is None:
            return

        user = identity_svc.get_user(user_id)
        providers = identity_svc.list_providers(user_id)
        tg_id = get_tg_id_for_user(user_id)
        email = next((p["identifier"] for p in providers if p["provider"] == "email"), None)

        f_price = format_decimal(total_price)

        if tg_id and user.user_name:
            user_str = f"@{user.user_name} | <a href='tg://user?id={tg_id}'>{tg_id}</a>"
        elif tg_id:
            user_str = f"<a href='tg://user?id={tg_id}'>{tg_id}</a>"
        elif user.user_name:
            user_str = f"@{user.user_name}"
        else:
            user_str = f"id={user_id}"

        links_list = [l.strip().strip("'\"[]") for l in str(order["links"] or "").split(",") if l.strip().strip("'\"[]")]
        links_str = "".join(f"\n<code>{l}</code>" for l in links_list)

        lines = [
            f"🌐 <b>Новый заказ #{order['increment']} (веб)</b>",
            f"💰 Сумма: <b>{f_price} ₽</b>",
            f"👤 Пользователь: {user_str}",
        ]
        if email:
            lines.append(f"📧 Email: {email}")
        lines += [
            f"📋 Тариф: {order['position_name']}",
            f"📊 Статус: {order['status']}",
            f"📞 Контакт: {'Да' if order['contacts'] else 'Нет'}",
            f"📅 Дата: {order['date']}",
            f"🔗 Ссылок: {len(links_list)}{links_str}",
        ]

        adm_msg = "\n".join(lines)
        await send_admins(adm_msg)

        if tg_id:
            await bot.send_message(
                chat_id=tg_id,
                text=f"✅ Заказ #{order['increment']} принят. Сумма: {f_price} ₽",
            )
    except Exception:
        logger.exception("_notify_new_order failed for user_id=%s", user_id)
