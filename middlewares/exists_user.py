import logging
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from utils.sqlite3 import get_user, get_user_by_tg_id, update_user
from utils.sender import send_admins
from data.loader import bot
from services import identity

logger = logging.getLogger(__name__)


class ExistsUserMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    # ── fires for EVERY incoming Telegram update ──────────────────────────────
    async def on_pre_process_update(self, update: Update, data: dict):
        logger.info(
            "UPDATE type=%s id=%s | msg=%s | cb_data=%s",
            update.update_id,
            "message" if update.message else
            "callback_query" if update.callback_query else
            "other",
            update.message.text[:50] if update.message and update.message.text else None,
            update.callback_query.data if update.callback_query else None,
        )

    async def _ensure_user(self, tg_user, data: dict) -> None:
        if tg_user is None or tg_user.is_bot:
            return

        user_id = tg_user.id
        user_name = tg_user.username or ""
        first_name = tg_user.first_name or ""

        is_new = get_user_by_tg_id(user_id) is None
        internal_user_id = identity.get_or_create_user_by_telegram(
            tg_id=user_id,
            user_name=user_name,
            first_name=first_name,
        )
        data["user_id"] = internal_user_id

        if is_new:
            logger.info("new user registered: tg_id=%s username=%s", user_id, user_name)
            await send_admins(
                f"<b>💎 Зарегистрирован новый пользователь @{user_name} "
                f"(<a href='tg://user?id={user_id}'>{user_id}</a>)</b>"
            )
        else:
            db_user = get_user_by_tg_id(user_id)
            if db_user and db_user['user_name'] != user_name:
                update_user(db_user['id'], user_name=user_name)
            if db_user and db_user['first_name'] != first_name:
                update_user(db_user['id'], first_name=first_name)

    async def on_pre_process_message(self, message: Message, data: dict):
        await self._ensure_user(message.from_user, data)

    async def on_pre_process_callback_query(self, call: CallbackQuery, data: dict):
        logger.info("callback received: user_id=%s data=%r", call.from_user.id if call.from_user else None, call.data)
        await self._ensure_user(call.from_user, data)
