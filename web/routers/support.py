"""Support chat API.

POST /api/support/messages  — user sends question, relayed to admins via bot
GET  /api/support/messages  — full conversation history for current user
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from services import support as support_svc
from web.deps import require_user
from web.schemas import SupportMessageCreate, SupportMessageItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support", tags=["support"])

_SUPPORT_TAG = "Вопрос из веб"


@router.get("/messages", response_model=list[SupportMessageItem])
async def get_messages(
    since_id: int = 0,
    user_id: int = Depends(require_user),
) -> list[SupportMessageItem]:
    msgs = support_svc.get_conversation(user_id, since_id=since_id)
    return [
        SupportMessageItem(
            id=m["id"],
            direction=m["direction"],
            text=m["text"],
            created_at=str(m["created_at"] or ""),
        )
        for m in msgs
    ]


@router.post("/messages", status_code=204, response_model=None)
async def send_message(
    body: SupportMessageCreate,
    user_id: int = Depends(require_user),
) -> None:
    msg_id = support_svc.create_user_message(user_id, body.text)
    asyncio.create_task(_forward_to_admins(user_id, msg_id, body.text))


async def _forward_to_admins(user_id: int, msg_id: int, text: str) -> None:
    try:
        from services import identity
        from services.db import connect as db_connect
        from utils.sender import send_admins

        try:
            u = identity.get_user(user_id)
            user_str = f"@{u.user_name}" if u.user_name else f"ID {user_id}"
        except Exception:
            user_str = f"ID {user_id}"

        fwd_text = (
            f"💬 <b>{_SUPPORT_TAG} #{msg_id}</b>\n"
            f"От: {user_str}\n\n{text}"
        )

        sent = await send_admins(fwd_text, "questions", parse_mode="HTML")
        if sent is None:
            logger.warning(
                "support: SUPPORT_THREAD_QUESTIONS unset — message %s for user %s not delivered to admins",
                msg_id, user_id,
            )
            return

        with db_connect() as con:
            con.execute(
                "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
                (sent.message_id, msg_id),
            )
            con.commit()
    except Exception:
        logger.exception("_forward_to_admins failed for user_id=%s", user_id)
