"""Endpoints for the in-app notifications bell feed."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from services import notifications as svc
from web.deps import require_user
from web.schemas import (
    MarkAllReadResponse,
    NotificationItem,
    NotificationListResponse,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_(
    user_id: int = Depends(require_user),
) -> NotificationListResponse:
    rows = svc.list_notifications(user_id, limit=50)
    return NotificationListResponse(
        items=[
            NotificationItem(
                id=int(r["id"]),
                kind=str(r["kind"]),
                order_id=(int(r["order_id"]) if r["order_id"] is not None else None),
                new_status=(str(r["new_status"]) if r["new_status"] is not None else None),
                text=str(r["text"]),
                created_at=str(r["created_at"]),
                read_at=(str(r["read_at"]) if r["read_at"] is not None else None),
            )
            for r in rows
        ],
        unread_count=svc.unread_count(user_id),
    )


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    user_id: int = Depends(require_user),
) -> MarkAllReadResponse:
    return MarkAllReadResponse(marked=svc.mark_all_read(user_id))
