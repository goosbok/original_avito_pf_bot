import colorama
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.types import InputMediaVideo
from aiogram.utils.markdown import hlink
from aiogram import types
#from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, IDFilter
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import RetryAfter

from data import config
from data.config import price_google, price_yandex, price_vk, price_flamp, price_2gis, price_avito, services
from data.loader import dp, bot
from keyboards.users_menu import *
from utils.other import *
from utils.sender import *
from utils.sqlite3 import get_user, add_refill, user_orders_all, add_order, get_order, update_user, get_users_last_order, delete_user, get_refill

from handlers.admin_functions import *
#from handlers.robokassa import *
from utils.yookassa_refil import create_invoice, check_payment_status
import asyncio
from utils.msql import sql_add_review, sql_get_last_review

class FSMToken(StatesGroup):
    promik = State()

class avito(StatesGroup):
    delete_review = State()

class EnterData(StatesGroup):
    period = State()
    pf = State()

class seoboost(StatesGroup):
    link = State()

class review(StatesGroup):
    add_link = State()

def get_nick(param):
    value = get_setting(param)
    if value:
        if not value.startswith('@'):
            value = '@' + value
        return value
    else:
        return None

@dp.message_handler(commands="id")
async def cmd_id(message: types.Message):
    STR = get_string('str_your_id')
    await message.answer(STR.format(message.from_user.id))

@dp.message_handler(commands="delme")
async def cmd_delme(message: types.Message):
    user_id = message.from_user.id
    try:
        delete_user(id=user_id)
        STR = get_string('str_delete_user')
        await message.answer(STR.format(user_id))
    except:
        print(f"{colorama.Fore.RED}Error:{colorama.Fore.RESET}\n")

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
    await state.finish()
    data = call.data.split(':')
    text = data[1]

    if text == 'tasks':
        price = int(get_price('price_avito_pf'))
        formated_price = format_decimal(price)
        STR = get_string('str_tasks_text')
        await call.message.answer(STR.format(formated_price), reply_markup=get_menu_kb())
    elif text == 'qna':
        #await call.message.answer(qna_text, reply_markup=qna_kb())
        STR = get_string('str_qna_text')
        await call.message.answer(STR, reply_markup=qna_avito_kb())
    elif text == 'rules':
        STR = get_string('str_rules_text')
        await call.message.answer(STR, reply_markup=get_menu_kb())
    elif text == 'start':
        BTN = get_string('btn_video_guide')
        button = InlineKeyboardButton(
            text=BTN,
            callback_data="how_to"
        )
        keyboard = get_menu_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        STR = get_string('str_how_to_start_text')
        await call.message.answer(STR, reply_markup=keyboard)
    elif text == 'support':
        STR = get_string('str_support_text')
        support = get_nick('manager_nick')
        await call.message.answer(STR.format(support), reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="qna_avito", state='*')
async def user_call_qna_avito(call: CallbackQuery, state: FSMContext):
    all_qna = get_all_qna_avito()
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    for qna in all_qna:
        if qna['parametr'] == call.data:
            await call.message.answer(qna['value'], reply_markup=qna_avito_kb())

@dp.callback_query_handler(text_startswith="user:", state='*')
async def user(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    action = data[1]
    if action == 'profile':
        #await call.message.answer("Личный кабинет:", reply_markup=profile_kb())
        user = get_user(id=call.from_user.id)
        profile_string = get_string('str_user_profile')
        ref_link = f"{config.botlink}?start={call.from_user.id}"
        rferals_count = get_referals_count(user)
        f_balance = format_decimal(user['balance'])
        await call.message.answer(text=profile_string.format(f_balance, ref_link, rferals_count), disable_web_page_preview=True, reply_markup=profile_kb())
    elif action == 'promo':
        STR = get_string('str_input_promo')
        await call.message.answer(STR, reply_markup=menu_btn_kb())
        await FSMToken.promik.set()

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")


@dp.message_handler(state=FSMToken.promik)
async def promik(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text
    promocode = get_promocode(code=code)
    user = message.from_user
    await state.finish()
    if promocode:
        if promocode['isactivated'] == 0:
            activate_promocode(code)
            balance = get_balancik(message.from_user.id)
            balance = balance + int(promocode['price'])
            add_balance(balance, user_id)
            STR = get_string('str_promo_activated')
            f_price = format_decimal(promocode['price'])
            f_balance = format_decimal(balance)
            await message.answer(STR.format(f_price, f_balance), reply_markup=get_menu_kb())
            usr = get_user(id=user_id)
            str_user = await get_user_string_without_first_name(usr)
            MSG = get_string('str_msg_admin_promo')
            await send_admins(MSG.format(code, str_user, f_balance))

        elif promocode['isactivated'] == 1:
            STR = get_string('str_promo_inactive')
            await message.answer(STR, reply_markup=get_menu_kb())
        elif promocode['isactivated'] == 2:
            users_str = ""
            if not promocode['prom_users']:
                users_str = user_id
                update_promocode(increment=promocode['increment'], prom_users=users_str)
                balance = get_balancik(message.from_user.id)
                balance = balance + int(promocode['price'])
                add_balance(balance, user_id)
                STR = get_string('str_promo_activated')
                f_price = format_decimal(promocode['price'])
                f_balance = format_decimal(balance)
                await message.answer(STR.format(f_price, f_balance), reply_markup=get_menu_kb())
                usr = get_user(id=user_id)
                str_user = await get_user_string_without_first_name(usr)
                MSG = get_string('str_msg_admin_promo')
                await send_admins(MSG.format(code, str_user, f_balance))
            else:
                users_array = promocode['prom_users'].split(",")

                if str(user_id) not in users_array:
                    users_array.append(str(user_id))
                    users_str = ','.join(users_array)

                    update_promocode(increment=promocode['increment'], prom_users=users_str)
                    balance = get_balancik(message.from_user.id)
                    balance = balance + int(promocode['price'])
                    add_balance(balance, user_id)
                    STR = get_string('str_promo_activated')
                    f_price = format_decimal(promocode['price'])
                    f_balance = format_decimal(balance)
                    await message.answer(STR.format(f_price, f_balance), reply_markup=get_menu_kb())
                    usr = get_user(id=user_id)
                    str_user = await get_user_string_without_first_name(usr)
                    MSG = get_string('str_msg_admin_promo')
                    await send_admins(MSG.format(code, str_user, f_balance))
                else:
                    STR = get_string('str_promo_reactiv')
                    await message.answer(STR.format(code), reply_markup=get_menu_kb())
        else:
            print("Не успешно: значение найдено в таблице promocodes, но неизвестное состояние isactivated.")
    else:
        STR = get_string('str_promo_bad')
        await message.answer(STR, reply_markup=get_menu_kb())
        print("Не успешно: значение не найдено в таблице promocodes.")

@dp.callback_query_handler(text_startswith="profile:", state='*')
async def profile(call: CallbackQuery, state: FSMContext):
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
            orders = user_orders_all(call.from_user.id)
            orders_array = listord_array(orders)
            await state.update_data(orders=orders, array=orders_array)
            await call.message.answer(f"Страница 1 из {len(orders)}\n{orders_array[0]}", reply_markup=show_user_order_by_index(len(orders)-1, len(orders)))
        except:
            STR = get_string('str_error')
            await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))
    elif action == 'ordstatus':
        await state.set_state("check_order")
        STR = get_string('str_input_order_number')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="ordr:", state="*")
async def user_call_show_order_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message')

    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = listord_array(orders)

    try:
        index = int(call.data.split(":")[1])
        orders_array = state_data['array']
        await state.update_data(index=index, array=orders_array)
        await call.message.answer(f"Страница {index+1} из {len(orders)}\n{orders_array[index]}", reply_markup=show_user_order_by_index(index, len(orders)))
    except:
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsKWZiGSMCSvVs8Fxo5jM0pmfuxIMAA9M4AAL9VolLYmPxna-48Sk1BA')
        STR = get_string('str_error')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))

@dp.callback_query_handler(text_startswith="user_show_all:", state="*")
async def user_call_show_by_status(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message')
    action = call.data.split(':')[1]

    if action == 'completed':
        orders = []
        for order in user_orders_all(call.from_user.id):
            if order['status'] == 'Completed':
                orders.append(order)
    elif action == 'posted':
        orders = []
        for order in user_orders_all(call.from_user.id):
            if order['status'] == 'Posted':
                orders.append(order)
    try:
        orders_array = listord_array(orders)
        await state.update_data(orders=orders, array=orders_array)
        await call.message.answer(f"Страница 1 из {len(orders)}\n{orders_array[len(orders)-1]}", reply_markup=show_user_order_by_index(len(orders)-1, len(orders)))
    except:
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsKWZiGSMCSvVs8Fxo5jM0pmfuxIMAA9M4AAL9VolLYmPxna-48Sk1BA')
        STR = get_string('str_no_posted_orders')
        await call.message.answer(STR, reply_markup=user_back_kb('user:profile'))

@dp.callback_query_handler(text="user_show_all:orders", state="*")
async def user_call_show_all_orders(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    state_data = await state.get_data()
    orders = user_orders_all(call.from_user.id)
    if 'index' in state_data:
        index = state_data['index']
    else:
        index = len(orders) - 1
    if orders:
        orders_array = listord_array(orders)
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsRmZiHByCAAGHv2QnvB5WC0gOcM2S6QACdEIAAucOkEtX70Rr-qnYCDUE')
        for i in range(len(orders_array)):
            try:
                if i < len(orders_array) - 1:
                    await call.message.answer(orders_array[i])
                else:
                    await call.message.answer(orders_array[i], reply_markup=user_back_kb('profile:listord'))
            except RetryAfter as e:
                wait_time = e.timeout  # Время ожидания из исключения
                print(f"Flood control exceeded. Waiting for {wait_time} seconds.")
                await asyncio.sleep(wait_time)  # Ожидание перед повторной попыткой
                if i < len(orders_array) - 1:
                    await call.message.answer(orders_array[i])
                else:
                    await call.message.answer(orders_array[i], reply_markup=user_back_kb('profile:listord'))
    else:
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsTGZiHN5_OkQDOquJfFQslnkHwYavAAIwOQACTbCJS_QvdBkhGwOcNQQ')
        STR = get_string('str_error_get_orders')
        await call.message.answer(STR, reply_markup=user_back_kb(f'user:profile'))

@dp.callback_query_handler(text_startswith="repeat:", state="*")
async def call_repeat(call: types.CallbackQuery, state: FSMContext):
    index = call.data.split(":")[1]
    order = user_orders_all(call.from_user.id)[int(index)]
    links = order['links'].split('\n')
    async with state.proxy() as data:
        data['links'] = links
    image = f"images/avito_pf.jpg"
    STR = get_string('str_select_action')
    with open(image, 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=pf_kb())

@dp.callback_query_handler(text_startswith="tarifs:", state='*')
async def tarif(call: CallbackQuery, state: FSMContext):
    #await state.finish()
    async with state.proxy() as data:
        if 'links' not in data:
            await state.finish()
        else:
            links = data['links']
            await state.finish()
            data['links'] = links
    tarif = call.data.split(":")[1]
    if tarif == "pf":
        STR = get_string('srt_select_variant_pf')
        image = f"images/avito_pf.jpg"
        with open(image, 'rb') as photo:
            await call.message.answer_photo(photo=photo, caption=STR, reply_markup=pf_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")


@dp.callback_query_handler(text="yandex_pf", state='*')
async def yandex_pf(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")

@dp.callback_query_handler(text="review_bonus", state='*')
async def call_review_bonus(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🧑🏻‍💻 Данная функция в разработке")

@dp.callback_query_handler(text_startswith="pf:", state='*')
async def pf(call: CallbackQuery, state: FSMContext):
    call_data = call.data.split(":")
    if call_data[1].isdigit():
        days = call_data[1]
        days_str = get_days_suffix(days)
        await state.update_data(days=days)
        price = get_price('price_avito_pf')
        f_price = format_decimal(price)
        STR = get_string('str_pf_text')
        await call.message.answer(STR.format(days, days_str, f_price), reply_markup=pf_period_kb(days))
    elif call_data[1] =="enter-period":
        STR = get_string('str_enter_days')
        await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))
        await EnterData.period.set()
    elif call_data[1] =="enter-pf":
        STR = get_string('str_enter_pf')
        await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))
        await EnterData.pf.set()
    else:
        async with state.proxy() as data:
            #Количество дней
            days = call.data.split("-")[0].split(":")[1]
            days_str = get_days_suffix(days)
            #Количество ПФ
            data['days'] = days
            data['fix'] = call.data.split("-")[1]
            data['period'] = f"{days} {days_str}"
            #Стоимость
            data['count'] = get_price('price_avito_pf')
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * int(days))
        if 'links' not in data:
            STR = get_string('str_pf_links')
            await call.message.answer(STR, reply_markup=user_back_kb('tarifs:pf'), disable_web_page_preview=True)
        else:
            await place_order(call.message, state)
        await state.set_state("place_order")

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.message_handler(state=EnterData.period)
async def enter_period_func(message: types.Message, state: FSMContext):
    if message.text.isdigit() and int(message.text) >= 1:
        days = message.text
        days_str = get_days_suffix(days)
        price = get_price('price_avito_pf')
        STR = get_string('str_pf_text')
        f_price = format_decimal(price)
        await message.answer(STR.format(days, days_str, f_price), reply_markup=pf_period_kb(days))
        await state.update_data(days=days)
    else:
        STR = get_string('str_bad_number')
        await message.answer(STR, reply_markup=user_back_kb('tarifs:pf'))

@dp.message_handler(state=EnterData.pf)
async def enter_pf_func(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    days = state_data['days']
    if message.text.isdigit() and int(message.text) >= 5:
        async with state.proxy() as data:
            #Количество дней
            days_str = get_days_suffix(days)
            #Количество ПФ
            data['days'] = days
            data['fix'] = int(message.text)
            data['period'] = f"{days} {days_str}"
            #Стоимость
            data['count'] = get_price('price_avito_pf')
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * int(days))
        await state.set_state("place_order")
        STR = get_string('str_pf_links')
        await message.answer(STR, reply_markup=user_back_kb('user:tarif'))
    else:
        STR = get_string('str_bad_number')
        await message.answer(STR, reply_markup=user_back_kb('user:tarif'))

def extract_avito_links(text: str) -> list:
    """Извлекает уникальные ссылки avito.ru из произвольного текста.

    Обрабатывает:
    - текст со ссылками (не только сообщения, начинающиеся с http)
    - ссылки, разорванные переносом строки
    """
    # Склеиваем строки, которые выглядят как продолжение разорванной ссылки:
    # строка без пробелов, не начинается с http, идёт сразу после http-строки
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
async def place_order(message: Message, state: FSMContext):
    links = extract_avito_links(message.text)
    if links:
        async with state.proxy() as data:
            if 'links' not in data:
                data['links'] = links
            data['total_price'] *= len(data['links'])
        await state.set_state("order_checkout")
        STR = get_string('str_pf_contacts')
        msg = await message.answer(STR, reply_markup=yes_no_contact_kb())
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
        except:
            print("Error deleting message!")
    else:
        ERR = get_string('str_bad_link')
        await message.answer(ERR.format('avito.ru'))

@dp.callback_query_handler(text_startswith="contact:", state='*')
async def order_contact_set(call: CallbackQuery, state: FSMContext):
    answer = str2bool(call.data.split(":")[1])

    async with state.proxy() as data:
        data['contact'] = answer
    if 'total_price' in data:
        STR = get_string('str_debet_pf')
        f_price = format_decimal(int(data['total_price']))
        await call.message.answer(STR.format(f_price), reply_markup=yes_no_order_kb())
        await call.message.delete()
    else:
        STR = get_string('str_error')
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsKWZiGSMCSvVs8Fxo5jM0pmfuxIMAA9M4AAL9VolLYmPxna-48Sk1BA')
        await call.message.answer(STR, reply_markup=get_menu_kb())

@dp.callback_query_handler(text="order_confirm", state='*')
async def confirm_order(call: CallbackQuery, state: FSMContext):
    user = get_user(id=call.from_user.id)
    async with state.proxy() as data:
        if user['balance'] >= data['total_price']:
            update_user(id=user['id'], balance=user['balance']-data['total_price'])
            add_order(user_id=user['id'],
                      price=data['total_price'],
                      position_name=f"{data['days']}/{data['fix']}",
                      status="Posted",
                      links=str(data['links']),
                      contacts=data['contact'],
                      user_name=user['user_name'])
            ADM_MSG = get_string('str_new_order_text')
            order = get_users_last_order(user['id'])
            ord_id = order['increment']
            f_price = format_decimal(order['price'])
            user_str = await get_user_string_without_first_name(user)
            pos_name = order['position_name']
            status = order['status']
            if order['contacts']:
                con_str = 'Да'
            else:
                con_str = 'Нет'
            ord_date = order['date']
            links_cnt = len(order['links'])
            links_str = ""
            for link in order['links'].split(','):
                link = link.replace("'", "")
                links_str += f"\n<code>{link}</code>"
            ADM_MSG = ADM_MSG.format(ord_id, f_price, user_str, pos_name, status, con_str, ord_date, links_cnt, links_str)
            if len(ADM_MSG) < 4096:
                await send_admins(ADM_MSG)
            else:
                msg_arr = ADM_MSG.split('\n')
                for msg in split_messages(msg_arr, '\n'):
                    await send_admins(msg)

            USR_MSG = get_string('str_order_confirm').format(ord_id)
            await call.message.answer(USR_MSG, reply_markup=get_menu_kb())
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
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="menu", state='*')
async def to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.finish()
    STR = get_string('srt_select_variant_pf')
    await call.message.answer(STR, reply_markup=get_menu_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.message_handler(lambda message: message.text.isdigit(), state="check_order")
async def check_order(message: Message, state: FSMContext):
    await state.finish()
    order_id = int(message.text)
    try:
        order = get_order(order_id)
        if order['user_id'] == message.from_user.id:
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
    except:
        print("Error deleting message!")


@dp.message_handler(lambda message: message.text.isdigit(), state="refill_balance")
async def refill(message: Message, state: FSMContext):
    amount = int(message.text)
    min_amount = int(get_setting('min_amount'))
    if amount < min_amount:
        await state.finish()
        STR = get_string('str_more_money')
        f_min_amo = format_decimal(min_amount)
        msg = await message.answer(STR.format(f_min_amo), reply_markup=user_back_kb('user:profile'))
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        except:
            print("Error deleting message!")
    else:
        #await message.answer_sticker("CAACAgIAAxkBAAKsC2ZiFkw2x6LCIMANpdUYdwFmX6XnAAIuQQACL3WRSy5s2sn5ZuS8NQQ")
        STR = get_string('str_refil_balance')
        f_amount = format_decimal(amount)
        STR = STR.format(f_amount)
        msg = await message.answer(STR, reply_markup=yes_no_kb())
        async with state.proxy() as data:
            data['price'] = amount
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="refil:confirm", state="refill_balance")
async def refill_balance(call: CallbackQuery, state: FSMContext):
    from services.refill import (
        create_invoice as svc_create_invoice,
        finalize_with_referral_bonus,
    )
    from services.exceptions import PaymentError, UserNotFound

    await call.message.delete()
    async with state.proxy() as data:
        amount = data['price']
    user_id = call.from_user.id

    try:
        payment_url, payment_id = svc_create_invoice(user_id, int(amount))
    except PaymentError:
        support_nick = get_nick('manager_nick')
        msg = get_string('str_payment_error').format(support_nick)
        await bot.send_message(chat_id=user_id, text=msg, reply_markup=payment_error_kb())
        return

    STR1 = get_string('str_debet_money').format(format_decimal(amount))

    if user_id != 6988175544 and user_id != 257838190:
        await bot.send_message(
            chat_id=user_id, text=STR1,
            reply_markup=yookassa_kb(int(amount), payment_url),
        )
        success = await check_payment_status(payment_id)
    else:
        success = True

    if not success:
        STR6 = get_string('str_pay_error').format(get_nick('manager_nick'))
        await bot.send_message(chat_id=user_id, text=STR6)
        return

    try:
        result = finalize_with_referral_bonus(user_id, int(amount))
    except UserNotFound:
        await bot.send_message(chat_id=user_id, text=get_string('str_error'))
        return
    except Exception as ex:
        print(f'Error:\n{ex}')
        await bot.send_message(chat_id=user_id, text=get_string('str_error'))
        return

    usr = get_user(id=user_id)
    user_string = await get_user_string_without_first_name(usr)
    f_amount = format_decimal(amount)
    f_balance = format_decimal(result.user_balance)

    STR2 = get_string('str_usr_pay_success').format(f_amount, f_balance)
    await bot.send_message(chat_id=user_id, text=STR2, reply_markup=user_back_kb('user:profile'))
    STR3 = get_string('str_adm_pay_success').format(f_amount, user_string, f_balance)
    await send_admins(STR3)
    print(f"Юзер {usr['id']}: {usr['user_name']} пополнил баланс на {amount} руб.")

    if result.referrer_bonus > 0 and result.referrer_id is not None:
        ref_user = get_user(id=str(result.referrer_id))
        if ref_user:
            f_add_bal = format_decimal(result.referrer_bonus)
            f_new_bal = format_decimal(result.referrer_new_balance)
            STR4 = get_string('str_ref_balance_refil').format(f_add_bal, f_new_bal)
            await bot.send_message(chat_id=str(result.referrer_id), text=STR4)
            ref_user_str = ref_user.get('user_name') or ref_user['id']
            print(f"Юзер {ref_user_str} получил пополнение на {result.referrer_bonus} руб.")

###############################################################################################
#############################             ВИДОСИК              ################################
###############################################################################################

@dp.callback_query_handler(text="how_to", state='*')
async def call_how_to(call: CallbackQuery, state: FSMContext):
    """
    with open('images/IMG_2661.MP4', 'rb') as video:
        await call.message.answer_video(video, caption="Видео инструкция", reply_markup=get_menu_kb())
    """
    # Создаем объект InputMediaVideo
    with open('images/IMG_2661.MP4', 'rb') as video:
        video_obj = InputMediaVideo(media=video, caption="Видео инструкция")

        # Устанавливаем ширину и высоту видео
        video.width = 886
        video.height = 1612

        # Отправляем видео
        await call.message.answer_media_group(media=[video_obj])
        STR = get_string('str_select_action')
        await call.message.answer(STR, reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

###############################################################################################
#############################             ОТЗЫВЫ               ################################
###############################################################################################

@dp.callback_query_handler(text="reviews", state='*')
async def call_reviews_button(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    await state.finish()
    STR = get_string('str_review_start')
    with open('images/logo_small.jpg', 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=reviews_kb())

@dp.callback_query_handler(text_startswith="reviews:", state="*")
async def call_reviews_service(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message")
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
async def call_reviews_service(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print(f"Error deleting message\n")

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
    reviews_count = state_data['reviews_count']
    service = services[f"{state_data['service']}"]
    price = state_data['price']
    formated_price = format_decimal(int(price[reviews_count]))
    amount = format_decimal(int(state_data['amount']))
    STR = get_string('str_review_order_confirm')
    STR = STR.format(reviews_count, service, formated_price, amount)

    if state_data['service'] in message.text:
        await state.update_data(link=message.text)
        await message.answer(STR, reply_markup=yes_no_reviews())
    else:
        STR1 = get_string('str_review_bad_link')
        await message.answer(STR1)

@dp.callback_query_handler(text="rev_confirm", state='*')
async def call_confirm_review(call: CallbackQuery, state: FSMContext):
    user = get_user(id=call.from_user.id)
    state_data = await state.get_data()
    amount = state_data['amount']
    service = state_data['service']
    link = state_data['link']
    if user['balance'] >= int(amount):
        update_user(id=user['id'], balance=user['balance']-int(amount))
        #add_order_reviews(user_id=user['id'], price=amount, service=service, status="Размещен")
        await sql_add_review(str(call.from_user.id), int(amount), service,link, 'Posted')
        #await send_admins(new_order_review_text(get_users_last_order_reviews(user['id'])))
        order = await sql_get_last_review(str(call.from_user.id))
        #await send_admins(new_order_review_text(order))
        manager = get_nick('nick_manager_reviews')
        STR = get_string('str_review_confirm').format(order['id'], manager)
        MSG = get_string('str_new_review_admin_report')
        famount = format_decimal(amount)
        user_str = await get_user_string_without_first_name(user)
        MSG = MSG.format(order['id'], famount, user_str, services[service], order['status'], order['date'], order['link'])
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
    except:
        print("Error deleting message!")

###############################################################################################
########################     Удаление негативного отзыва Авито    #############################
###############################################################################################

@dp.callback_query_handler(text="avito_del_review", state='*')
async def call_avito_del_review(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    STR = get_string('str_delete_review')
    price = get_price('price_avito_del_review')
    f_price = format_decimal(price)
    STR = STR.format(f_price)
    await call.message.answer(STR)
    await avito.delete_review.set()

@dp.message_handler(text_startswith="https:", state=avito.delete_review)
async def avito_del_review(message: types.Message, state: FSMContext):
    link = message.text
    user = get_user(id=message.from_user.id)
    #amount = 7000
    amount = int(get_price('price_avito_del_review'))
    service = 'avito'
    if user['balance'] >= amount:
        update_user(id=user['id'], balance=user['balance']-int(amount))
        add_order_delreview(user['id'], amount, service, link, 'Размещен')
        order = get_users_last_order_delreviews(str(message.from_user.id))
        #await send_admins(new_order_review_text(order))
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
        f_ref = format_decimal(int(amount) - int(user_balance))
        BTN = get_string('btn_refill_balance')
        button = InlineKeyboardButton(
            text=BTN,
            callback_data="profile:ref_bal"
        )
        keyboard = menu_btn_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        await call.message.answer(STR.format(balance, f_amount, f_ref), reply_markup=keyboard)

###############################################################################################
#############################           SEO BOOST              ################################
###############################################################################################

@dp.callback_query_handler(text="seo_boost", state='*')
async def call_seo_boost(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    MSG = get_string('str_seo_main')
    await call.message.answer(MSG, reply_markup=seo_boost_kb())

@dp.callback_query_handler(text="seo_howto", state='*')
async def call_seo_howto(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    MSG = get_string('str_seo_howto')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))

@dp.callback_query_handler(text="seo_why", state='*')
async def call_seo_why(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    MSG = get_string('str_seo_why')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))

@dp.callback_query_handler(text="seo_result", state='*')
async def call_seo_result(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    MSG = get_string('str_seo_result')
    await call.message.answer(MSG, reply_markup=user_back_kb('seo_boost'))

@dp.callback_query_handler(text="seo_order", state='*')
async def call_seo_order(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
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
    price = int(get_setting('seo_price'))
    link = message.text
    total_price = price * months_count
    MSG = get_string('str_seo_order')
    await state.update_data(total_price=total_price)
    await state.update_data(link=link)
    f_price = format_decimal(int(total_price))
    MSG = MSG.format(months_count, months_suffix, link, f_price)
    await message.answer(MSG, reply_markup=seo_order_confirm(total_price))

@dp.callback_query_handler(text_startswith="seo_yes:", state='*')
async def user_call_seo_yes(call: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    months_count = int(state_data['months'])
    total_price = state_data['total_price']
    link = state_data['link']
    user = get_user(id=call.from_user.id)
    manager = get_nick('manager_nick')
    if user['balance'] >= total_price:
        update_user(id=user['id'], balance=user['balance']-total_price)
        add_order_seo(user_id=user['id'], price=total_price, months=months_count, status="Размещён",
        link=str(link).replace(']','').replace('[',''))
        adm_message = get_string('str_seo_admin_msg')
        o = get_user_last_order_seo(call.from_user.id)
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
    except:
        print("Error deleting message!")
