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
        from utils.other import format_decimal
        from utils.sender import send_admins
        from utils.sqlite3 import get_tg_id_for_user, get_users_last_order

        order = get_users_last_order(user_id)
        if order is None:
            return

        f_price = format_decimal(total_price)
        links_str = ""
        for link in str(order["links"] or "").split(","):
            link = link.strip().strip("'\"[]")
            if link:
                links_str += f"\n<code>{link}</code>"

        adm_msg = (
            f"🌐 <b>Новый заказ #{order['increment']} (веб)</b>\n"
            f"Цена: {f_price} ₽\n"
            f"Параметры: {order['position_name']}\n"
            f"Контакты: {'Да' if order['contacts'] else 'Нет'}\n"
            f"Ссылки:{links_str}"
        )
        await send_admins(adm_msg)

        tg_id = get_tg_id_for_user(user_id)
        if tg_id:
            await bot.send_message(
                chat_id=tg_id,
                text=f"✅ Заказ #{order['increment']} принят. Сумма: {f_price} ₽",
            )
    except Exception:
        logger.exception("_notify_new_order failed for user_id=%s", user_id)
