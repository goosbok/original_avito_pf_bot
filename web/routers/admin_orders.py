"""Admin endpoints for orders — list/filter, change status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services.db import connect
from web.admin_deps import require_admin
from web.schemas import (
    AdminOrderItem,
    AdminOrderListResponse,
    AdminOrderStatusChange,
)

router = APIRouter(prefix="/api/admin/orders", tags=["admin"])


def _row_to_item(row) -> AdminOrderItem:
    return AdminOrderItem(
        order_id=int(row["increment"]),
        user_id=int(row["user_id"]),
        user_name=row["user_name"],
        price=int(row["price"] or 0),
        position_name=str(row["position_name"] or ""),
        status=str(row["status"] or ""),
        links=str(row["links"] or ""),
        date=str(row["date"] or ""),
        contacts=bool(row["contacts"]),
    )


@router.get("", response_model=AdminOrderListResponse)
async def list_orders(
    status: str | None = None,
    user_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    _: int = Depends(require_admin),
) -> AdminOrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    where = []
    params: list = []
    if status:
        where.append("status = ?")
        params.append(status)
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with connect() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM orders {where_sql}", tuple(params)
        ).fetchone()["c"]
        rows = con.execute(
            f"SELECT increment, user_id, user_name, price, position_name, status, links, date, contacts "
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
            "SELECT increment FROM orders WHERE increment = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="order not found")
        con.execute(
            "UPDATE orders SET status = ? WHERE increment = ?", (body.status, order_id)
        )
        con.commit()
    return {"order_id": order_id, "status": body.status}
