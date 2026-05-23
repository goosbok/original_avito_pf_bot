"""Admin dashboard stats."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from services.db import connect
from web.admin_deps import require_admin
from web.schemas import AdminStatsResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])

_GUEST_UNPAID_STATUSES = ("pending_payment", "payment_failed", "cancelled")


@router.get("/stats", response_model=AdminStatsResponse)
async def stats(_: int = Depends(require_admin)) -> AdminStatsResponse:
    # Все даты в БД хранятся в ISO+UTC (см. utils/dates.py + scripts/migrate_dates_to_iso.py).
    # LIKE 'YYYY-MM-DD%' валиден и для full-ISO ('2026-05-23T11:30:00+00:00'),
    # и для SQLite CURRENT_TIMESTAMP формы ('2026-05-23 11:30:00').
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{today}%"

    with connect() as con:
        users_total = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        users_today = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE reg_date LIKE ?",
            (prefix,),
        ).fetchone()["c"]

        orders_reg = con.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE date LIKE ?",
            (prefix,),
        ).fetchone()["c"]
        orders_guest = con.execute(
            "SELECT COUNT(*) AS c FROM guest_orders WHERE created_at LIKE ?",
            (prefix,),
        ).fetchone()["c"]
        orders_today = orders_reg + orders_guest

        revenue_reg = con.execute(
            "SELECT COALESCE(SUM(price), 0) AS s FROM orders "
            "WHERE date LIKE ? AND status != 'Cancelled'",
            (prefix,),
        ).fetchone()["s"]
        placeholders = ",".join("?" * len(_GUEST_UNPAID_STATUSES))
        revenue_guest = con.execute(
            f"SELECT COALESCE(SUM(price), 0) AS s FROM guest_orders "
            f"WHERE created_at LIKE ? AND status NOT IN ({placeholders})",
            (prefix, *_GUEST_UNPAID_STATUSES),
        ).fetchone()["s"]
        revenue_today = (revenue_reg or 0) + (revenue_guest or 0)

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
        revenue_today=int(revenue_today),
        open_support_threads=int(open_threads or 0),
    )
