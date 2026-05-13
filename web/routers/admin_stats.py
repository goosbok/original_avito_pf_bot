"""Admin dashboard stats."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from services.db import connect
from web.admin_deps import require_admin
from web.schemas import AdminStatsResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def stats(_: int = Depends(require_admin)) -> AdminStatsResponse:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with connect() as con:
        users_total = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        users_today = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE reg_date LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
        orders_today = con.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE date LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
        revenue_today = con.execute(
            "SELECT COALESCE(SUM(price), 0) AS s FROM orders "
            "WHERE date LIKE ? AND status != 'Cancelled'",
            (f"{today}%",),
        ).fetchone()["s"]
        open_threads = con.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS c
            FROM support_messages m
            WHERE m.id = (SELECT MAX(id) FROM support_messages WHERE user_id = m.user_id)
              AND m.direction = 'user'
            """
        ).fetchone()["c"]
    return AdminStatsResponse(
        users_total=int(users_total),
        users_registered_today=int(users_today),
        orders_today=int(orders_today),
        revenue_today=int(revenue_today or 0),
        open_support_threads=int(open_threads or 0),
    )
