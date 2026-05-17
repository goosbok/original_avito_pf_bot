import logging
import string
import random

from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp, bot
from utils.sqlite3 import get_admins, get_user, get_order, delete_order
from design import order_text

logger = logging.getLogger(__name__)


class Admin(StatesGroup):
    del_promik = State()
    new_promik = State()
    new_promik_price = State()
    del_user = State()
    user_info = State()


class hammster(StatesGroup):
    set_login = State()


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


random_combination = generate_random_string(8)


async def find_user(param):
    if param.isdigit():
        user = get_user(id=param)
    else:
        if param[0] != '@':
            try:
                user = get_user(user_name=param)
            except Exception as e:
                logger.exception("get_user_string: user not found param=%s", param)
        else:
            try:
                user = get_user(user_name=param[1:])
            except Exception as e:
                logger.exception("get_user_string: user not found param=%s", param)
    return user


@dp.message_handler(commands=['admin'], state='*')
async def adminka(message: Message, state: FSMContext):
    await state.finish()
    # Admins are stored as Telegram IDs; compare against from_user.id, not the
    # internal user PK that the middleware injects as user_id.
    if str(message.from_user.id) in get_admins():
        from keyboards.inline_keyboards import admin
        await bot.send_message(chat_id=message.from_user.id, text="👋 Добро пожаловать в админ панель!", reply_markup=admin())


@dp.callback_query_handler(text="admin_back", state='*')
async def admin_back(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    if str(call.from_user.id) in get_admins():
        from keyboards.inline_keyboards import admin
        await call.message.answer("👋 Админ-меню", reply_markup=admin())
        try:
            await call.message.delete()
        except Exception:
            pass


@dp.message_handler(commands="delete")
async def cmd_del_order(message: types.Message):
    order_id = message.text[8:]
    if str(message.from_user.id) in get_admins():
        try:
            order = get_order(id=order_id)
            delete_order(id=order_id)
            await message.answer(text=f"⚠️ Заказ <b>{order_id}:</b>\n{order_text(order)}\nУспешно удален!")
        except Exception as e:
            await message.answer(text=f"⚠️ Заказ <b>{order_id}</b> не найден!\n{e}")


# Create a dictionary to store user entered promo codes
user_promo_codes = {}


@dp.callback_query_handler(text="to_admin_menu", state='*')
async def to_admin_menu(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    await state.finish()
    from keyboards.inline_keyboards import admin
    await bot.send_message(chat_id=call.from_user.id, text="👋 Добро пожаловать в админ панель!", reply_markup=admin())
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.callback_query_handler(text="users_man", state='*')
async def profile(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
    from keyboards.inline_keyboards import users_man_kb
    await call.message.answer("🐹 Управление пользователями:", reply_markup=users_man_kb())
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
