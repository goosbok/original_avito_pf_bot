"""Admin endpoints for users — list/search, detail, balance, VIP."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from services import identity, orders as orders_svc
from services.db import connect
from services.exceptions import UserNotFound
from web.admin_deps import require_admin
from web.schemas import (
    AdminBalanceAdjust,
    AdminBalanceAdjustResponse,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSummary,
    AdminVipToggle,
    OrderItem,
    ProviderInfo,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


def _row_to_summary(row) -> AdminUserSummary:
    return AdminUserSummary(
        user_id=int(row["id"]),
        user_name=row["user_name"],
        first_name=row["first_name"],
        balance=int(row["balance"] or 0),
        is_vip=bool(row["is_vip"]),
        reg_date=str(row["reg_date"]) if row["reg_date"] else None,
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _: int = Depends(require_admin),
) -> AdminUserListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size
    like = f"%{q.strip()}%" if q else None

    with connect() as con:
        if like:
            total = con.execute(
                "SELECT COUNT(*) AS c FROM users "
                "WHERE user_name LIKE ? OR first_name LIKE ? OR CAST(id AS TEXT) LIKE ?",
                (like, like, like),
            ).fetchone()["c"]
            rows = con.execute(
                "SELECT id, user_name, first_name, balance, reg_date, is_vip FROM users "
                "WHERE user_name LIKE ? OR first_name LIKE ? OR CAST(id AS TEXT) LIKE ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (like, like, like, page_size, offset),
            ).fetchall()
        else:
            total = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            rows = con.execute(
                "SELECT id, user_name, first_name, balance, reg_date, is_vip FROM users "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()

    return AdminUserListResponse(
        items=[_row_to_summary(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get("/{target_user_id}", response_model=AdminUserDetail)
async def user_detail(
    target_user_id: int,
    _: int = Depends(require_admin),
) -> AdminUserDetail:
    try:
        u = identity.get_user(target_user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    providers = [ProviderInfo(**p) for p in identity.list_providers(target_user_id)]
    items, _total = orders_svc.list_orders(target_user_id, page=1, page_size=5)
    recent_orders = [
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
    ]
    with connect() as con:
        row = con.execute(
            "SELECT is_vip, reg_date FROM users WHERE id = ?",
            (target_user_id,),
        ).fetchone()
    return AdminUserDetail(
        user_id=u.id,
        user_name=u.user_name,
        first_name=u.first_name,
        balance=u.balance,
        is_vip=bool(row["is_vip"]) if row else False,
        reg_date=str(row["reg_date"]) if row and row["reg_date"] else None,
        providers=providers,
        recent_orders=recent_orders,
    )


@router.post("/{target_user_id}/balance", response_model=AdminBalanceAdjustResponse)
async def adjust_balance(
    target_user_id: int,
    body: AdminBalanceAdjust,
    admin_user_id: int = Depends(require_admin),
) -> AdminBalanceAdjustResponse:
    """Manual credit: bump balance and write an audit row to `refills`."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        row = con.execute(
            "SELECT balance FROM users WHERE id = ?",
            (target_user_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="user not found")
        before = int(row["balance"] or 0)
        after = before + body.delta
        con.execute("UPDATE users SET balance = ? WHERE id = ?", (after, target_user_id))
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id, source_type, source_app_id) "
            "VALUES (?, ?, ?, ?, 'admin_manual', NULL)",
            (target_user_id, body.delta, now, f"admin:{admin_user_id}:{body.reason[:120]}"),
        )
        con.commit()
    return AdminBalanceAdjustResponse(
        user_id=target_user_id,
        balance_before=before,
        balance_after=after,
    )


@router.post("/{target_user_id}/vip", status_code=200)
async def set_vip(
    target_user_id: int,
    body: AdminVipToggle,
    _: int = Depends(require_admin),
) -> dict:
    with connect() as con:
        row = con.execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="user not found")
        con.execute(
            "UPDATE users SET is_vip = ? WHERE id = ?",
            (1 if body.is_vip else 0, target_user_id),
        )
        con.commit()
    return {"user_id": target_user_id, "is_vip": body.is_vip}
