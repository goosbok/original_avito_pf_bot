import logging
import asyncio
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram import types
from aiogram.utils.exceptions import RetryAfter

from data import config
from data.loader import dp, bot
from keyboards.users_menu import (
    get_menu_kb, user_back_kb, menu_btn_kb,
    pf_kb,
    profile_kb,
    show_user_order_by_index,
)
from utils.other import (
    get_user_string_without_first_name,
    format_decimal,
    str2bool,
    get_referals_count,
)
from utils.sqlite3 import (
    get_user,
    user_orders_all, get_order,
    get_string, get_setting,
)
from design import listord_array

logger = logging.getLogger(__name__)
logger.info("profile.py loaded — registering handlers")


def get_nick(param):
    value = get_setting(param)
    if value:
        if not value.startswith('@'):
            value = '@' + value
        return value
    else:
        return None


@dp.callback_query_handler(text="user:profile", state='*')
async def user_profile(call: CallbackQuery, state: FSMContext, user_id: int):
    logger.info("user:profile callback: tg_id=%s data=%s", call.from_user.id, call.data)
    await state.finish()
    user = get_user(id=user_id)
    if user is None:
        await call.message.answer(get_string('str_error') or '⚠️ Ошибка', reply_markup=get_menu_kb())
        try:
            await call.message.delete()
        except Exception:
            logger.debug("user:profile: could not delete message")
        return
    profile_string = get_string('str_user_profile')
    ref_link = f"{config.botlink}?start={user_id}"
    rferals_count = get_referals_count(user)
    f_balance = format_decimal(user['balance'])
    await call.message.answer(
        text=profile_string.format(f_balance, ref_link, rferals_count),
        disable_web_page_preview=True,
        reply_markup=profile_kb()
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("user:profile: could not delete message")


@dp.callback_query_handler(text_startswith="profile:", state='*')
async def profile(call: CallbackQuery, state: FSMContext, user_id: int):
    logger.info("profile callback: tg_id=%s data=%s", call.from_user.id, call.data)
    await state.finish()
    data = call.data.split(":")
    action = data[1]
    if action == 'ref_bal':
        if str2bool(get_setting('payment_work')):
            await state.set_state("refill_balance")
            STR = get_string('str_refill_balance_text')
            await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))
        else:
            STR = get_string('str_payment_not_work')
            manager_nick = get_nick('manager_nick')
            await call.message.answer(STR.format(manager_nick), reply_markup=user_back_kb('user:profile'))
    elif action == 'listord':
        try:
            orders = user_orders_all(user_id) or []
            if not orders:
                STR = get_string('str_error_get_orders') or '📭 У вас пока нет заказов.'
                await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))
            else:
                orders_array = listord_array(orders)
                await state.update_data(orders=orders, array=orders_array)
                await call.message.answer(
                    f"Страница 1 из {len(orders)}\n{orders_array[0]}",
                    reply_markup=show_user_order_by_index(len(orders) - 1, len(orders)),
                )
        except Exception:
            logger.exception("profile listord: failed for tg_id=%s", call.from_user.id)
            STR = get_string('str_error')
            await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))
    elif action == 'ordstatus':
        await state.set_state("check_order")
        STR = get_string('str_input_order_number')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))

    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(text_startswith="ordr:", state="*")
async def user_call_show_order_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")

    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = listord_array(orders)

    try:
        index = int(call.data.split(":")[1])
        orders_array = state_data['array']
        await state.update_data(index=index, array=orders_array)
        await call.message.answer(
            f"Страница {index+1} из {len(orders)}\n{orders_array[index]}",
            reply_markup=show_user_order_by_index(index, len(orders))
        )
    except Exception:
        STR = get_string('str_error')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))


@dp.callback_query_handler(text_startswith="user_show_all:", state="*")
async def user_call_show_by_status(call: types.CallbackQuery, state: FSMContext, user_id: int):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    action = call.data.split(':')[1]

    if action == 'completed':
        orders = []
        for order in user_orders_all(user_id):
            if order['status'] == 'Completed':
                orders.append(order)
    elif action == 'posted':
        orders = []
        for order in user_orders_all(user_id):
            if order['status'] == 'Posted':
                orders.append(order)
    try:
        orders_array = listord_array(orders)
        await state.update_data(orders=orders, array=orders_array)
        await call.message.answer(
            f"Страница 1 из {len(orders)}\n{orders_array[len(orders)-1]}",
            reply_markup=show_user_order_by_index(len(orders)-1, len(orders))
        )
    except Exception:
        STR = get_string('str_no_posted_orders')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))


@dp.callback_query_handler(text="user_show_all:orders", state="*")
async def user_call_show_all_orders(call: types.CallbackQuery, state: FSMContext, user_id: int):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    state_data = await state.get_data()
    orders = user_orders_all(user_id)
    if 'index' in state_data:
        index = state_data['index']
    else:
        index = len(orders) - 1
    if orders:
        orders_array = listord_array(orders)
        for i in range(len(orders_array)):
            try:
                if i < len(orders_array) - 1:
                    await call.message.answer(orders_array[i])
                else:
                    await call.message.answer(orders_array[i], reply_markup=user_back_kb('profile:listord'))
            except RetryAfter as e:
                wait_time = e.timeout
                logger.warning("flood control: waiting %s sec for tg_id=%s", wait_time, call.from_user.id)
                await asyncio.sleep(wait_time)
                if i < len(orders_array) - 1:
                    await call.message.answer(orders_array[i])
                else:
                    await call.message.answer(orders_array[i], reply_markup=user_back_kb('profile:listord'))
    else:
        STR = get_string('str_error_get_orders')
        await call.message.answer(STR, reply_markup=user_back_kb(f'user:profile'))


@dp.callback_query_handler(text_startswith="repeat:", state="*")
async def call_repeat(call: types.CallbackQuery, state: FSMContext, user_id: int):
    index = call.data.split(":")[1]
    order = user_orders_all(user_id)[int(index)]
    links = order['links'].split('\n')
    async with state.proxy() as data:
        data['links'] = links
    image = f"images/avito_pf.jpg"
    STR = get_string('str_select_action')
    with open(image, 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=pf_kb())


@dp.message_handler(lambda message: message.text.isdigit(), state="check_order")
async def check_order(message: Message, state: FSMContext, user_id: int):
    await state.finish()
    order_id = int(message.text)
    try:
        order = get_order(order_id)
        if order['user_id'] == user_id:
            STR = get_string('str_order_status_txt')
            STR = STR.format(order['increment'], order['status'])
            msg = await message.answer(STR, reply_markup=menu_btn_kb())
        else:
            STR = get_string('str_not_your_order')
            msg = await message.answer(STR, reply_markup=menu_btn_kb())
    except TypeError:
        STR = get_string('no_such_order')
        msg = await message.answer(STR, reply_markup=menu_btn_kb())

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
    except Exception:
        logger.debug("could not delete message")
