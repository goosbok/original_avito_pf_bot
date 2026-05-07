import logging
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from utils.sqlite3 import get_user, update_user
from utils.sender import send_admins
from data.loader import bot
from services import identity

logger = logging.getLogger(__name__)


class ExistsUserMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def _ensure_user(self, tg_user, data: dict) -> None:
        if tg_user is None or tg_user.is_bot:
            return

        user_id = tg_user.id
        user_name = tg_user.username or ""
        first_name = tg_user.first_name or ""

        is_new = get_user(id=user_id) is None
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
            db_user = get_user(id=user_id)
            if db_user['user_name'] != user_name:
                update_user(user_id, user_name=user_name)
            if db_user['first_name'] != first_name:
                update_user(user_id, first_name=first_name)

    async def on_pre_process_message(self, message: Message, data: dict):
        await self._ensure_user(message.from_user, data)

    async def on_pre_process_callback_query(self, call: CallbackQuery, data: dict):
        logger.info("callback received: user_id=%s data=%r", call.from_user.id if call.from_user else None, call.data)
        await self._ensure_user(call.from_user, data)
