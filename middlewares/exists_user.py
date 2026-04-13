# - *- coding: utf- 8 - *-
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Update
from utils.sqlite3 import *
from utils.sender import *
from data.loader import bot

# TODO: отредачить поля
class ExistsUserMiddleware(BaseMiddleware):
    def __init__(self):
        super(ExistsUserMiddleware, self).__init__()

    async def on_process_message(self, update: Update, data: dict):

        #print(update)
        user = update
        if "message_id" in update:
            user = update.from_user
        elif "callback_query" in update:
            user = update.callback_query.from_user
        elif "pre_checkout_query" in update:
            user = update.pre_checkout_query.from_user

        if user is not None:
            if not user.is_bot:
                self.id = user.id
                self.user_name = user.username
                self.first_name = user.first_name
                self.bot = await bot.get_me()

                if self.user_name is None:
                    self.user_name = ""

                if get_user(id=self.id) is None:
                    register_user(id=self.id, user_name=self.user_name, first_name=self.first_name)
                    await send_admins(f"<b>💎 Зарегистрирован новый пользователь @{self.user_name} (<a href='tg://user?id={self.id}'>{self.id}</a>)</b>")
                else:
                    if get_user(id=self.id)['user_name'] != self.user_name:
                        update_user(self.id, user_name=self.user_name)
                    if get_user(id=self.id)['first_name'] != self.first_name:
                        update_user(self.id, first_name=self.first_name)

                    if len(self.user_name) >= 1:
                        if self.user_name != get_user(id=self.id)['user_name']:
                            update_user(id=self.id, user_name=self.user_name)
                    else:
                        update_user(id=self.id, user_name="")