import logging
import re
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, ContentType, InlineKeyboardButton
from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup

from utils.error_handler import report_handler_error
from data.loader import dp, bot
from keyboards.users_menu import (
    get_menu_kb, user_back_kb, menu_btn_kb,
    pf_kb, pf_period_kb,
    yes_no_contact_kb, yes_no_order_kb,
)
from utils.other import (
    get_user_string_without_first_name,
    get_days_suffix, format_decimal,
    split_messages, str2bool,
    link_cleaner,
)
from utils.sender import send_admins
from utils.sqlite3 import (
    get_user,
    add_order, get_users_last_order,
    update_user,
    get_string, get_price,
)
from services.funnel import track_step

logger = logging.getLogger(__name__)
logger.info("pf_order.py loaded — registering handlers")


class EnterData(StatesGroup):
    period = State()
    pf = State()


@dp.callback_query_handler(text_startswith="tarifs:", state='*')
async def tarif(call: CallbackQuery, state: FSMContext, user_id: int):
    logger.info("tarif callback: tg_id=%s data=%s", call.from_user.id, call.data)
    async with state.proxy() as data:
        if 'links' not in data:
            await state.finish()
        else:
            links = data['links']
            await state.finish()
            data['links'] = links
    tarif_name = call.data.split(":")[1]
    if tarif_name in {"pf"}:
        track_step(user_id=user_id, service="pf_avito", step="view_tariff")
    if tarif_name == "pf":
        STR = get_string('srt_select_variant_pf')
        image = f"images/avito_pf.jpg"
        with open(image, 'rb') as photo:
            await call.message.answer_photo(photo=photo, caption=STR, reply_markup=pf_kb())

    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(text="yandex_pf", state='*')
async def yandex_pf(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")


@dp.callback_query_handler(text="review_bonus", state='*')
async def call_review_bonus(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")


@dp.callback_query_handler(text_startswith="pf:", state='*')
async def pf(call: CallbackQuery, state: FSMContext, user_id: int):
    logger.info("pf callback: tg_id=%s data=%s", call.from_user.id, call.data)
    call_data = call.data.split(":")
    if call_data[1].isdigit():
        track_step(user_id=user_id, service="pf_avito", step="select_period")
        days = call_data[1]
        days_str = get_days_suffix(days)
        await state.update_data(days=days)
        price = get_price('price_avito_pf')
        f_price = format_decimal(price)
        STR = get_string('str_pf_text')
        await call.message.answer(STR.format(days, days_str, f_price), reply_markup=pf_period_kb(days))
    elif call_data[1] == "enter-period":
        STR = get_string('str_enter_days')
        await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))
        await EnterData.period.set()
    elif call_data[1] == "enter-pf":
        STR = get_string('str_enter_pf')
        await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))
        await EnterData.pf.set()
    else:
        async with state.proxy() as data:
            days = call.data.split("-")[0].split(":")[1]
            days_str = get_days_suffix(days)
            data['days'] = days
            data['fix'] = call.data.split("-")[1]
            data['period'] = f"{days} {days_str}"
            data['count'] = get_price('price_avito_pf')
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * int(days))
        track_step(user_id=user_id, service="pf_avito", step="select_count")
        if 'links' not in data:
            STR = get_string('str_pf_links')
            await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'), disable_web_page_preview=True)
        else:
            await place_order(call.message, state, user_id)
        await state.set_state("place_order")

    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.message_handler(state=EnterData.period)
async def enter_period_func(message: types.Message, state: FSMContext, user_id: int):
    if message.text.isdigit() and int(message.text) >= 1:
        days = message.text
        days_str = get_days_suffix(days)
        price = get_price('price_avito_pf')
        STR = get_string('str_pf_text')
        f_price = format_decimal(price)
        await message.answer(STR.format(days, days_str, f_price), reply_markup=pf_period_kb(days))
        await state.update_data(days=days)
        track_step(user_id=user_id, service="pf_avito", step="select_period")
    else:
        STR = get_string('str_bad_number')
        await message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))


@dp.message_handler(state=EnterData.pf)
async def enter_pf_func(message: types.Message, state: FSMContext, user_id: int):
    state_data = await state.get_data()
    days = state_data['days']
    if message.text.isdigit() and int(message.text) >= 5:
        async with state.proxy() as data:
            days_str = get_days_suffix(days)
            data['days'] = days
            data['fix'] = int(message.text)
            data['period'] = f"{days} {days_str}"
            data['count'] = get_price('price_avito_pf')
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * int(days))
        track_step(user_id=user_id, service="pf_avito", step="select_count")
        await state.set_state("place_order")
        STR = get_string('str_pf_links')
        await message.answer(STR, reply_markup=user_back_kb('user:tarif'))
    else:
        STR = get_string('str_bad_number')
        await message.answer(STR, reply_markup=user_back_kb('user:tarif'))


def extract_avito_links(text: str) -> list:
    """Извлекает уникальные ссылки avito.ru из произвольного текста."""
    lines = text.split('\n')
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('http'):
            while i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and ' ' not in nxt and not nxt.startswith('http'):
                    line += nxt
                    i += 1
                else:
                    break
        merged.append(line)
        i += 1

    full_text = ' '.join(merged)
    raw_urls = re.findall(r'https?://(?:www\.)?avito\.ru/\S+', full_text)

    seen = set()
    unique_links = []
    for url in raw_urls:
        url = link_cleaner(url)
        if url not in seen:
            seen.add(url)
            unique_links.append(url)
    return unique_links


@dp.message_handler(content_types=ContentType.TEXT, state='place_order')
async def place_order(message: Message, state: FSMContext, user_id: int):
    state_data = await state.get_data()
    links = state_data.get('links') or extract_avito_links(message.text)
    if links:
        async with state.proxy() as data:
            if 'links' not in data:
                data['links'] = links
            data['total_price'] *= len(data['links'])
        track_step(user_id=user_id, service="pf_avito", step="links_valid")
        await state.set_state("order_checkout")
        STR = get_string('str_pf_contacts')
        msg = await message.answer(STR, reply_markup=yes_no_contact_kb())
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
        except Exception:
            logger.debug("could not delete message")
    else:
        ERR = get_string('str_bad_link')
        await message.answer(ERR.format('avito.ru'))


@dp.callback_query_handler(text_startswith="contact:", state='*')
async def order_contact_set(call: CallbackQuery, state: FSMContext, user_id: int):
    answer = str2bool(call.data.split(":")[1])

    async with state.proxy() as data:
        data['contact'] = answer
    track_step(user_id=user_id, service="pf_avito", step="contact_chosen")
    if 'total_price' in data:
        STR = get_string('str_debet_pf')
        f_price = format_decimal(int(data['total_price']))
        await call.message.answer(STR.format(f_price), reply_markup=yes_no_order_kb())
        await call.message.delete()
    else:
        from utils.error_handler import error_kb
        STR = get_string('str_error')
        await call.message.answer(STR, reply_markup=error_kb())


@dp.callback_query_handler(text="order_confirm", state='*')
async def confirm_order(call: CallbackQuery, state: FSMContext, user_id: int):
    track_step(user_id=user_id, service="pf_avito", step="order_confirmed")
    user = get_user(id=user_id)
    async with state.proxy() as data:
        if 'total_price' not in data:
            from utils.error_handler import error_kb
            STR = get_string('str_error')
            await call.message.answer(STR, reply_markup=error_kb())
            try:
                await call.message.delete()
            except Exception:
                pass
            return
        if user['balance'] >= data['total_price']:
            try:
                update_user(id=user['id'], balance=user['balance'] - data['total_price'])
                add_order(
                    user_id=user['id'],
                    price=data['total_price'],
                    position_name=f"{data['days']}/{data['fix']}",
                    status="Posted",
                    links=str(data['links']),
                    contacts=data['contact'],
                    user_name=user['user_name'],
                )
                ADM_MSG = get_string('str_new_order_text')
                order = get_users_last_order(user['id'])
                ord_id = order['increment']
                f_price = format_decimal(order['price'])
                user_str = await get_user_string_without_first_name(user)
                pos_name = order['position_name']
                status = order['status']
                con_str = 'Да' if order['contacts'] else 'Нет'
                ord_date = order['date']
                links_cnt = len(order['links'])
                links_str = ""
                for link in order['links'].split(','):
                    link = link.replace("'", "")
                    links_str += f"\n<code>{link}</code>"
                ADM_MSG = ADM_MSG.format(
                    ord_id, f_price, user_str, pos_name, status,
                    con_str, ord_date, links_cnt, links_str,
                )
                if len(ADM_MSG) < 4096:
                    await send_admins(ADM_MSG)
                else:
                    for msg in split_messages(ADM_MSG.split('\n'), '\n'):
                        await send_admins(msg)
                USR_MSG = get_string('str_order_confirm').format(ord_id)
                await call.message.answer(USR_MSG, reply_markup=get_menu_kb())
                logger.info(
                    "order placed: user_id=%s price=%s days=%s fix=%s",
                    user_id, data['total_price'], data.get('days'), data.get('fix'),
                )
            except Exception as exc:
                await report_handler_error(
                    exc,
                    logger=logger,
                    context={
                        "handler": "confirm_order",
                        "user_id": user_id,
                        "balance": user['balance'],
                        "total_price": data.get('total_price'),
                        "days": data.get('days'),
                        "links_count": len(str(data.get('links', '')).split(',')),
                    },
                    reply_target=call,
                )
                await state.finish()
                return
        else:
            await state.reset_data()
            STR = get_string('str_not_enough_money')
            balance = format_decimal(user['balance'])
            f_amount = format_decimal(data['total_price'])
            f_ref = format_decimal(int(data['total_price']) - int(user['balance']))
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
