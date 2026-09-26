import io
import logging
import asyncio
import random
import time
from datetime import timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import TelegramAPIError

from data import config
from data.loader import dp, bot
from utils.sqlite3 import get_admins, all_users, get_tg_id_for_user
from utils.other import conv_delta
from keyboards.inline_keyboards import spam_send_kb, list_spam_send_kb, messages_kb, admin_back_kb
from services.list_broadcast import (
    RecipientsFileError, parse_recipients_csv, resolve_recipients, send_to_list, undelivered_csv,
)

logger = logging.getLogger(__name__)



spam_ok_stickers = ['CAACAgIAAxkBAAKkxGZiBbbOh3b7DO0AAQko2z_Ea--_fgACrz0AAus-MUmBZQXoeh94iTUE', 'CAACAgIAAxkBAAKky2ZiBqaVIwreVHo-mMSW1aMa_yefAAI4QwAC-GaQS2IRSUEqOCBxNQQ']


async def accept_broadcast_message(message: types.Message, state: FSMContext, confirm_text: str, confirm_kb) -> None:
    """Запоминает присланное/пересланное сообщение и показывает, как его увидят получатели.

    Рассылается копия именно этого сообщения (copy_message), поэтому сохраняются
    форматирование, ссылки и любые вложения.
    """
    if message.media_group_id:
        data = await state.get_data()
        if data.get("album_warned") == message.media_group_id:
            return
        await state.update_data(album_warned=message.media_group_id)
        await message.answer("⚠️ Альбом из нескольких фото/видео разослать целиком нельзя. "
                             "Пришлите одно фото или видео с подписью.")
        return
    payload = {"from_chat_id": message.chat.id, "message_id": message.message_id}
    await state.update_data(broadcast_payload=payload)
    await message.answer("Получатели увидят сообщение так:")
    try:
        await bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id,
                               message_id=message.message_id)
    except TelegramAPIError:
        logger.warning("broadcast: cannot copy message type=%s", message.content_type, exc_info=True)
        await state.update_data(broadcast_payload=None)
        await message.answer("⚠️ Такое сообщение разослать нельзя. Пришлите другое.")
        return
    await message.answer(confirm_text, reply_markup=confirm_kb)


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
    await bot.send_message(chat_id=user_id, text="🔔 Пришлите или перешлите сюда сообщение для рассылки — текст, фото, видео, голосовое. Оформление и ссылки сохранятся.")
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await Spam.SpamShow.set()


@dp.message_handler(content_types=types.ContentTypes.ANY, state=Spam.SpamShow)
async def spam_message(message: types.Message, state: FSMContext):
    await accept_broadcast_message(message, state, "Отправить?", spam_send_kb())


def _all_users_recipients() -> list:
    admins = get_admins()
    tg_ids = []
    for user in all_users():
        tg_id = get_tg_id_for_user(user['id'])
        if tg_id is not None and str(tg_id) not in admins and user['is_vip'] != 1:
            tg_ids.append(tg_id)
    return tg_ids


async def _run_spam(payload: dict):
    total_users = len(all_users())
    start_time = time.monotonic()
    report = await send_to_list(bot, _all_users_recipients(), payload)
    sended = report.delivered
    not_sended = total_users - sended
    sec = await conv_delta(timedelta(seconds=time.monotonic() - start_time))
    for admin in get_admins():
        admin_tg_id = get_tg_id_for_user(int(admin)) or int(admin)
        try:
            random_sticker = random.choice(spam_ok_stickers)
            await bot.send_sticker(chat_id=admin_tg_id, sticker=random_sticker)
            await bot.send_message(chat_id=admin_tg_id, text=f"⚠️Рассылка сообщений завершена!\nПользователей в базе <b>{total_users}</b> из них <b>{sended}</b> доставлено, <b>{not_sended}</b> не доставлено, время рассылки <b>{sec}</b>", reply_markup=admin_back_kb('messages_menu'))
        except Exception as e:
            logger.exception("sender: failed to send to admin_id=%s", admin)


@dp.callback_query_handler(text_startswith="send:", state="*")
async def call_send_button(call: types.CallbackQuery, state: FSMContext):
    answer = call.data.split(':')[1]
    payload = (await state.get_data()).get("broadcast_payload")
    await state.finish()
    try:
        await call.message.delete()
    except:
        pass
    if answer == "yes" and payload:
        asyncio.create_task(_run_spam(payload))
        await call.message.answer("⚠️ Рассылка сообщений началась.", reply_markup=admin_back_kb('messages_menu'))
    else:
        await call.message.answer("⚠️ Рассылка сообщений отменена.", reply_markup=admin_back_kb('messages_menu'))


@dp.callback_query_handler(text="messages_menu", state="*")
async def messages_menu(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
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


# --- Рассылка по списку Telegram ID из CSV-файла ---

class ListSpam(StatesGroup):
    WaitFile = State()
    WaitMessage = State()


@dp.callback_query_handler(text="send_list_spam", state="*")
async def list_spam_start(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    if str(call.from_user.id) not in get_admins():
        return
    await call.message.answer(
        "📋 Пришлите CSV-файл со списком получателей.\n\n"
        "Нужна колонка <b>telegram_id</b> (или ID в первой колонке). "
        "Написать бот может только тем, кто хоть раз запускал бота.",
        reply_markup=admin_back_kb('messages_menu'),
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    await ListSpam.WaitFile.set()


@dp.message_handler(content_types=['document'], state=ListSpam.WaitFile)
async def list_spam_file(message: types.Message, state: FSMContext):
    buf = io.BytesIO()
    await message.document.download(destination_file=buf)
    try:
        parsed = parse_recipients_csv(buf.getvalue())
    except RecipientsFileError as e:
        await message.answer(f"⚠️ Не получилось прочитать файл: {e}. Пришлите другой файл.",
                             reply_markup=admin_back_kb('messages_menu'))
        return

    resolved = resolve_recipients(parsed.tg_ids)
    lines = [f"📋 В файле {len(parsed.tg_ids)} получателей."]
    if resolved.unknown:
        lines.append(f"• {len(resolved.unknown)} нет в базе бота — им не отправим")
    if resolved.excluded:
        lines.append(f"• {len(resolved.excluded)} исключены из рассылки — им не отправим")
    if parsed.invalid:
        lines.append(f"• {parsed.invalid} строк без ID пропущено")
    if not resolved.send:
        lines.append("\nНекому отправлять. Пришлите другой файл.")
        await message.answer("\n".join(lines), reply_markup=admin_back_kb('messages_menu'))
        return

    lines.append(f"\n✅ Получат сообщение: <b>{len(resolved.send)}</b>")
    lines.append("\n🔔 Пришлите или перешлите сюда сообщение для рассылки — текст, фото, видео, голосовое. Оформление и ссылки сохранятся.")
    await state.update_data(list_tg_ids=resolved.send)
    await message.answer("\n".join(lines), reply_markup=admin_back_kb('messages_menu'))
    await ListSpam.WaitMessage.set()


@dp.message_handler(content_types=['text', 'photo'], state=ListSpam.WaitFile)
async def list_spam_not_file(message: types.Message):
    await message.answer("📎 Нужен именно CSV-файл — прикрепите его как документ.",
                         reply_markup=admin_back_kb('messages_menu'))


@dp.message_handler(content_types=types.ContentTypes.ANY, state=ListSpam.WaitMessage)
async def list_spam_message(message: types.Message, state: FSMContext):
    count = len((await state.get_data()).get("list_tg_ids", []))
    await accept_broadcast_message(message, state, f"Отправить {count} получателям?", list_spam_send_kb())


async def _run_list_spam(admin_chat_id: int, tg_ids: list, payload: dict):
    start_time = time.monotonic()
    report = await send_to_list(bot, tg_ids, payload)
    sec = await conv_delta(timedelta(seconds=time.monotonic() - start_time))
    text = (
        f"⚠️ Рассылка по списку завершена!\n"
        f"Получателей <b>{len(tg_ids)}</b>: доставлено <b>{report.delivered}</b>, "
        f"заблокировали бота <b>{len(report.blocked)}</b>, ошибок <b>{len(report.failed)}</b>. "
        f"Время рассылки <b>{sec}</b>"
    )
    try:
        await bot.send_message(admin_chat_id, text, reply_markup=admin_back_kb('messages_menu'))
        if report.blocked or report.failed:
            await bot.send_document(
                admin_chat_id,
                types.InputFile(io.BytesIO(undelivered_csv(report)), filename="undelivered.csv"),
                caption="Кому не доставлено",
            )
    except Exception:
        logger.exception("list broadcast: failed to send report to admin chat_id=%s", admin_chat_id)


@dp.callback_query_handler(text_startswith="list_send:", state=ListSpam.WaitMessage)
async def list_spam_confirm(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.finish()
    try:
        await call.message.delete()
    except Exception:
        pass
    tg_ids, payload = data.get("list_tg_ids"), data.get("broadcast_payload")
    if call.data != "list_send:yes" or not tg_ids or not payload:
        await call.message.answer("⚠️ Рассылка по списку отменена.", reply_markup=admin_back_kb('messages_menu'))
        return
    asyncio.create_task(_run_list_spam(call.from_user.id, tg_ids, payload))
    await call.message.answer(f"⚠️ Рассылка по списку началась ({len(tg_ids)} получателей). "
                              f"Пришлю отчёт, когда закончу.", reply_markup=admin_back_kb('messages_menu'))
