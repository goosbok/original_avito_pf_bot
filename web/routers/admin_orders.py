"""Admin endpoints for orders — list/filter, change status."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from services.db import connect
from services.order_links import list_links as _list_order_links
from services.notifications import (
    push_tg_notification,
    record_order_status_change,
)
from web.admin_deps import require_admin
from web.schemas import (
    AdminOrderItem,
    AdminOrderListResponse,
    AdminOrderStatusChange,
)

router = APIRouter(prefix="/api/admin/orders", tags=["admin"])


def _render_links_str(order_id: int) -> str:
    """Return newline-joined URLs from order_links (orders.links is NULL for new orders).

    NOTE: adds one extra DB query per order shown (N+1). Acceptable for
    paginated lists of ≤20 orders; can be batched later if needed.
    """
    try:
        rows = _list_order_links(int(order_id))
    except Exception:
        return ""
    return "\n".join(r["url"] for r in rows if r.get("url"))


def _row_to_item(row) -> AdminOrderItem:
    phone = row["phone"] if "phone" in row.keys() else None
    return AdminOrderItem(
        order_id=int(row["increment"]),
        user_id=int(row["user_id"]),
        user_name=row["user_name"],
        price=int(row["price"] or 0),
        position_name=str(row["position_name"] or ""),
        status=str(row["status"] or ""),
        links=_render_links_str(int(row["increment"])),
        date=str(row["date"] or ""),
        contacts=bool(row["contacts"]),
        is_guest=phone is not None,
        guest_phone=str(phone) if phone is not None else None,
    )


@router.get("", response_model=AdminOrderListResponse)
async def list_orders(
    status: str | None = None,
    user_id: int | None = None,
    is_guest: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    _: int = Depends(require_admin),
) -> AdminOrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    # После Task 2 миграции гостевых заказов больше нет в отдельной таблице:
    # они лежат в orders с phone IS NOT NULL (и payment_method='yookassa').
    where = []
    params: list = []
    if status:
        where.append("status = ?")
        params.append(status)
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    if is_guest is True:
        where.append("phone IS NOT NULL")
    elif is_guest is False:
        where.append("phone IS NULL")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with connect() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM orders {where_sql}", tuple(params)
        ).fetchone()["c"]
        rows = con.execute(
            f"SELECT increment, user_id, user_name, price, position_name, status, links, date, contacts, phone "
            f"FROM orders {where_sql} ORDER BY increment DESC LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        ).fetchall()

    return AdminOrderListResponse(
        items=[_row_to_item(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.post("/{order_id}/status", status_code=200)
async def change_status(
    order_id: int,
    body: AdminOrderStatusChange,
    _: int = Depends(require_admin),
) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT increment, user_id, status FROM orders WHERE increment = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="order not found")
        old_status = str(row["status"] or "")
        user_id = int(row["user_id"])
        if old_status != body.status:
            con.execute(
                "UPDATE orders SET status = ? WHERE increment = ?",
                (body.status, order_id),
            )
            con.commit()

    if old_status != body.status:
        text = record_order_status_change(
            user_id=user_id, kind="order", order_id=order_id,
            old_status=old_status, new_status=body.status,
        )
        if text is not None:
            asyncio.create_task(push_tg_notification(user_id=user_id, text=text))

    return {"order_id": order_id, "status": body.status}
