"""Admin endpoints for support — threads list, reply.

Reply path mirrors the bot's admin reply (handlers/support_web.py):
- inserts an 'admin' row into support_messages
- if the user has a Telegram provider, forwards the reply via the bot
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from services import identity, support as support_svc
from services.db import connect
from services.exceptions import UserNotFound
from web.admin_deps import require_admin
from web.schemas import (
    AdminSupportReply,
    AdminSupportThread,
    AdminSupportThreadsResponse,
    SupportMessageItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/support", tags=["admin"])


@router.get("/threads", response_model=AdminSupportThreadsResponse)
async def list_threads(
    _: int = Depends(require_admin),
) -> AdminSupportThreadsResponse:
    """Distinct users with support history, newest first, with unanswered flag."""
    with connect() as con:
        rows = con.execute(
            """
            SELECT
                m.user_id,
                u.user_name,
                u.first_name,
                (SELECT text FROM support_messages WHERE user_id = m.user_id ORDER BY id DESC LIMIT 1) AS last_text,
                (SELECT created_at FROM support_messages WHERE user_id = m.user_id ORDER BY id DESC LIMIT 1) AS last_at,
                (SELECT direction FROM support_messages WHERE user_id = m.user_id ORDER BY id DESC LIMIT 1) AS last_dir,
                COUNT(*) AS cnt
            FROM support_messages m
            LEFT JOIN users u ON u.id = m.user_id
            GROUP BY m.user_id
            ORDER BY last_at DESC
            """
        ).fetchall()

    threads = [
        AdminSupportThread(
            user_id=int(r["user_id"]),
            user_name=r["user_name"],
            first_name=r["first_name"],
            last_message_text=str(r["last_text"] or ""),
            last_message_at=str(r["last_at"] or ""),
            last_direction=str(r["last_dir"] or ""),
            has_unanswered=(str(r["last_dir"]) == "user"),
            message_count=int(r["cnt"] or 0),
        )
        for r in rows
    ]
    return AdminSupportThreadsResponse(threads=threads)


@router.get("/threads/{target_user_id}", response_model=list[SupportMessageItem])
async def get_thread(
    target_user_id: int,
    _: int = Depends(require_admin),
) -> list[SupportMessageItem]:
    msgs = support_svc.get_conversation(target_user_id, since_id=0)
    return [
        SupportMessageItem(
            id=int(m["id"]),
            direction=str(m["direction"]),
            text=str(m["text"]),
            created_at=str(m["created_at"]),
        )
        for m in msgs
    ]


async def _forward_reply_to_user(user_id: int, text: str) -> None:
    """Best-effort: deliver the admin reply into the user's Telegram chat."""
    try:
        from utils.sqlite3 import get_tg_id_for_user
        from data.loader import bot

        tg_id = get_tg_id_for_user(user_id)
        if not tg_id:
            return
        await bot.send_message(chat_id=tg_id, text=f"💬 Ответ поддержки:\n{text}")
    except Exception:
        logger.exception("forward reply to user_id=%s failed", user_id)


@router.post("/threads/{target_user_id}/reply", status_code=200)
async def post_reply(
    target_user_id: int,
    body: AdminSupportReply,
    _: int = Depends(require_admin),
) -> dict:
    # Reject replies into nonexistent threads to avoid orphan messages.
    with connect() as con:
        exists = con.execute(
            "SELECT 1 FROM support_messages WHERE user_id = ? LIMIT 1",
            (target_user_id,),
        ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="no thread for this user")

    msg_id = support_svc.create_admin_reply(target_user_id, body.text)
    asyncio.create_task(_forward_reply_to_user(target_user_id, body.text))
    return {"id": msg_id, "user_id": target_user_id}
