import logging
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup

from data import config
from data.loader import dp
from keyboards.users_menu import (
    get_menu_kb, menu_btn_kb,
    reviews_kb, reviews_count, yes_no_reviews,
)
from utils.other import (
    get_user_string_without_first_name,
    format_decimal,
)
from utils.sender import send_admins
from utils.sqlite3 import (
    get_user,
    update_user,
    get_string, get_setting, get_price,
    add_order_reviews, get_users_last_order_reviews,
    add_order_delreview, get_users_last_order_delreviews,
)
from data.config import services

logger = logging.getLogger(__name__)
logger.info("reviews.py loaded — registering handlers")


class review(StatesGroup):
    add_link = State()


class avito(StatesGroup):
    delete_review = State()


def get_nick(param):
    value = get_setting(param)
    if value:
        if not value.startswith('@'):
            value = '@' + value
        return value
    else:
        return None


@dp.callback_query_handler(text="reviews", state='*')
async def call_reviews_button(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    await state.finish()
    STR = get_string('str_review_start')
    with open('images/logo_small.jpg', 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=reviews_kb())


@dp.callback_query_handler(text_startswith="reviews:", state="*")
async def call_reviews_service(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    service = call.data.split(":")[1]

    if service == "vk":
        STR = get_string('str_reviews_vk')
        price = get_price('price_vk')
    elif service == "yandex":
        STR = get_string('str_reviews_yandex')
        price = get_price('price_yandex')
    elif service == "avito":
        STR = get_string('str_reviews_avito')
        price = get_price('price_avito')
    elif service == "2gis":
        STR = get_string('str_reviews_2gis')
        price = get_price('price_2gis')
    elif service == "flamp":
        STR = get_string('str_reviews_flamp')
        price = get_price('price_flamp')
    elif service == "google":
        STR = get_string('str_reviews_flamp')
        price = get_price('price_google')

    await state.update_data(service=service, price=price)
    image = f"images/review_{service}.jpg"
    with open(image, 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=reviews_count(service))


@dp.callback_query_handler(text_startswith="rev_price:", state="*")
async def call_reviews_service_price(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")

    param = call.data.split(":")[1]
    state_data = await state.get_data()
    price = state_data['price']
    amount = int(price[param])*int(param)
    await state.update_data(reviews_count=param, amount=amount)
    STR = get_string('str_reviews_add_link')
    await call.message.answer(STR)
    await review.add_link.set()


@dp.message_handler(text_startswith="https:", state=review.add_link)
async def review_add_link(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    reviews_count_val = state_data['reviews_count']
    service = services[f"{state_data['service']}"]
    price = state_data['price']
    formated_price = format_decimal(int(price[reviews_count_val]))
    amount = format_decimal(int(state_data['amount']))
    STR = get_string('str_review_order_confirm')
    STR = STR.format(reviews_count_val, service, formated_price, amount)

    if state_data['service'] in message.text:
        await state.update_data(link=message.text)
        await message.answer(STR, reply_markup=yes_no_reviews())
    else:
        STR1 = get_string('str_review_bad_link')
        await message.answer(STR1)


@dp.callback_query_handler(text="rev_confirm", state='*')
async def call_confirm_review(call: CallbackQuery, state: FSMContext, user_id: int):
    user = get_user(id=user_id)
    state_data = await state.get_data()
    amount = state_data['amount']
    service = state_data['service']
    link = state_data['link']
    if user['balance'] >= int(amount):
        update_user(id=user['id'], balance=user['balance']-int(amount))
        add_order_reviews(user_id=user['id'], price=amount, service=service, link=link, status='Posted')
        order = get_users_last_order_reviews(user_id)
        manager = get_nick('nick_manager_reviews')
        STR = get_string('str_review_confirm').format(order['increment'], manager)
        MSG = get_string('str_new_review_admin_report')
        famount = format_decimal(amount)
        user_str = await get_user_string_without_first_name(user)
        MSG = MSG.format(order['increment'], famount, user_str, services[service], order['status'], order['date'], order['link'])
        await call.message.answer(STR, reply_markup=get_menu_kb())
        await send_admins(MSG)
    else:
        await state.reset_data()
        STR = get_string('str_not_enough_money')
        balance = format_decimal(user['balance'])
        f_amount = format_decimal(amount)
        f_ref = format_decimal(int(amount) - int(user['balance']))
        BTN = get_string('btn_refill_balance')
        button = InlineKeyboardButton(
            text=BTN,
            callback_data="profile:ref_bal"
        )
        keyboard = menu_btn_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        await call.message.answer(STR.format(balance, f_amount, f_ref), reply_markup=keyboard)

    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(text="avito_del_review", state='*')
async def call_avito_del_review(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    STR = get_string('str_delete_review')
    price = get_price('price_avito_del_review')
    f_price = format_decimal(price)
    STR = STR.format(f_price)
    await call.message.answer(STR)
    await avito.delete_review.set()


@dp.message_handler(text_startswith="https:", state=avito.delete_review)
async def avito_del_review(message: types.Message, state: FSMContext, user_id: int):
    link = message.text
    user = get_user(id=user_id)
    amount = int(get_price('price_avito_del_review'))
    service = 'avito'
    if user['balance'] >= amount:
        update_user(id=user['id'], balance=user['balance']-int(amount))
        add_order_delreview(user['id'], amount, service, link, 'Размещен')
        order = get_users_last_order_delreviews(user_id)
        manager = get_nick('manager_nick')
        STR = get_string('str_review_confirm').format(order['increment'], manager)
        MSG = get_string('str_new_review_admin_report')
        famount = format_decimal(amount)
        user_str = await get_user_string_without_first_name(user)
        MSG = MSG.format(order['increment'], famount, user_str, services[service], order['status'], order['date'], order['link'])
        await message.answer(STR, reply_markup=get_menu_kb())
        await send_admins(MSG)
    else:
        await state.reset_data()
        STR = get_string('str_not_enough_money')
        balance = format_decimal(user['balance'])
        f_amount = format_decimal(amount)
        f_ref = format_decimal(int(amount) - int(user['balance']))
        BTN = get_string('btn_refill_balance')
        button = InlineKeyboardButton(
            text=BTN,
            callback_data="profile:ref_bal"
        )
        keyboard = menu_btn_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        await message.answer(STR.format(balance, f_amount, f_ref), reply_markup=keyboard)
