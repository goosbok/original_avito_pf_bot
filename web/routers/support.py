"""Support chat API.

POST /api/support/messages  — user sends question, relayed to admins via bot
GET  /api/support/messages  — full conversation history for current user
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from services import support as support_svc
from web.deps import require_user
from web.schemas import SupportMessageCreate, SupportMessageItem

router = APIRouter(prefix="/api/support", tags=["support"])

_SUPPORT_TAG = "Вопрос из веб"


@router.get("/messages", response_model=list[SupportMessageItem])
async def get_messages(user_id: int = Depends(require_user)) -> list[SupportMessageItem]:
    msgs = support_svc.get_conversation(user_id)
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
        from data.loader import bot
        from services import identity
        from services.db import connect as db_connect
        from utils.sqlite3 import get_admins, get_spam_exclude, get_tg_id_for_user

        try:
            u = identity.get_user(user_id)
            user_str = f"@{u.user_name}" if u.user_name else f"ID {user_id}"
        except Exception:
            user_str = f"ID {user_id}"

        fwd_text = (
            f"💬 <b>{_SUPPORT_TAG} #{msg_id}</b>\n"
            f"От: {user_str}\n\n{text}"
        )

        first_tg_msg_id = None
        for admin in get_admins():
            if admin in get_spam_exclude():
                continue
            tg_id = get_tg_id_for_user(int(admin)) or int(admin)
            try:
                sent = await bot.send_message(chat_id=tg_id, text=fwd_text, parse_mode="HTML")
                if first_tg_msg_id is None:
                    first_tg_msg_id = sent.message_id
            except Exception:
                pass

        if first_tg_msg_id is not None:
            with db_connect() as con:
                con.execute(
                    "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
                    (first_tg_msg_id, msg_id),
                )
                con.commit()
    except Exception:
        pass
