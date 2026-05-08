import logging
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery
from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp
from keyboards.users_menu import (
    get_menu_kb, user_back_kb,
    seo_boost_kb, seo_months, seo_order_confirm,
)
from utils.other import (
    format_decimal,
    declension_months,
    get_user_string_without_first_name,
)
from utils.sender import send_admins
from utils.sqlite3 import (
    get_user,
    update_user,
    get_string, get_setting, get_price, get_nick,
    add_order_seo, get_user_last_order_seo,
)

logger = logging.getLogger(__name__)
logger.info("seo.py loaded — registering handlers")


class seoboost(StatesGroup):
    link = State()


@dp.callback_query_handler(text="seo_boost", state='*')
async def call_seo_boost(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    MSG = get_string('str_seo_main')
    await call.message.answer(MSG, reply_markup=seo_boost_kb())


@dp.callback_query_handler(text="seo_howto", state='*')
async def call_seo_howto(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    MSG = get_string('str_seo_howto')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))


@dp.callback_query_handler(text="seo_why", state='*')
async def call_seo_why(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    MSG = get_string('str_seo_why')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))


@dp.callback_query_handler(text="seo_result", state='*')
async def call_seo_result(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    MSG = get_string('str_seo_result')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))


@dp.callback_query_handler(text="seo_order", state='*')
async def call_seo_order(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    price = get_price('price_seo')
    f_price = format_decimal(price)
    MSG = get_string('str_seo_order_start')
    await call.message.answer(MSG.format(f_price), reply_markup=seo_months())


@dp.callback_query_handler(text_startswith="seo:", state='*')
async def user_call_seo_months_count(call: CallbackQuery, state: FSMContext):
    await state.finish()
    months_count = call.data.split(':')[1]
    MSG = get_string('str_seo_enter_link')
    months_suffix = declension_months(int(months_count))
    await call.message.answer(MSG.format(months_count, months_suffix))
    await state.update_data(months=months_count)
    await state.update_data(suffix=months_suffix)
    await seoboost.link.set()


@dp.message_handler(state=seoboost.link)
async def seo_link_add(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    months_count = int(state_data['months'])
    months_suffix = state_data['suffix']
    price = int(get_price('seo_price'))
    link = message.text
    total_price = price * months_count
    MSG = get_string('str_seo_order')
    await state.update_data(total_price=total_price)
    await state.update_data(link=link)
    f_price = format_decimal(int(total_price))
    MSG = MSG.format(months_count, months_suffix, link, f_price)
    await message.answer(MSG, reply_markup=seo_order_confirm(total_price))


@dp.callback_query_handler(text_startswith="seo_yes:", state='*')
async def user_call_seo_yes(call: CallbackQuery, state: FSMContext, user_id: int):
    state_data = await state.get_data()
    if not all(k in state_data for k in ('months', 'total_price', 'link')):
        STR = get_string('str_error') or '⚠️ Заказ устарел. Начните оформление заново.'
        await call.message.answer(STR, reply_markup=get_menu_kb())
        try:
            await call.message.delete()
        except Exception:
            pass
        return
    months_count = int(state_data['months'])
    total_price = state_data['total_price']
    link = state_data['link']
    user = get_user(id=user_id)
    manager = get_nick('manager_nick')
    if user['balance'] >= total_price:
        update_user(id=user['id'], balance=user['balance']-total_price)
        add_order_seo(user_id=user['id'], price=total_price, months=months_count, status="Размещён",
        link=str(link).replace(']','').replace('[',''))
        adm_message = get_string('str_seo_admin_msg')
        o = get_user_last_order_seo(user_id)
        f_price = format_decimal(int(o['price']))
        username = await get_user_string_without_first_name(user)
        MSG = adm_message.format(o['increment'], o['months'], f_price, username, o['status'], o['date'], o['link'])
        await send_admins(MSG)
        msg = get_string('str_seo_order_confirm').format(o['increment'], manager)
        await call.message.answer(msg, reply_markup=get_menu_kb())
    else:
        STR = get_string('str_not_enough_money')
        f_balance = format_decimal(int(user['balance']))
        f_price = format_decimal(total_price)
        f_diff = format_decimal(int(total_price - user['balance']))
        STR = STR.format(f_balance, f_price, f_diff)
        await call.message.answer(STR, reply_markup=get_menu_kb())
        await state.reset_data()

    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
