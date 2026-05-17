import logging
import asyncio
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram import types
from aiogram.dispatcher.filters import Text

from utils.error_handler import report_handler_error
from data.loader import dp, bot
from keyboards.users_menu import (
    get_menu_kb,
    qna_avito_kb,
)
from utils.other import format_decimal
from utils.sqlite3 import get_nick
from utils.sqlite3 import (
    delete_user,
    get_string, get_setting, get_price,
    get_all_qna_avito,
)
from aiogram.types import InputMediaVideo

logger = logging.getLogger(__name__)
logger.info("commands.py loaded — registering handlers")


@dp.message_handler(commands="id")
async def cmd_id(message: types.Message):
    logger.info("cmd_id: tg_id=%s", message.from_user.id)
    STR = get_string('str_your_id')
    await message.answer(STR.format(message.from_user.id))


@dp.message_handler(commands="delme")
async def cmd_delme(message: types.Message, user_id: int):
    logger.info("cmd_delme: user_id=%s", user_id)
    try:
        delete_user(id=user_id)
        STR = get_string('str_delete_user')
        await message.answer(STR.format(user_id))
    except Exception as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "cmd_delme", "user_id": user_id},
            reply_target=message,
        )


@dp.message_handler(commands="cancel", state="*")
@dp.message_handler(Text(equals="отмена", ignore_case=True), state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    STR = get_string('str_cmd_cancel')
    await message.answer(STR, reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(commands="egg")
@dp.message_handler(Text(equals="egg", ignore_case=True), state="*")
async def cmd_egg(message: Message):
    STICK = get_setting('egg_sticker')
    msg = await message.answer_sticker(STICK)
    await asyncio.sleep(5)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)


"""
@dp.message_handler(lambda message: message.text not in ['/start', '/id', '/delme', '/cancel'], state='*')
async def handle_invalid_command(message: types.Message, state: FSMContext):
    MSG = get_string('str_bad_command')
    await message.answer(MSG)
"""

# pre checkout  (must be answered in 10 seconds)
@dp.pre_checkout_query_handler(lambda query: True)
async def pre_checkout_query(pre_checkout_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)


@dp.callback_query_handler(text_startswith="info:", state='*')
async def info(call: CallbackQuery, state: FSMContext):
    logger.info("info callback: tg_id=%s data=%s", call.from_user.id, call.data)
    await state.finish()
    data = call.data.split(':')
    text = data[1]

    if text == 'tasks':
        price = int(get_price('price_avito_pf'))
        formated_price = format_decimal(price)
        STR = get_string('str_tasks_text')
        await call.message.answer(STR.format(formated_price), reply_markup=get_menu_kb())
    elif text == 'qna':
        STR = get_string('str_qna_text')
        await call.message.answer(STR, reply_markup=qna_avito_kb())
    elif text == 'rules':
        STR = get_string('str_rules_text')
        await call.message.answer(STR, reply_markup=get_menu_kb())
    elif text == 'start':
        BTN = get_string('btn_video_guide') or '🎬 Видео-инструкция'
        button = InlineKeyboardButton(text=BTN, callback_data="how_to")
        keyboard = get_menu_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        STR = get_string('str_how_to_start_text') or get_string('str_tasks_text') or '📖 Как начать работу'
        await call.message.answer(STR, reply_markup=keyboard)
    elif text == 'support':
        STR = get_string('str_support_text')
        support = get_nick('manager_nick')
        await call.message.answer(STR.format(support), reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except Exception:
        logger.debug("info: could not delete message")


@dp.callback_query_handler(text_startswith="qna_avito", state='*')
async def user_call_qna_avito(call: CallbackQuery, state: FSMContext):
    logger.info("qna_avito callback: tg_id=%s data=%s", call.from_user.id, call.data)
    all_qna = get_all_qna_avito()
    try:
        await call.message.delete()
    except Exception:
        logger.debug("qna_avito: could not delete message")
    for qna in all_qna:
        if qna['parametr'] == call.data:
            await call.message.answer(qna['value'], reply_markup=qna_avito_kb())


@dp.callback_query_handler(text="how_to", state='*')
async def call_how_to(call: CallbackQuery, state: FSMContext):
    with open('images/IMG_2661.MP4', 'rb') as video:
        video_obj = InputMediaVideo(media=video, caption="Видео инструкция")
        video.width = 886
        video.height = 1612
        await call.message.answer_media_group(media=[video_obj])
        STR = get_string('str_select_action')
        await call.message.answer(STR, reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(text_startswith="menu", state='*')
async def to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.finish()
    STR = get_string('str_select_action') or get_string('srt_select_variant_pf') or '📋 Главное меню'
    await call.message.answer(STR, reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


# ── diagnostic: fires for any callback that no other handler matched ──────────
@dp.callback_query_handler(state='*')
async def unhandled_callback(call: types.CallbackQuery, state: FSMContext):
    logger.warning("UNHANDLED callback: user_id=%s data=%r state=%s",
                   call.from_user.id, call.data, await state.get_state())
    await call.answer()
