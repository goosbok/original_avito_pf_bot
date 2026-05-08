import logging
import asyncio
import random
import time
from datetime import timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from data import config
from data.loader import dp, bot
from utils.sqlite3 import get_admins, all_users, get_tg_id_for_user
from utils.other import conv_delta
from keyboards.inline_keyboards import spam_send_kb, messages_kb, admin_back_kb

logger = logging.getLogger(__name__)


list_content_types = ['text', 'photo']

spam_send_stickers = ['CAACAgIAAxkBAAKkwmZiBWDI9edrau5mxOWyZVdKku86AAK6PAACn8eQS1pXdxbNkN0GNQQ', 'CAACAgIAAxkBAAKkyWZiBjXiq-xMlCblUMTRPEE8l9gMAAKEOwACqg-ASB2g--fr7MgZNQQ']
spam_ok_stickers = ['CAACAgIAAxkBAAKkxGZiBbbOh3b7DO0AAQko2z_Ea--_fgACrz0AAus-MUmBZQXoeh94iTUE', 'CAACAgIAAxkBAAKky2ZiBqaVIwreVHo-mMSW1aMa_yefAAI4QwAC-GaQS2IRSUEqOCBxNQQ']
spam_no_stickers = ['CAACAgIAAxkBAAKkzWZiB2S2CnhpW7OwVogkxgXiaDvNAAIDPQACen2QSwnVTmP8lTDXNQQ', 'CAACAgIAAxkBAAKkz2ZiB3WcO3970Sz0PvC-QmSa5oBlAAIwOQACTbCJS_QvdBkhGwOcNQQ']


class Spam(StatesGroup):
    SpamShow = State()
    SpamSend = State()


class admin_message(StatesGroup):
    send = State()


class coder_message(StatesGroup):
    send = State()


@dp.callback_query_handler(text="send_spam", state="*")
async def send_spam(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text=f"🔔 Ввыедите сообщение для рассылки:")
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await Spam.SpamShow.set()


@dp.message_handler(content_types=list_content_types, state=Spam.SpamShow)
async def spam_message(message: types.Message, state: FSMContext):
    content_type = message.content_type

    if content_type == "text":
        await message.answer("Вы ввели сообщение:")
        await message.answer(message.text)
        msg = await message.answer("Отправить?", reply_markup=spam_send_kb())
        await state.update_data(content_type="text", text=message.text, msg_id=msg.message_id)
    elif content_type == "photo":
        photo_id = message.photo[-1].file_id
        await message.answer("Вы ввели сообщение:")
        await message.answer_photo(photo=photo_id, caption=message.caption)
        msg = await message.answer("Отправить?", reply_markup=spam_send_kb())
        await state.update_data(content_type="photo", photo_id=photo_id, caption=message.caption, msg_id=msg.message_id)


async def send_spam(state: FSMContext):
    state_data = await state.get_data()
    content_type = state_data['content_type']
    msg_id = state_data['msg_id']
    users = all_users()
    total_users = len(users)
    sended = 0
    not_sended = 0
    admins = get_admins()
    if content_type == "text":
        text = state_data['text']
        start_time = time.monotonic()
        for user in users:
            tg_id = get_tg_id_for_user(user['id'])
            if tg_id is None:
                not_sended += 1
                continue
            if str(tg_id) not in admins and user['is_vip'] != 1:
                try:
                    await bot.send_message(tg_id, text=text)
                    sended += 1
                except:
                    logger.warning("spam: failed to send to tg_id=%s", tg_id)
                    not_sended += 1
            else:
                not_sended += 1
    elif content_type == "photo":
        photo_id = state_data['photo_id']
        caption = state_data['caption']
        start_time = time.monotonic()
        for user in users:
            tg_id = get_tg_id_for_user(user['id'])
            if tg_id is None:
                not_sended += 1
                continue
            if str(tg_id) not in admins and user['is_vip'] != 1:
                try:
                    await bot.send_photo(chat_id=tg_id, photo=photo_id, caption=caption)
                    sended += 1
                except:
                    logger.warning("spam: failed to send to tg_id=%s", tg_id)
                    not_sended += 1
            else:
                not_sended += 1
    end_time = time.monotonic()
    sec = await conv_delta(timedelta(seconds=end_time - start_time))
    for admin in admins:
        admin_tg_id = get_tg_id_for_user(int(admin)) or int(admin)
        try:
            random_sticker = random.choice(spam_ok_stickers)
            await bot.send_sticker(chat_id=admin_tg_id, sticker=random_sticker)
            await bot.send_message(chat_id=admin_tg_id, text=f"⚠️Рассылка сообщений завершена!\nПользователей в базе <b>{total_users}</b> из них <b>{sended}</b> доставлено, <b>{not_sended}</b> не доставлено, время рассылки <b>{sec}</b>", reply_markup=admin_back_kb('messages_menu'))
        except Exception as e:
            logger.exception("sender: failed to send to admin_id=%s", admin)
    await state.finish()


@dp.callback_query_handler(text_startswith="send:", state="*")
async def call_send_button(call: types.CallbackQuery, state: FSMContext):
    answer = call.data.split(':')[1]
    try:
        await call.message.delete()
    except:
        pass
    if answer == "yes":
        asyncio.create_task(send_spam(state))
        random_sticker = random.choice(spam_send_stickers)
        await call.message.answer("⚠️ Рассылка сообщений началась.", reply_markup=admin_back_kb('messages_menu'))
    else:
        random_sticker = random.choice(spam_no_stickers)
        await state.finish()
        await call.message.answer("⚠️ Рассылка сообщений отменена.", reply_markup=admin_back_kb('messages_menu'))


@dp.callback_query_handler(text="messages_menu")
async def messages_menu(call: types.CallbackQuery):
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text="🤖 Кому отправим сообщение:", reply_markup=messages_kb())
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.callback_query_handler(text="admin_send")
async def input_admin_message(call: types.CallbackQuery):
    await call.message.answer("🤖 Функция для кодера. Введите сообщение для отправки админу:")
    await admin_message.send.set()

    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.message_handler(state=admin_message.send)
async def send_admin_message(message: types.Message, state: FSMContext):
    admins = get_admins()
    sender_tg_id = str(message.from_user.id)
    for admin in admins:
        admin_tg_id = get_tg_id_for_user(int(admin)) or int(admin)
        if admin != sender_tg_id:
            await bot.send_message(chat_id=admin_tg_id, text=message.text, disable_web_page_preview=True)
        else:
            await bot.send_message(chat_id=admin_tg_id, text="Сообщение отправлено!", disable_web_page_preview=True)
    await state.finish()


@dp.callback_query_handler(text="coder_send")
async def input_coder_message(call: types.CallbackQuery):
    await call.message.answer("🤖 Функция для админа. Введите сообщение для отправки кодеру:")
    await coder_message.send.set()
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.message_handler(state=coder_message.send)
async def send_coder_message(message: types.Message, state: FSMContext):
    CODER = config.CODER
    await bot.send_message(chat_id=CODER, text=message.text, disable_web_page_preview=True)
    await state.finish()
