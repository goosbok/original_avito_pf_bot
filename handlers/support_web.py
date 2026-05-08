"""Bot handler: admin reply to a web support message -> stored in support_messages."""
from __future__ import annotations

import logging
import re

from aiogram.types import Message

from data.loader import dp

logger = logging.getLogger(__name__)

_SUPPORT_PATTERN = re.compile(r"Вопрос из веб #(\d+)")


@dp.message_handler(
    lambda m: m.reply_to_message is not None and m.reply_to_message.text is not None,
    content_types=["text"],
    state="*",
)
async def admin_reply_to_support(message: Message) -> None:
    from utils.sqlite3 import get_admins

    admins = [str(a) for a in get_admins()]
    if str(message.from_user.id) not in admins:
        return

    replied_text = message.reply_to_message.text or ""
    match = _SUPPORT_PATTERN.search(replied_text)
    if match is None:
        return

    msg_id = int(match.group(1))

    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM support_messages WHERE id = ?",
            (msg_id,),
        ).fetchone()

    if row is None:
        logger.warning("support reply: msg_id=%s not found in DB", msg_id)
        return

    user_id = row["user_id"]

    from services.support import create_admin_reply
    create_admin_reply(user_id, message.text, message.message_id)

    from utils.sqlite3 import get_tg_id_for_user
    tg_id = get_tg_id_for_user(user_id)
    if tg_id:
        try:
            await message.bot.send_message(
                chat_id=tg_id,
                text=f"💬 Ответ поддержки:\n{message.text}",
            )
        except Exception:
            logger.warning("could not notify user_id=%s in TG", user_id)

    await message.reply("✅ Ответ сохранён")
    logger.info("support reply saved for user_id=%s, msg_id=%s", user_id, msg_id)
