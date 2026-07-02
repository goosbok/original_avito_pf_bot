import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp, bot
from utils.sqlite3 import (
    get_user, update_user, delete_user, all_users, get_all_vip, get_tg_id_for_user,
    get_all_telegram_ids,
)
from utils.other import get_user_string_without_first_name
from keyboards.inline_keyboards import admin_back_kb, user_select_kb
from .admin_base import Admin, find_user

logger = logging.getLogger(__name__)


async def _show_candidate(target, state: FSMContext) -> None:
    """Send current candidate card with pagination keyboard."""
    data = await state.get_data()
    candidates = data["candidates"]
    page = data["page"]
    usr = candidates[page]
    usr_str = await get_user_string_without_first_name(usr)
    text = (
        f"🔍 Найдено {len(candidates)} пользователей. Выберите нужного:\n\n"
        f"🐹 {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>"
    )
    kb = user_select_kb(page, len(candidates))
    msg = target.message if hasattr(target, "message") else target
    await msg.answer(text, reply_markup=kb)


async def _proceed(target, state: FSMContext, usr: dict, action: str) -> None:
    """Route to the appropriate next step for the given action."""
    msg = target.message if hasattr(target, "message") else target
    if action == "balance":
        usr_str = await get_user_string_without_first_name(usr)
        await msg.answer(f"Выбран\n🐹 Пользователь {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>")
        await state.update_data(usr=usr)
        await balance.change_balance.set()
        await msg.answer("💳 Введите новый баланс:")
    elif action == "del":
        usr_str = await get_user_string_without_first_name(usr)
        try:
            delete_user(usr['id'])
            await msg.answer(f"✅ Пользователь {usr_str} успешно удален!", reply_markup=admin_back_kb('users_man'))
        except Exception as e:
            logger.exception("handler error")
            await msg.answer(f"❎ Ошибка удаления пользователя!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif action == "vip_set":
        usr_str = await get_user_string_without_first_name(usr)
        adm_tg_id = target.from_user.id if hasattr(target, "from_user") else None
        adm_usr = get_user(id=adm_tg_id) if adm_tg_id else None
        try:
            if usr['is_vip'] != 1:
                update_user(id=usr['id'], is_vip=1)
                await msg.answer(f"🐹 Пользователь {usr_str} получил 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
                tg_id = get_tg_id_for_user(usr['id'])
                if tg_id and adm_usr:
                    await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} установил Вам 💎VIP-статус!")
            else:
                await msg.answer(f"🐹 Пользователь {usr_str} уже имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        except Exception as e:
            logger.exception("handler error")
            await msg.answer(f"❎ Ошибка установки VIP-статуса!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif action == "vip_unset":
        usr_str = await get_user_string_without_first_name(usr)
        adm_tg_id = target.from_user.id if hasattr(target, "from_user") else None
        adm_usr = get_user(id=adm_tg_id) if adm_tg_id else None
        try:
            if usr['is_vip'] != 0:
                update_user(id=usr['id'], is_vip=0)
                await msg.answer(f"🐹 Пользователь {usr_str} потерял 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
                tg_id = get_tg_id_for_user(usr['id'])
                if tg_id and adm_usr:
                    await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} отменил Вам 💎VIP-статус!")
            else:
                await msg.answer(f"🐹 Пользователь {usr_str} не имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        except Exception as e:
            logger.exception("handler error")
            await msg.answer(f"❎ Ошибка снятия VIP-статуса!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()


async def handle_user_input(message: types.Message, state: FSMContext, action: str) -> None:
    """Shared entry point for all four admin user flows."""
    users = await find_user(message.text)
    if len(users) == 0:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif len(users) == 1:
        await _proceed(message, state, users[0], action)
    else:
        await state.update_data(candidates=users, page=0, pending_action=action)
        await Admin.select_user.set()
        await _show_candidate(message, state)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("usel:"), state=Admin.select_user)
async def usel_nav(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split(":")[1]
    if action == "noop":
        await call.answer()
        return
    if action == "cancel":
        await call.answer()
        await state.finish()
        await call.message.answer("❌ Отменено.", reply_markup=admin_back_kb('users_man'))
        return
    await call.answer()
    data = await state.get_data()
    candidates = data["candidates"]
    page = data["page"]
    if action == "prev":
        page = max(0, page - 1)
    elif action == "next":
        page = min(len(candidates) - 1, page + 1)
    elif action == "pick":
        pending = data["pending_action"]
        await call.answer()
        try:
            await call.message.delete()
        except Exception:
            pass
        await _proceed(call, state, candidates[page], pending)
        return
    await state.update_data(page=page)
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_candidate(call.message, state)


class balance(StatesGroup):
    select_user = State()
    change_balance = State()


class vip(StatesGroup):
    set_status = State()
    unset_status = State()


@dp.callback_query_handler(text="users_ids")
async def call_users_ids(call: types.CallbackQuery):
    user_id = call.from_user.id
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    ids = get_all_telegram_ids()
    with open("ids.txt", "w") as file:
        for id in ids:
            file.write(str(id) + "\n")

    file_path = "ids.txt"
    with open(file_path, 'rb') as file:
        await bot.send_document(user_id, document=InputFile(file), reply_markup=admin_back_kb('users_man'))


@dp.callback_query_handler(text="users_len")
async def call_users_len(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    usr_cnt = len(all_users())
    await call.message.answer(f"🤖 в базе зарегистрировано {usr_cnt} 🐹 пользователей", reply_markup=admin_back_kb('users_man'))


@dp.callback_query_handler(text="del_user")
async def del_user(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя 🐹 для удаления!")
    await Admin.del_user.set()
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.message_handler(state=Admin.del_user)
async def del_usr(message: types.Message, state: FSMContext):
    delUser = await find_user(message.text)
    if not delUser:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
        return
    usr_str = await get_user_string_without_first_name(delUser)
    try:
        delete_user(delUser['id'])
        await message.answer(f"✅ Пользователь {usr_str} успешно удален!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        logger.exception("handler error")
        await message.answer(f"❎ Ошибка удаления пользователя!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()


@dp.callback_query_handler(text="user_balance")
async def usr_balance(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя 🐹 баланс, которого надо изменить:")
    await balance.select_user.set()
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.message_handler(state=balance.select_user)
async def usr_sel(message: types.Message, state: FSMContext):
    usr = await find_user(message.text)
    if not usr:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
        return
    try:
        usr_str = await get_user_string_without_first_name(usr)
        await message.answer(f"Выбран\n🐹 Пользователь {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>")
        await state.update_data(usr=usr)
        await balance.change_balance.set()
        await message.answer("💳 Введите новый баланс:")
    except Exception as e:
        logger.exception("handler error")
        await message.answer(f"⚠️ Ошибка!:\n{e}")
        await state.finish()


@dp.message_handler(state=balance.change_balance)
async def change_balance(message: types.Message, state: FSMContext, user_id: int):
    new_balance = message.text
    state_data = await state.get_data()
    ch_usr = state_data['usr']
    adm_user = get_user(id=user_id)
    usr_str = await get_user_string_without_first_name(ch_usr)
    try:
        await message.answer(f"Пользователю {usr_str} установлен баланс <b>{new_balance}руб.</b>", reply_markup=admin_back_kb('users_man'))
        update_user(id=ch_usr['id'], balance=new_balance)
        tg_id = get_tg_id_for_user(ch_usr['id'])
        if tg_id:
            await bot.send_message(chat_id=tg_id, text=f"<b>🤖 Пользователь @{adm_user['user_name']} установил Ваш 💳 баланс на {new_balance}руб.</b>")
        await state.finish()
    except Exception as e:
        logger.exception("handler error")
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()


@dp.callback_query_handler(text="set_vip")
async def set_vip(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя:")
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await vip.set_status.set()


@dp.message_handler(state=vip.set_status)
async def vip_set(message: types.Message, state: FSMContext, user_id: int):
    try:
        usr = await find_user(message.text)
        adm_usr = get_user(id=user_id)
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 1:
            update_user(id=usr['id'], is_vip=1)
            await message.answer(f"🐹 Пользователь {usr_str} получил 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} установил Вам 💎VIP-статус!")
        else:
            await message.answer(f"🐹 Пользователь {usr_str} уже имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()


@dp.callback_query_handler(text="delete_vip")
async def unset_vip(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя:")
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await vip.unset_status.set()


@dp.message_handler(state=vip.unset_status)
async def vip_unset(message: types.Message, state: FSMContext, user_id: int):
    try:
        usr = await find_user(message.text)
        adm_usr = get_user(id=user_id)
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 0:
            update_user(id=usr['id'], is_vip=0)
            await message.answer(f"🐹 Пользователь {usr_str} потерял 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} отменил Вам 💎VIP-статус!")
        else:
            await message.answer(f"🐹 Пользователь {usr_str} не имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()


@dp.callback_query_handler(text="get_vip", state="*")
async def call_get_vip(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug("could not delete message", exc_info=True)

    STR = "<b>👑 Список VIP - пользователей\n</b>"
    all_vip = get_all_vip()
    for user in all_vip:
        user_str = await get_user_string_without_first_name(user)
        STR += f"{user_str}\n"
    await call.message.answer(STR, reply_markup=admin_back_kb('users_man'))


@dp.message_handler(content_types=types.ContentType.STICKER)
async def handle_sticker(message: types.Message):
    sticker_id = message.sticker.file_id
    await message.answer(f"ID стикера: {sticker_id}")
