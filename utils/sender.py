#-------------------------------------------------------------------------------
# Name:        Sender
# Purpose:
#
# Author:      KIPiA
#
# Created:     15.01.2025
# Copyright:   (c) KIPiA 2025
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import data.config as config
from data.loader import bot
from aiogram.utils.exceptions import ChatNotFound
from utils.sqlite3 import get_admins, get_spam_exclude

#Отправка отчета админам
async def send_admins(msg: str):
    for admin in get_admins():
        if admin not in get_spam_exclude():
            await bot.send_message(chat_id=admin, text=msg, disable_web_page_preview=True)
        else:
            pass

#Отправка отчета админам
async def send_admin(msg: str):
    await bot.send_message(chat_id=257838190, text=msg, disable_web_page_preview=True)

#Отправка отчета манагерам
async def send_managers(msg: str):
    for admin in get_admins():
        if admin != 6988175544 and admin != 257838190:
            await bot.send_message(chat_id=admin, text=msg, disable_web_page_preview=True)
        else:
            pass

