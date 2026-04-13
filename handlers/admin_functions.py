import colorama
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, ContentType, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.markdown import hlink
from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BotBlocked
from keyboards.inline_keyboards import months_names
import matplotlib.pyplot as plt
import io

import asyncio
import string
import math
import time
from datetime import timedelta, datetime

from utils.sqlite3 import *

import random

from data import config
from data.config import *
from data.loader import dp, bot
from design import *
from keyboards.inline_keyboards import *
from utils.other import *
from utils.sender import *
from utils.msql import *
from utils.googlesheets import create_sheet, create_orders_report, create_refills_report, create_reviews_report
#from utils.sqlite3 import get_user, add_refill, user_orders_all, add_order, get_order, update_user, get_users_last_order, delete_user, all_users, delete_order, get_refill, all_orders

class Admin(StatesGroup):
    del_promik = State()
    new_promik = State()
    new_promik_price = State()
    del_user = State()
    user_info = State()

class balance(StatesGroup):
    select_user = State()
    change_balance = State()

class hammster(StatesGroup):
    set_login = State()

class vip(StatesGroup):
    set_status = State()
    unset_status = State()

class Spam(StatesGroup):
    SpamShow = State()
    SpamSend = State()

class admin_message(StatesGroup):
    send = State()

class coder_message(StatesGroup):
    send = State()

class Order(StatesGroup):
    order = State()
    delete = State()
    user = State()

class Order1(StatesGroup):
    order = State()

class magic(StatesGroup):
    user = State()

class refills(StatesGroup):
    user = State()

class reviews(StatesGroup):
    user = State()
    close = State()

class del_reviews(StatesGroup):
    user = State()
    close = State()

class setup_class(StatesGroup):
    str_variable_view = State()
    str_variable_add = State()
    variable_view = State()
    variable_add = State()
    button_view = State()
    button_add = State()
    string_edit = State()
    btn_edit = State()
    price_edit = State()
    min_amount = State()
    set_admin = State()
    spam_exclude = State()
    report_exclude = State()

class ProgressStates(StatesGroup):
    progress = State()

list_content_types = ['text', 'photo']


spam_send_stickers = ['CAACAgIAAxkBAAKkwmZiBWDI9edrau5mxOWyZVdKku86AAK6PAACn8eQS1pXdxbNkN0GNQQ', 'CAACAgIAAxkBAAKkyWZiBjXiq-xMlCblUMTRPEE8l9gMAAKEOwACqg-ASB2g--fr7MgZNQQ']
spam_ok_stickers = ['CAACAgIAAxkBAAKkxGZiBbbOh3b7DO0AAQko2z_Ea--_fgACrz0AAus-MUmBZQXoeh94iTUE', 'CAACAgIAAxkBAAKky2ZiBqaVIwreVHo-mMSW1aMa_yefAAI4QwAC-GaQS2IRSUEqOCBxNQQ']
spam_no_stickers = ['CAACAgIAAxkBAAKkzWZiB2S2CnhpW7OwVogkxgXiaDvNAAIDPQACen2QSwnVTmP8lTDXNQQ', 'CAACAgIAAxkBAAKkz2ZiB3WcO3970Sz0PvC-QmSa5oBlAAIwOQACTbCJS_QvdBkhGwOcNQQ']

def generate_random_string(length):
    characters = string.ascii_letters + string.digits  # буквы и цифры
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
                print(f"{user_not_in_base.format(param)}\n{e}")
        else:
            try:
                user = get_user(user_name=param[1:])
            except Exception as e:
                print(f"{user_not_in_base.format(param)}\n{e}")
    return user

@dp.message_handler(commands=['admin'], state='*')
async def adminka(message: Message, state: FSMContext):
    await state.finish()
    if str(message.from_user.id) in get_admins():
        await bot.send_message(chat_id=message.from_user.id, text="👋 Добро пожаловать в админ панель!", reply_markup=admin())

@dp.message_handler(commands="delete")
async def cmd_del_order(message: types.Message):
    order_id = message.text[8:]
    userok = message.from_user.id
    admins = get_admins()
    if userok in admins:
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
    await state.finish()
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text="👋 Добро пожаловать в админ панель!", reply_markup=admin())
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text="users_man", state='*')
async def profile(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
    user_id = call.from_user.id
    await call.message.answer("🐹 Управление пользователями:", reply_markup=users_man_kb())
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text="promo_codes", state='*')
async def promo_codes(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text="⚙️ Управление промокодами:", reply_markup=promo_codes_kb())

    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text="add_promo", state="*")
async def add_promik(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    if 'page' in state_data:
        page = state_data['page']
    else:
        page = 'promo_codes'

    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    code = generate_random_string(8)
    add_promocode(code, 2000)
    await call.message.answer(f"✅ Успешно! Промокод - <code>{code}</code>", reply_markup=admin_back_kb(page))

@dp.callback_query_handler(text="show_promo", state="*")
async def call_show_promik(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    if 'page' in state_data:
        page = state_data['page']
    else:
        page = 'promo_codes'

    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    user_id = call.from_user.id
    prm = "Найдены промокоды:\n"
    all_promo = all_promocodes()
    prm = '\n'.join(['❎' if promo['isactivated'] == 1 else '✅' + f"<code>{promo['code']}</code> цена: {promo['price']} руб." for promo in all_promo])
    await call.message.answer(prm, reply_markup=admin_back_kb(page))

@dp.callback_query_handler(text="deactiv_promo")
async def del_promik(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer("⚙️ Введите промокод!")
    await Admin.del_promik.set()

@dp.message_handler(state=Admin.del_promik)
async def del_prom(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    if 'page' in state_data:
        page = state_data['page']
    else:
        page = 'promo_codes'

    code = message.text
    del_promo(code)
    await message.answer("✅ Промокод успешно удалён!", reply_markup=admin_back_kb(page))
    await state.finish()

@dp.callback_query_handler(text="del_activated_promo", state="*")
async def call_del_act_promo(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    if 'page' in state_data:
        page = state_data['page']
    else:
        page = 'promo_codes'
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    all_promo = all_promocodes()
    for code in all_promo:
        if code['isactivated'] == 1:
            del_promo(code['code'])

    all_promo = all_promocodes()
    await call.message.answer("✅Активированные промокоды удалены!")
    prm = '\n'.join(['❎' if promo['isactivated'] == 1 else '✅' + f"<code>{promo['code']}</code> цена: {promo['price']} руб." for promo in all_promo])
    await call.message.answer(prm, reply_markup=admin_back_kb(page))

@dp.callback_query_handler(text="add_custom_promo")
async def call_add_custom_promo(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    await call.message.answer("🔮Введите новый промокод:")
    await state.update_data(call=call)
    await Admin.new_promik.set()

@dp.message_handler(state=Admin.new_promik)
async def add_custom_promo(message: types.Message, state: FSMContext):
    code = message.text
    promocode = get_promocode(code=code)
    if not promocode:
        await state.update_data(new_prom=code)
        await message.answer(f"🔮Вы собираетесь добавить промокод <code>{code}</code>, укажите его стоимость:")
        await Admin.new_promik_price.set()
    else:
        call_data = await state.get_data()
        call = call_data['call']
        await call_add_custom_promo(call, state)


@dp.message_handler(state=Admin.new_promik_price)
async def add_custom_promo_price(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    if 'page' in state_data:
        page = state_data['page']
    else:
        page = 'promo_codes'

    if message.text.isdigit():
        price = int(message.text)
    else:
        await message.answer("❎Некорректная стоимость промокода!")
        await Admin.new_promik.set()
    promocode_data = await state.get_data()
    code = promocode_data['new_prom']
    if add_promocode(code, int(price)):
        await message.answer(f"✅Успешно добавлен промокод <code>{code}</code>, стоимостью <b>{price} руб.</b>", reply_markup=admin_back_kb(page))
        promocode = get_promocode(code=code)
        update_promocode(increment=promocode['increment'], isactivated=2)
    else:
        await message.answer("❎Ошибка добавления промокода!", reply_markup=admin_back_kb(page))
    await state.finish()

@dp.callback_query_handler(text="users_ids")
async def call_users_ids(call: types.CallbackQuery):
    user_id = call.from_user.id
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    ids = all_users()
    with open("ids.txt", "w") as file:
        for id in ids:
            file.write(str(id['id']) + "\n")

    file_path = "ids.txt"
    with open(file_path, 'rb') as file:
        await bot.send_document(user_id, document=InputFile(file), reply_markup=admin_back_kb('users_man'))

@dp.callback_query_handler(text="users_len")
async def call_users_len(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    usr_cnt = len(all_users())
    await call.message.answer(f"🤖 в базе зарегистрировано {usr_cnt} 🐹 пользователей", reply_markup=admin_back_kb('users_man'))

@dp.callback_query_handler(text="del_user")
async def del_user(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя 🐹 для удаления!")
    await Admin.del_user.set()
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.message_handler(state=Admin.del_user)
async def del_usr(message: types.Message, state: FSMContext):
    delUser = await find_user(message.text)
    #usr_str = await get_user_string(delUser['id'])
    usr_str = await get_user_string_without_first_name(delUser)
    try:
        delete_user(delUser['id'])
        await message.answer(f"✅ Пользователь {usr_str} успешно удален!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        print(e)
        await message.answer(f"❎ Ошибка удаления пользователя!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()

@dp.callback_query_handler(text="user_balance")
async def usr_balance(call: types.CallbackQuery):
    await call.message.answer("⚙️ Введите ID или логин пользователя 🐹 баланс, которого надо изменить:")
    await balance.select_user.set()
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.message_handler(state=balance.select_user)
async def usr_sel(message: types.Message, state: FSMContext):
    #usr = get_user(id=message.text)
    usr = await find_user(message.text)
    try:
        #usr_str = await get_user_string(usr['id'])
        usr_str = await get_user_string_without_first_name(usr)
        await message.answer(f"Выбран\n🐹 Пользователь {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>")
        await state.update_data(usr=usr)
        await balance.change_balance.set()
        await message.answer("💳 Введите новый баланс:")
    except Exception as e:
        print(e)
        await message.answer(f"⚠️ Ошибка!:\n{e}")
        await state.finish()

@dp.message_handler(state=balance.change_balance)
async def change_balance(message: types.Message, state: FSMContext):
    new_balance = message.text
    state_data = await state.get_data()
    ch_usr = state_data['usr']
    adm_user = get_user(id=message.from_user.id)
    #usr_str = await get_user_string(ch_usr['id'])
    usr_str = await get_user_string_without_first_name(ch_usr)
    try:
        await message.answer(f"Пользователю {usr_str} установлен баланс <b>{new_balance}руб.</b>", reply_markup=admin_back_kb('users_man'))
        update_user(id=ch_usr['id'], balance=new_balance)
        await bot.send_message(chat_id=ch_usr['id'], text=f"<b>🤖 Пользователь @{adm_user['user_name']} установил Ваш 💳 баланс на {new_balance}руб.</b>")
        await state.finish()
    except Exception as e:
        print(e)
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()

@dp.callback_query_handler(text="set_vip")
async def set_vip(call: types.CallbackQuery):
    user_id = call.from_user.id
    await call.message.answer("⚙️ Введите ID или логин пользователя:")
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await vip.set_status.set()

@dp.message_handler(state=vip.set_status)
async def vip_set(message: types.Message, state: FSMContext):
    try:
        usr = await find_user(message.text)
        adm_usr = get_user(id=message.from_user.id)
        #usr_str = await get_user_string(usr['id'])
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 1:
            update_user(id=usr['id'], is_vip=1)
            await message.answer(f"🐹 Пользователь {usr_str} получил 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            await bot.send_message(chat_id=usr['id'], text=f"🤖 Пользователь @{adm_usr['user_name']} установил Вам 💎VIP-статус!")
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
        print('Error deleting message!')
    await vip.unset_status.set()

@dp.message_handler(state=vip.unset_status)
async def vip_unset(message: types.Message, state: FSMContext):
    try:
        #usr = get_user(id=message.text)
        usr = await find_user(message.text)
        adm_usr = get_user(id=message.from_user.id)
        #usr_str = await get_user_string(usr['id'])
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 0:
            update_user(id=usr['id'], is_vip=0)
            await message.answer(f"🐹 Пользователь {usr_str} потерял 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            await bot.send_message(chat_id=usr['id'], text=f"🤖 Пользователь @{adm_usr['user_name']} отменил Вам 💎VIP-статус!")
        else:
            await message.answer(f"🐹 Пользователь {usr_str} не имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()

@dp.callback_query_handler(text="send_spam", state="*")
async def send_spam(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text=f"🔔 Ввыедите сообщение для рассылки:")
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await Spam.SpamShow.set()

@dp.message_handler(content_types=list_content_types, state = Spam.SpamShow)
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
            if user['id'] not in admins and user['is_vip'] != 1:
                try:
                    await bot.send_message(user['id'], text=text)
                    sended += 1
                except:
                    print(f"Error sending message to {user['id']}")
                    not_sended += 1
            else:
                not_sended += 1
    elif content_type == "photo":
        photo_id = state_data['photo_id']
        caption = state_data['caption']
        start_time = time.monotonic()
        for user in users:
            if user['id'] not in admins and user['is_vip'] != 1:
                try:
                    await bot.send_photo(chat_id=user['id'], photo=photo_id, caption=caption)
                    sended += 1
                except:
                    print(f"Error sending message to {user['id']}")
                    not_sended += 1
            else:
                not_sended += 1
    end_time = time.monotonic()
    sec = await conv_delta(timedelta(seconds=end_time - start_time))
    for admin in admins:
        try:
            random_sticker = random.choice(spam_ok_stickers)
            await bot.send_sticker(chat_id=admin, sticker=random_sticker)
            await bot.send_message(chat_id=admin, text=f"⚠️Рассылка сообщений завершена!\nПользователей в базе <b>{total_users}</b> из них <b>{sended}</b> доставлено, <b>{not_sended}</b> не доставлено, время рассылки <b>{sec}</b>", reply_markup=admin_back_kb('messages_menu'))
        except Exception as e:
            print(f"Error sending a message to the administrator with ID {admin}\n{e}")
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
        #await call.message.answer_sticker(random_sticker)
        await call.message.answer("⚠️ Рассылка сообщений началась.", reply_markup=admin_back_kb('messages_menu'))
    else:
        random_sticker = random.choice(spam_no_stickers)
        #await call.message.answer_sticker(random_sticker)
        await state.finish()
        await call.message.answer("⚠️ Рассылка сообщений отменена.", reply_markup=admin_back_kb('messages_menu'))

@dp.callback_query_handler(text="messages_menu")
async def messages_menu(call: types.CallbackQuery):
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text="🤖 Кому отправим сообщение:", reply_markup=messages_kb())
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text="admin_send")
async def input_admin_message(call: types.CallbackQuery):
    await call.message.answer("🤖 Функция для кодера. Введите сообщение для отправки админу:")
    await admin_message.send.set()

    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.message_handler(state=admin_message.send)
async def send_admin_message(message: types.Message, state: FSMContext):
    admins = get_admins()
    for admin in admins:
        if admin != message.from_user.id:
            await bot.send_message(chat_id=admin, text=message.text, disable_web_page_preview=True)
        else:
            await bot.send_message(chat_id=admin, text="Сообщение отправлено!", disable_web_page_preview=True)
    await state.finish()

@dp.callback_query_handler(text="coder_send")
async def input_coder_message(call: types.CallbackQuery):
    await call.message.answer("🤖 Функция для админа. Введите сообщение для отправки кодеру:")
    await coder_message.send.set()
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.message_handler(state=coder_message.send)
async def send_coder_message(message: types.Message, state: FSMContext):
    CODER = config.CODER
    await bot.send_message(chat_id=CODER, text=message.text, disable_web_page_preview=True)
    await state.finish()

###############################################################################################
#############################          Заказы Авито ПФ         ################################
###############################################################################################

@dp.callback_query_handler(text="orders_man", state='*')
async def orders_man(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
    user_id = call.from_user.id
    orders = all_orders()
    orders_cnt = len(orders)
    ord_dec = decline_order(orders_cnt)
    total_payed = 0
    completed_cnt = 0
    posted_cnt = 0
    for order in orders:
        total_payed += int(order['price'])
        if order['status'] == 'Completed':
            completed_cnt += 1
        else:
            posted_cnt += 1
    f_payed = format_decimal(total_payed)
    #await call.message.answer_sticker('CAACAgIAAxkBAAKsRmZiHByCAAGHv2QnvB5WC0gOcM2S6QACdEIAAucOkEtX70Rr-qnYCDUE')
    STR = f"♾️ Всего <b>{orders_cnt} {ord_dec}</b>\n✅ Выполнено: {completed_cnt}\n✍🏻 Не выполнено {posted_cnt}\nВсего заработано <b>{f_payed} ₽</b>\n⚙️ Управление заказами:"
    await call.message.answer(STR, reply_markup=orders_kb())

    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text="search_order")
async def search_order(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("⚙️ Введите ID заказа:")
    await Order.order.set()

@dp.callback_query_handler(text="del_order")
async def select_order_del(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("⚙️ Введите ID заказа:")
    await Order.delete.set()

@dp.message_handler(state=Order.delete)
async def del_order(message: types.Message, state: FSMContext):
    order_id = message.text
    order = get_order(id=order_id)
    delete_order(id=order_id)
    try:
        await message.answer(text=f"⚠️ Заказ <b>{order_id}:</b>\n{order_text(order)}\nУспешно удален!")
    except Exception as e:
        await message.answer(text=f"⚠️ Заказ <b>{order_id}</b> не найден!\n{e}")
    await state.finish()

@dp.callback_query_handler(text="user_all_orders", state="*")
async def call_user_all_orders(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    if 'old_user' not in state_data:
        await call.message.answer("⚙️ Введите ID или логин пользователя:")
        await Order.user.set()
    else:
        await admin_show_user_all_orders(call.message, state)

@dp.message_handler(state=Order.user)
async def admin_show_user_all_orders(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    if 'old_user' not in state_data:
        usr = await find_user(message.text)
    else:
        usr = state_data['old_user']
    try:
        if usr:
            orders = user_orders_all(usr['id'])
            orders_array = listord_array(orders)
            await state.update_data(orders=orders, array=orders_array)
            if 'report_type' not in state_data:
                if 'page' in state_data:
                    page = state_data['page']
                else:
                    page = 'orders_man'
            else:
                page = 'to_general_user_report'
            await message.answer(f"Страница 1 из {len(orders)}\n{orders_array[0]}", reply_markup=show_admin_order_by_index(0, len(orders), page))
        else:
            await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('orders_man'))
            await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()

@dp.callback_query_handler(text_startswith="order:", state="*")
async def admin_call_show_order_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        pass
    index = int(call.data.split(":")[1])
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    if 'report_type' not in state_data:
        if 'page' in state_data:
            page = state_data['page']
        else:
            page = 'orders_man'
    else:
        page = 'to_general_user_report'
    await call.message.answer(f"Страница {index+1} из {len(orders)}\n{orders_array[index]}", reply_markup=show_admin_order_by_index(index, len(orders), page))

@dp.callback_query_handler(text="admin_show_all_orders", state="*")
async def admin_call_show_all_orders(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    if orders:
        orders_array = listord_array(orders)
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsRmZiHByCAAGHv2QnvB5WC0gOcM2S6QACdEIAAucOkEtX70Rr-qnYCDUE')
        for order in orders_array:
            await call.message.answer(order)
        await call.message.answer("Выберите действие:", reply_markup=admin_back_kb('orders_man'))
    else:
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsTGZiHN5_OkQDOquJfFQslnkHwYavAAIwOQACTbCJS_QvdBkhGwOcNQQ')
        await call.message.answer("⚠️ Ошибка получения заказов пользователя!", reply_markup=admin_back_kb('orders_man'))

@dp.message_handler(state=Order.order)
async def order_work_start(message: types.Message, state: FSMContext):
    order = get_order(id=message.text)
    STR = get_string('str_order_text')
    inc = order['increment']
    price = format_decimal(order['price'])
    user = get_user(id=order['user_id'])
    user_str = await get_user_string_without_first_name(user)
    pos = order['position_name'].split('/')
    days_suff = get_days_suffix(pos[0])
    pos_name = f"{pos[0]} {days_suff} / {pos[1]} ПФ"
    if order['status'] == 'Posted':
        status = 'Размещён'
    elif order['status'] == 'Completed':
        status = 'Выполнен'
    else:
        status = 'В работе'
    if order['contacts']:
        cont = '✅Да'
    else:
        cont = '❎Нет'
    dat = order['date']
    links =''
    links_cnt = 0
    for link in order['links'].split():
        links += f"<code>{link}</code>\n"
        links_cnt += 1
    STR = STR.format(inc, price, user_str, pos_name, status, cont, dat, links_cnt, links)
    await message.answer(STR, reply_markup=admin_back_kb(None))
    await state.finish()

@dp.callback_query_handler(text="gotovoebat")
async def order_input_id(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await bot.send_message(chat_id=call.from_user.id, text=f"⚙️ Введите ID заказа:")
    await Order1.order.set()

@dp.message_handler(state=Order1.order)
async def order_finish(message: types.Message, state: FSMContext):
    order = message.text
    edit_order(status="Completed", order=order)
    order1 = get_order(order)
    id = order1['user_id']
    info = get_user(id=id)
    await bot.send_message(chat_id=id, text=f"✅ Ваш заказ №{order} выполнен.")
    await bot.send_message(chat_id=message.from_user.id, text="✅ Успешно")
    await state.finish()

@dp.callback_query_handler(text="gsheets")
async def gsheets(call: types.CallbackQuery, state: FSMContext):
    #await call.message.answer_sticker("CAACAgIAAxkBAAKsC2ZiFkw2x6LCIMANpdUYdwFmX6XnAAIuQQACL3WRSy5s2sn5ZuS8NQQ")
    #await call.message.answer(sheet_complete, reply_markup=gsheets_url(create_sheet()))
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    STICKER = get_setting('wait_sticker')
    msg = await call.message.answer("⏳ Идет генерация отчета.")
    stick = await call.message.answer_sticker(STICKER)
    await call.message.answer(sheet_complete, reply_markup=gsheets_url(create_sheet()))
    try:
        await bot.delete_message(chat_id=call.message.chat.id, message_id=msg.message_id)
        await bot.delete_message(chat_id=call.message.chat.id, message_id=stick.message_id)
    except:
        pass

@dp.callback_query_handler(text_startswith="orders_", state="*")
async def admin_call_orders_by_status(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    orders = all_orders()
    action = call.data.split('_')[1]
    orders_cnt = 0
    if action == "completed":
        sort_orders = all_orders_by_status('Completed')
    elif action == "posted":
        sort_orders = all_orders_by_status('Posted')
    orders_array = listord_array(sort_orders)
    cnt = len(orders_array)
    await state.update_data(orders=sort_orders, array = orders_array)
    await call.message.answer(f"Страница {cnt} из {len(orders_array)}\n{orders_array[cnt-1]}",
        reply_markup=show_admin_order_by_index(cnt - 1, cnt, page='orders_man', all_orders=False))

@dp.callback_query_handler(text="magic", state="*")
async def magic_menu(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🔮 волшебное меню", reply_markup=magic_kb())
    await state.update_data(page=call.data)
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

@dp.callback_query_handler(text_startswith="magic:", state="*")
async def magic_start(call: types.CallbackQuery, state: FSMContext):
    param = call.data.split(':')[1]
    state_data = await state.get_data()
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    if param == "generate":
        await call.message.answer(magic_ref)
        await state.update_data(magic_command=param)
        await magic.user.set()
    elif param == "report":
        await call.message.answer(magic_report)
        if 'report' in state_data:
            if 'show_referals' in state_data:
                show_referals = state_data['show_referals']
            else:
                show_referals = False
            if 'show_orders' in state_data:
                show_orders = state_data['show_orders']
            else:
                show_orders = False
            if 'show_refills' in state_data:
                show_refills = state_data['show_refills']
            else:
                show_refills = False
            if 'page' in state_data:
                page = state_data['page']
            else:
                page = 'magic'
            await call.message.answer(state_data['report']['general'], reply_markup=magic_general_kb(page, show_referals, show_orders, show_refills))
        else:
            await state.update_data(magic_command=param)
            await magic.user.set()
    elif param == "referals":
        if 'show_orders' in state_data:
            show_orders = state_data['show_orders']
        else:
            show_orders = False
        if 'show_refills' in state_data:
            show_refills = state_data['show_refills']
        else:
            show_refills = False
        if 'report_type' not in state_data:
            if 'page' in state_data:
                page = state_data['page']
            else:
                page = 'magic'
        else:
            page = 'to_general_user_report'
        #await call.message.answer(state_data['report']['referals'], reply_markup=magic_referals_kb(page, show_orders, show_refills))
        if len(state_data['report']['referals']) < 4096:
            await call.message.answer(state_data['report']['referals'], reply_markup=magic_referals_kb(page, show_orders, show_refills))
        else:
            MSG = state_data['report']['referals'].split(",")
            MSG_PARTS = split_messages(MSG, ",")
            for i in range (len(MSG_PARTS)):
                if i == len(MSG_PARTS) - 1:
                    await call.message.answer(MSG_PARTS[i], reply_markup=magic_referals_kb(page, show_orders, show_refills))
                else:
                    await call.message.answer(MSG_PARTS[i])
        await magic.user.set()
    else:
        await state.update_data(magic_command=param)
        if 'old_user' not in state_data:
            await call.message.answer(magic_report)
            await magic.user.set()
        else:
            await magic_gen(call.message, state)

@dp.callback_query_handler(text="to_general_user_report", state="*")
async def call_to_general_user_report(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message!\n{e}")

    state_data = await state.get_data()
    if 'report' in state_data:
        if 'show_referals' in state_data:
            show_referals = state_data['show_referals']
        else:
            show_referals = False
        if 'show_orders' in state_data:
            show_orders = state_data['show_orders']
        else:
            show_orders = False
        if 'show_refills' in state_data:
            show_refills = state_data['show_refills']
        else:
            show_refills = False
        if 'page' in state_data:
            page = state_data['page']
        else:
            page = 'users_man'
        if 'general' in state_data['report']:
            await call.message.answer(state_data['report']['general'], reply_markup=magic_general_kb(page, show_referals, show_orders, show_refills))
        else:
            if 'old_user' in state_data:
                user = state_data['old_user']
                report = await gen_magic_report(user['id'])
                await state.update_data(report=report, old_user=user, show_referals=report['show_referals'], show_orders=report['show_orders'], show_refills=report['show_refills'], report_type='general')
                await call.message.answer(report['general'], reply_markup=magic_general_kb(page, report['show_referals'], report['show_orders'], report['show_refills']))


async def generate_link(user_id):
    user = get_user(id=user_id)
    if user:
        if user['magic'] is None:
            magic = generate_random_string(10)
            update_user(id=user_id, magic=magic, is_vip=1)
            link = f"{config.botlink}?start={magic}"
            name = await get_user_string_with_first_name(user)
            STR = f"{magic_gen_str.format(name, link)}"
            return STR
        else:
            magic = user['magic']
            link = f"{config.botlink}?start={magic}"
            name = await get_user_string_with_first_name(user)
            STR = f"{magic_gen_str.format(name, link)}"
            return STR
    else:
        return None

async def gen_magic_report(user_id):
    report = {}

    user = get_user(id=user_id)
    name = await get_user_string_with_first_name(user)

    if user:
        report['general'] = f"📖 Отчет по пользователю\nID {name}\nЗарегистрирован: <b>{user['reg_date']}</b>\nБаланс <b>{user['balance']} руб.</b>"

        if user['ref_id']:
            refer = get_user(id=user['ref_id'])
            if refer:
                report['general'] += f"\nРефер: {refer['id']}: <b>{refer['first_name']} (@{refer['user_name']})</b>"

        if user['is_vip'] is not None:
            report['general'] += f"\n💎VIP: ✅"
        else:
            report['general'] += f"\n💎VIP: ❎"

        orders = all_orders()
        total_user_orders = 0
        for order in orders:
            if int(order['user_id']) == int(user_id):
                total_user_orders += 1
        report['general'] += f"\n📖 Оставил <b>{total_user_orders}</b> заказов\n"

        reviews = all_orders_reviews()
        reviews_paid = 0
        total_user_reviews = 0
        for order in reviews:
            if int(order['user_id']) == int(user_id):
                total_user_reviews += 1
                reviews_paid += int(order['price'])
        report['general'] += f"\n📖 Отзывы: <b>{total_user_reviews}</b> заказов ({reviews_paid} руб.)\n"

        delreviews = user_orders_all_delreviews(user_id)

        del_reviews_cnt = 0
        del_reviews_paid = 0

        if delreviews:
            for order in delreviews:
                if order['service'] == 'avito':
                    del_reviews_cnt += 1
                    del_reviews_paid += int(order['price'])

        report['general'] += f"\n📖 Удаление отзыва с авито: <b>{del_reviews_cnt} ({del_reviews_paid} руб.)</b> заказов"

        users = all_users()
        referals_count = 0
        referals_str = ""
        referals_array = []
        referals_list_str = []

        if user['referals']:
            referals_array = user['referals'].split(',')
            referals_count = len(referals_array)
            for ref_id in referals_array:
                ref_user = get_user(id=ref_id)
                ref_str_add = await get_user_string_without_first_name(ref_user)
                referals_list_str.append(ref_str_add)
                referals_str = ', '.join(referals_list_str)


        report['referals'] = f"\n🐹 рефералы: <b>{referals_count}</b>\n{referals_str}"

        simply_ref_link = f"{config.botlink}?start={user_id}"
        if referals_count != 0:
            report['general'] += f"\n🐹 рефералы: <b>{referals_count}</b>"
        report['general'] += f"\nРеферальная ссылка:\n🔗{simply_ref_link}"

        if user['magic']:
            link = f"{config.botlink}?start={user['magic']}"
            report['general'] += f"\nВолшебная ссылка:\n🔗{link}"
        else:
            report['general'] += "\n🚫 Не имеет VIP-статуса"

        refills = all_refills()
        user_refil_count = 0
        user_total_sum = 0
        for refill in refills:
            if int(refill['user_id']) == int(user_id):
                user_refil_count += 1
                user_total_sum += int(refill['amount'])

        report['general'] += f"\n💵 Финансовая статистика:\nВносил деньги <b>{user_refil_count}</b> раз\
               \nВсего внесено <b>{user_total_sum} руб.</b>"
        if user['referals']:
            referals_refills_sum = 0
            referals_refills_count = 0
            for ref_id in referals_array:
                referal_refills = get_user_all_refills(ref_id)
                for refill in referal_refills:
                    referals_refills_sum += int(refill['amount'])
                    referals_refills_count += 1
            report['general'] += f"\nрефералы вносили деньги <b>{referals_refills_count}</b> раз"
            report['general'] += f"\n💵 рефералы внесли <b>{referals_refills_sum} руб.</b>"

        if referals_count !=0:
            report['show_referals'] = True
        else:
            report['show_referals'] = False

        if total_user_orders != 0:
            report['show_orders'] = True
        else:
            report['show_orders'] = False

        if user_total_sum != 0:
            report['show_refills'] = True
        else:
            report['show_refills'] = False

        return report
    else:
        return None

@dp.message_handler(state=magic.user)
async def magic_gen(message: types.Message, state: FSMContext):
    param = message.text
    state_data = await state.get_data()
    magic_command = state_data['magic_command']
    if 'old_user' in state_data:
        user = state_data['old_user']
    else:
        user = await find_user(param)
    if 'page' in state_data:
        page = state_data['page']
    if user:
        if magic_command == "generate":
            STR = await generate_link(user['id'])
            await message.answer(STR, reply_markup=admin_back_kb(page))
        elif magic_command == "report":
            report = await gen_magic_report(user['id'])
            await state.update_data(report=report, old_user=user, show_referals=report['show_referals'], show_orders=report['show_orders'], show_refills=report['show_refills'], report_type='general')
            await message.answer(report['general'], reply_markup=magic_general_kb(page, report['show_referals'], report['show_orders'], report['show_refills']))
        elif magic_command == "orders":
            orders = user_orders_all(user['id'])
            if orders or user['referals']:
                #await message.answer_sticker('CAACAgIAAxkBAAKvAmZiNWq86qlTDZCQwMa766d7y6bUAAIuQQACL3WRSy5s2sn5ZuS8NQQ')
                #await message.answer(sheet_complete, reply_markup=gsheets_url(create_orders_report(user['id'])))
                STICKER = get_setting('wait_sticker')
                msg = await call.message.answer("Идет генерация отчета.")
                stick = await call.message.answer_sticker(STICKER)
                await call.message.answer(sheet_complete, reply_markup=gsheets_url(create_orders_report(user['id'])))
                try:
                    await bot.delete_message(chat_id=call.message.chat.id, message_id=msg.message_id)
                    await bot.delete_message(chat_id=call.message.chat.id, message_id=stick.message_id)
                except:
                    pass
            else:
                await message.answer_sticker('CAACAgIAAxkBAAKu7WZiNMTibB1NWrqCdYmB5cOumovSAAIwOQACTbCJS_QvdBkhGwOcNQQ')
                await message.answer("⚠️ Пользователь не оставил заказов!")
        elif magic_command == "refills":
            refills = get_user_all_refills(user['id'])
            if refills:
                #await message.answer_sticker('CAACAgIAAxkBAAKvAmZiNWq86qlTDZCQwMa766d7y6bUAAIuQQACL3WRSy5s2sn5ZuS8NQQ')
                #await message.answer(sheet_complete, reply_markup=gsheets_url(create_refills_report(user['id'])))
                STICKER = get_setting('wait_sticker')
                msg = await call.message.answer("Идет генерация отчета.")
                stick = await call.message.answer_sticker(STICKER)
                await call.message.answer(sheet_complete, reply_markup=gsheets_url(create_refills_report(user['id'])))
                try:
                    await bot.delete_message(chat_id=call.message.chat.id, message_id=msg.message_id)
                    await bot.delete_message(chat_id=call.message.chat.id, message_id=stick.message_id)
                except:
                    pass
            else:
                #await message.answer_sticker('CAACAgIAAxkBAAKu7WZiNMTibB1NWrqCdYmB5cOumovSAAIwOQACTbCJS_QvdBkhGwOcNQQ')
                await message.answer("⚠️ Пользователь не вносил деньги!")
    else:
        await message.answer(f"{user_not_in_base.format(param)}")

@dp.callback_query_handler(text_startswith="refills:", state="*")
async def call_user_all_refills(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print('Error deleting message!\n{e}')

    param = call.data.split(':')[1]
    state_data = await state.get_data()
    if 'old_user' not in state_data:
        if param == 'user':
            await call.message.answer(magic_report)
            await refills.user.set()
        elif param.isdigit():
            ref_page = call.data.split(':')[2]
            if 'report' in state_data:
                finance_report = state_data['report']['finance']
            if 'page_dict' in state_data:
                kb_page_dict = state_data['page_dict']
            await call.message.answer(finance_report[param], reply_markup=refill_ref_kb(user_id=param, kb_page_dict=kb_page_dict, page=ref_page))
    else:
        if param.isdigit():
            ref_page = call.data.split(':')[2]
            if 'report' in state_data:
                finance_report = state_data['report']['finance']
            if 'page_dict' in state_data:
                kb_page_dict = state_data['page_dict']
            if 'page' in state_data:
                page = state_data['page']
            else:
                page = 'to_general_user_report'
            await call.message.answer(finance_report[param], reply_markup=refill_ref_kb(user_id=param, kb_page_dict=kb_page_dict, page=ref_page, back=page))
        else:
            await user_all_refills_user(call.message, state)


async def user_gen_finance_report(user_id):
    finance_data = get_user_all_refills(str(user_id))
    user = get_user(id=str(user_id))
    user_name_str = await get_user_string_with_first_name(user)
    refill_count = 0
    all_referals_refill_count = 0
    user_total_finance = 0
    all_referals_total_finance = 0
    user_add_str = ""
    finance_report = {}
    finance_report[str(user_id)]=f"💰 <b>Финансовый отчет по пользователю:</b>\n<u>{user_name_str}</u>\n"
    for refill in finance_data:
        refill_count += 1
        user_add_str += f"✅<b>{refill['date']}</b> 💰<b>{refill['amount']}</b> руб.\n"
        user_total_finance += int(refill['amount'])
    finance_report[str(user_id)] += f"Пользователь вносил деньги <b>{refill_count}</b> раз\n"
    finance_report[str(user_id)] += user_add_str
    finance_report[str(user_id)] += f"Всего внесено: 💰 <b>{user_total_finance}</b> руб."
    if user['referals']:
        ref_arr = user['referals'].split(',')
        for referal_id in ref_arr:
            referal_refill_count = 0
            referal_total_finance = 0
            referal_add_str = ""
            ref_finance_data = get_user_all_refills(referal_id)
            referal = get_user(id=referal_id)
            referal_name_str = await get_user_string_with_first_name(referal)
            finance_report[str(referal_id)]=f"💰 <b>Финансовый отчет по пользователю:</b>\n<u>{referal_name_str}</u>\n"
            for refill in ref_finance_data:
                referal_refill_count += 1
                referal_add_str += f"✅<b>{refill['date']}</b> 💰 <b>{refill['amount']}</b> руб.\n"
                referal_total_finance += int(refill['amount'])
                all_referals_total_finance += int(refill['amount'])
            finance_report[str(referal_id)] += f"Пользователь вносил деньги {referal_refill_count} раз\n"
            finance_report[str(referal_id)] += referal_add_str
            finance_report[str(referal_id)] += f"Всего внесено: 💰<b>{referal_total_finance}</b> руб."
            all_referals_refill_count += 1
        finance_report[str(user_id)] += f"\nРефералы вносили деньги <b>{all_referals_refill_count}</b> раз."
        finance_report[str(user_id)] += f"\nВсего внесено рефералами: 💰<b>{all_referals_total_finance}</b> руб."
    return finance_report

@dp.message_handler(state=refills.user)
async def user_all_refills_user(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    if 'old_user' not in state_data:
        user = await find_user(message.text)
        page = 'users_man'
    else:
        user = state_data['old_user']
        page = 'to_general_user_report'
    if user:
        finance_report = await user_gen_finance_report(user['id'])
        if user['referals']:
            ref_page = 0
            kb_page_dict = {}
            ref_arr = user['referals'].split(',')
            for i in range(math.ceil(len(ref_arr) / 11)):
                kb_page_dict[str(i)] = []
            for ref_id in ref_arr:
                if len(kb_page_dict[str(ref_page)]) <= 11:
                    kb_page_dict[str(ref_page)].append(ref_id)
                else:
                    ref_page += 1
                    kb_page_dict[str(ref_page)].append(ref_id)
            await state.update_data(report={'finance': finance_report}, page_dict=kb_page_dict, old_user=user)
            await message.answer(finance_report[str(user['id'])], reply_markup=refill_ref_kb(str(user['id']), kb_page_dict, back=page))
        else:
            await message.answer(finance_report[str(user['id'])], reply_markup=admin_back_kb('users_man'))
    else:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('orders_man'))
        await state.finish()
"""
@dp.callback_query_handler(text="money_by_year", state="*")
async def call_money_by_year(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")
    refills = all_refills()
    await state.update_data(refills=refills)
    years_array = []
    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")  # Парсим строку даты в объект datetime
        if refill_date.year not in years_array:
            years_array.append(refill_date.year)
    await call.message.answer("Выберите год из списка:", reply_markup=money_by_years(years_array))

@dp.callback_query_handler(text_startswith="year:", state="*")
async def call_money_by_month(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")
    param = call.data.split(':')[1]
    state_data = await state.get_data()
    refills = state_data['refills']
    months_array = []
    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")  # Парсим строку даты в объект datetime
        month = refill_date.month
        if month not in months_array:
            months_array.append(month)
    await state.update_data(months=months_array)
    await call.message.answer("Выберите месяц из списка:", reply_markup=money_by_month(months_array))

@dp.callback_query_handler(text_startswith="month:", state="*")
async def call_money_report(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")
    param = call.data.split(':')[1]
    state_data = await state.get_data()
    refills = state_data['refills']
    months_array = state_data['months']
    total_month_money = 0
    total_money = 0
    days = []
    amounts = []
    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")  # Парсим строку даты в объект datetime
        month = refill_date.month
        if str(refill['user_id']) not in get_report_exclude():
            total_money += refill['amount']
            if int(month) == int(param):
                total_month_money += refill['amount']
                days.append(refill_date.day)
                amounts.append(refill['amount'])
    plt.figure(figsize=(10, 6))
    plt.bar(days, amounts, color='skyblue')
    plt.title(f'Гистограмма платежей за месяц {months_names[str(param)]}')
    plt.xlabel('День')
    plt.ylabel('Сумма')
    plt.xticks(days)

    # Сохраняем график в байтовый объект
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    await call.message.answer_photo(buf, caption=f"<b>💰 Финансовый отчет по месяцу {months_names[str(param)]}:</b>\nПользователями внесено <b>{total_month_money} руб.</b>\nЗа все время внесено <b>{total_money} руб.</b>", reply_markup=money_by_month(months_array))

    buf.close()
"""
"""
Начало отредактированного кода
"""

@dp.callback_query_handler(text="money_by_year", state="*")
async def call_money_by_year(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")

    refills = all_refills()  # Получаем все пополнения
    await state.update_data(refills=refills)

    years_array = []
    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")
        if refill_date.year not in years_array:
            years_array.append(refill_date.year)

    await call.message.answer("Выберите год из списка:", reply_markup=money_by_years(years_array))

@dp.callback_query_handler(text_startswith="year:", state="*")
async def call_money_by_month(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")

    year = call.data.split(':')[1]  # Получаем год из текста
    state_data = await state.get_data()
    refills = state_data['refills']

    months_array = []
    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")
        if refill_date.year == int(year) and refill_date.month not in months_array:
            months_array.append(refill_date.month)

    await state.update_data(months=months_array, year=year)
    await call.message.answer("Выберите месяц из списка:", reply_markup=money_by_month(months_array))

@dp.callback_query_handler(text_startswith="month:", state="*")
async def call_money_report(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")

    month = call.data.split(':')[1]  # Получаем месяц из текста
    state_data = await state.get_data()
    refills = state_data['refills']
    months_array = state_data['months']

    total_month_money = 0
    total_money = 0
    days = []
    amounts = []

    # Найдем год также из сохраненного состояния
    year = state_data.get('year')  # Получаем год, сохраненный ранее при выборе года

    for refill in refills:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")
        if refill_date.month == int(month) and refill_date.year == int(year):  # Проверяем соответствие
            if str(refill['user_id']) not in get_report_exclude():
                total_money += refill['amount']
                total_month_money += refill['amount']
                days.append(refill_date.day)
                amounts.append(refill['amount'])

    plt.figure(figsize=(10, 6))
    plt.bar(days, amounts, color='skyblue')
    plt.title(f'Гистограмма платежей за месяц {months_names[str(month)]} {year}')
    plt.xlabel('День')
    plt.ylabel('Сумма')
    plt.xticks(days)

    # Сохраняем график в байтовый объект
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    await call.message.answer_photo(
        buf,
        caption=f"<b>💰 Финансовый отчет за {months_names[str(month)]} {year}:</b>\n"
                f"Пользователями внесено <b>{total_month_money} руб.</b>\n"
                f"За все время внесено <b>{total_money} руб.</b>",
        reply_markup=money_by_month(months_array)
    )

    buf.close()

"""
До сих пор код отредактирован ГПТшкой
"""

@dp.callback_query_handler(text="get_vip", state="*")
async def call_get_vip(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message\n{e}")

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

###############################################################################################
#############################             Отзывы               ################################
###############################################################################################

@dp.callback_query_handler(text="reviews_man", state="*")
async def call_reviews_man(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message")

    #all_orders = all_orders_reviews()
    all_orders = await sql_get_all_reviews()

    total_orders = 0
    vk_cnt = 0
    gis_cnt = 0
    google_cnt = 0
    flamp_cnt = 0
    avito_cnt = 0
    yandex_cnt = 0
    total_paid = 0
    vk_paid = 0
    gis_paid = 0
    google_paid = 0
    flamp_paid = 0
    avito_paid = 0
    yandex_paid = 0

    for order in all_orders:
        if order['user_id'] not in get_report_exclude():
            if order['service'] == 'vk':
                vk_cnt += 1
                vk_paid += int(order['price'])
            elif order['service'] == '2gis':
                gis_cnt += 1
                gis_paid += int(order['price'])
            elif order['service'] == 'google':
                google_cnt += 1
                google_paid += int(order['price'])
            elif order['service'] == 'flamp':
                flamp_cnt += 1
                flamp_paid += int(order['price'])
            elif order['service'] == 'avito':
                avito_cnt += 1
                avito_paid += int(order['price'])
            elif order['service'] == 'yandex':
                yandex_cnt += 1
                yandex_paid += int(order['price'])
            total_orders += 1
            total_paid += int(order['price'])

    delreviews = all_orders_delreviews()

    del_reviews_cnt = 0
    del_reviews_paid = 0

    for order in delreviews:
        if order['user_id'] not in get_report_exclude():
            if order['service'] == 'avito':
                del_reviews_cnt += 1
                del_reviews_paid += int(order['price'])

    #await call.message.answer_sticker('CAACAgIAAxkBAAEBJRBmdd5oCPLo6vXtzFQ0aUXwf7i-eQACdEIAAucOkEtX70Rr-qnYCDUE')
    await call.message.answer(f"📖<b>Отчет по заказам:</b>\n"
                              f"<u>Всего</u> <b>{total_orders}</b> из них:\n"
                              f"<u>Авито:</u> <b>{avito_cnt}</b> ({avito_paid} руб.)\n"
                              f"<u>ВКонтакте:</u> <b>{vk_cnt}</b> ({vk_paid} руб.)\n"
                              f"<u>Google:</u> <b>{google_cnt}</b> ({google_paid} руб.)\n"
                              f"<u>Flamp:</u> <b>{flamp_cnt}</b> ({flamp_paid} руб.)\n"
                              f"<u>2ГИС:</u> <b>{gis_cnt}</b> ({gis_paid} руб.)\n"
                              f"<u>Яндекс:</u> <b>{yandex_cnt}</b> ({yandex_paid} руб.)\n"
                              f"💵Всего заработано: <b>{total_paid} руб.</b>\n"
                              f"<u>Заказы на удаление отзывов:</u> <b>{del_reviews_cnt}</b> ({del_reviews_paid} руб.)", reply_markup=reviews_man_kb())


@dp.callback_query_handler(text="rev_user_search", state="*")
async def call_rev_user_search(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    await call.message.answer(magic_report)
    await reviews.user.set()

@dp.message_handler(state=reviews.user)
async def user_all_reviews(message: types.Message, state: FSMContext):
    try:
        rev_arr = []
        user = await find_user(message.text)
        orders = await sql_get_all_reviews_by_user(user['id'])
        STR = get_string('str_new_review_admin_report')
        usr_str = await get_user_string_without_first_name(user)
        for order in orders:
            service = services[order['service']]
            if order['status'] == 'Posted':
                status = 'Размещен'
            elif order['status'] == 'Completed':
                status = 'Выполнен'
            elif order['status'] == 'In progress':
                status = 'Выполняется'
            f_price = format_decimal(order['price'])
            STR = STR.format(order['id'], f_price, usr_str, service, status, order['date'], order['link'])
            rev_arr.append(STR)

        await message.answer(rev_arr[len(rev_arr)-1], reply_markup=show_admin_review_by_index(len(orders)-1, len(orders)))
        await state.update_data(orders=orders, array=rev_arr)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка получения заказов пользователя!\n{e}", reply_markup=admin_back_kb('reviews_man'))
        await state.finish()

@dp.callback_query_handler(text_startswith="review:", state="*")
async def admin_call_show_review_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message!\n{e}")
    index = int(call.data.split(":")[1])
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    await call.message.answer(f"Страница {index+1} из {len(orders)}\n{orders_array[index]}", reply_markup=show_admin_review_by_index(index, len(orders)))


@dp.callback_query_handler(text="admin_show_all_reviews", state="*")
async def admin_call_show_all_reviews(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    if orders:
        orders_array = reviews_array(orders)
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsRmZiHByCAAGHv2QnvB5WC0gOcM2S6QACdEIAAucOkEtX70Rr-qnYCDUE')
        for order in orders_array:
            await call.message.answer(order)
        await call.message.answer("Выберите действие:", reply_markup=admin_back_kb('reviews_man'))
    else:
        #await call.message.answer_sticker('CAACAgIAAxkBAAKsTGZiHN5_OkQDOquJfFQslnkHwYavAAIwOQACTbCJS_QvdBkhGwOcNQQ')
        await call.message.answer("⚠️ Ошибка получения заказов пользователя!", reply_markup=admin_back_kb('reviews_man'))

@dp.callback_query_handler(text="reviw_close", state="*")
async def admin_call_review_close(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer("⚙️ Введите номер заказа:")
    await reviews.close.set()

@dp.message_handler(state=reviews.close)
async def review_close(message: types.Message, state: FSMContext):
    try:
        review = get_order_reviews(message.text)
        if review['status'] == 'Размещен':
            edit_order_reviews('Выполнен', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('reviews_man'))
            await bot.send_message(chat_id=review['user_id'], text=f"<b>🎉 Ваш заказ номер {review['id']} на сервисе {review['service']} успешно выполнен!</b>")
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('reviews_man'))
    except Exception as e:
        await message.answer(f'⚠️ Ощибка получения заказа\n{e}', reply_markup=admin_back_kb('reviews_man'))

@dp.callback_query_handler(text="reviews_sheet", state="*")
async def admin_call_reviews_gsheets(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    orders = await sql_get_all_reviews()
    STICKER = get_setting('wait_sticker')
    msg = await call.message.answer("Идет генерация отчета.")
    stick = await call.message.answer_sticker(STICKER)
    await call.message.answer(sheet_complete, reply_markup=gsheets_url(create_reviews_report(orders)))
    try:
        await bot.delete_message(chat_id=call.message.chat.id, message_id=msg.message_id)
        await bot.delete_message(chat_id=call.message.chat.id, message_id=stick.message_id)
    except:
        pass

@dp.callback_query_handler(text="del_rev_user_search", state='*')
async def call_del_rev_user_search(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    await call.message.answer(magic_report)
    await del_reviews.user.set()

@dp.message_handler(state=del_reviews.user)
async def del_reviews_search(message: types.Message, state: FSMContext):
    try:
        user = await find_user(message.text)
        orders = user_orders_all_delreviews(user['id'])
        rev_arr = del_reviews_array(orders=orders, )
        await message.answer(rev_arr[len(rev_arr)-1], reply_markup=show_admin_review_by_index(len(orders)-1, len(orders)))
        await state.update_data(orders=orders, array=rev_arr)
    except Exception as e:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text=main_menu,
                callback_data="to_admin_menu"
            )
        )
        await message.answer(f"⚠️ Ошибка получения заказов пользователя!\n{e}", reply_markup=keyboard)
        await state.finish()

@dp.callback_query_handler(text="del_review_close", state="*")
async def admin_call_del_review_close(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer("⚙️ Введите номер заказа:")
    await del_reviews.close.set()

@dp.message_handler(state=del_reviews.close)
async def del_review_close(message: types.Message, state: FSMContext):
    try:
        del_review = get_order_delreviews(message.text)
        if del_review['status'] == 'Размещен':
            edit_order_delreviews('Выполнен', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('reviews_man'))
            await bot.send_message(chat_id=del_review['user_id'], text=f"<b>🎉 Ваш заказ на удаление негативного отзыва номер {del_review['increment']} на сервисе {del_review['service']} успешно выполнен!</b>")
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f'⚠️ Ощибка получения заказа\n{e}', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()

###############################################################################################
#############################           Настройки              ################################
###############################################################################################

#Настройки
@dp.callback_query_handler(text="settings", state="*")
async def admin_call_settings(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer("⚙️ Вы в пункте \"Настройки\". Выбирите вариант:", reply_markup=setup_kb())

#Касса/цены
@dp.callback_query_handler(text="price_setup", state="*")
async def admin_call_price_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    #await call.message.answer(text=in_devel, reply_markup=admin_back_kb('settings'))
    pay_work = str2bool(get_setting('payment_work'))
    #print(pay_work)
    if pay_work:
       STR = "Касса сейчас работает. Отключаем?"
    else:
       STR = "Касса сейчас отключена. Включить?"
    await call.message.answer(text=STR, reply_markup=payment_setup_kb(str(not pay_work)))



@dp.callback_query_handler(text_startswith="payment_toggle:", state="*")
async def admin_call_payment_toggle(call: types.CallbackQuery, state: FSMContext):
    value = call.data.split(":")[1]
    edit_setting('payment_work', value)
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    pay_work = str2bool(get_setting('payment_work'))
    if pay_work:
       STR = "Касса сейчас работает. Отключаем?"
    else:
       STR = "Касса сейчас отключена. Включить?"
    await call.message.answer(text=STR, reply_markup=payment_setup_kb(str(not pay_work)))

#Интерфейс
@dp.callback_query_handler(text="interface_setup", state="*")
async def admin_call_interface_setup(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer(text="⚙️ Вы в пункте \"Интерфейс\". Выбирите вариант:", reply_markup=setup_strings_kb())

#Визуальный редактор строк
@dp.callback_query_handler(text="str_visual_edit", state="*")
async def admin_call_str_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    all_str = get_all_strings()
    captions_array = []
    for string in all_str:
        if 'str_' in string['parametr']:
            captions_array.append(string)
    await call.message.answer(f"Страница 1 из {len(captions_array)}\n{captions_array[0]['value']}", reply_markup=str_visual_edit_kb(0, len(all_str), 'interface_setup'))

@dp.callback_query_handler(text_startswith="caption:", state="*")
async def admin_call_str_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    index = int(call.data.split(":")[1])
    all_str = get_all_strings()
    captions_array = []
    for string in all_str:
        if 'str_' in string['parametr']:
            captions_array.append(string)
    await call.message.answer(f"Страница {index+1} из {len(captions_array)}\n{captions_array[index]['value']}", reply_markup=str_visual_edit_kb(index, len(captions_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="edit:", state="*")
async def admin_call_str_visual_edit_param(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    index = int(call.data.split(":")[1])
    await state.update_data(index=index)
    await call.message.answer("Введите новое значение:")
    await setup_class.string_edit.set()

@dp.message_handler(state=setup_class.string_edit)
async def str_edit_value(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    index = state_data['index']
    all_str = get_all_strings()
    select_string = all_str[index]
    edit_string(select_string['parametr'], message.text)
    await message.answer("Строка успешно изменена!", reply_markup=admin_back_kb(f'caption:{index}'))

#Визуальный редактор кнопок
@dp.callback_query_handler(text="btn_visual_edit", state="*")
async def admin_call_btn_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    all_str = get_all_strings()
    btn_array = []
    for btn in all_str:
        if 'btn_' in btn['parametr']:
            btn_array.append(btn)
    await call.message.answer(f"Страница 1 из {len(btn_array)}\n{btn_array[0]['value']}", reply_markup=btn_visual_edit_kb(0, len(btn_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="btn:", state="*")
async def admin_call_btn_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    index = int(call.data.split(":")[1])
    all_str = get_all_strings()
    btn_array = []
    for btn in all_str:
        if 'btn_' in btn['parametr']:
            btn_array.append(btn)
    await call.message.answer(f"Страница {index+1} из {len(btn_array)}\n{btn_array[index]['value']}", reply_markup=btn_visual_edit_kb(index, len(btn_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="btn_edit:", state="*")
async def admin_call_btn_visual_edit_param(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    index = int(call.data.split(":")[1])
    await state.update_data(index=index)
    await call.message.answer("Введите новое значение:")
    await setup_class.btn_edit.set()

@dp.message_handler(state=setup_class.btn_edit)
async def str_edit_value(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    index = state_data['index']
    all_str = get_all_strings()
    btn_array = []
    for btn in all_str:
        if 'btn_' in btn['parametr']:
            btn_array.append(btn)
    select_btn = btn_array[index]
    edit_string(select_btn['parametr'], message.text)
    await message.answer("Кнопка успешно изменена!", reply_markup=admin_back_kb(f'btn:{index}'))

#Меню переменных
@dp.callback_query_handler(text="variables_setup", state="*")
async def admin_call_variable_setup(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer('Меню \"Переменные\". Выберите действие:', reply_markup=setup_variables_kb())

#Посмотреть переменную
@dp.callback_query_handler(text="str_variable_view", state="*")
async def admin_call_str_variable_view(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    settings = get_all_strings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range (len(settings)):
        if i < len(settings):
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}\n"
        else:
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}"

    if len(STR) < 4096:
        await call.message.answer(STR)
    else:
        MSG = STR.split("\n")
        MSG_PARTS = split_messages(MSG, "\n")
        for i in range (len(MSG_PARTS)):
            await call.message.answer(MSG_PARTS[i])
    await setup_class.str_variable_view.set()

#Добавить переменную
@dp.callback_query_handler(text="str_variable_add", state="*")
async def admin_call_str_variable_add(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    #await call.message.answer(text=in_devel, reply_markup=admin_back_kb(None))
    await call.message.answer(text="""✏️ Введите данные в виде:
        Параметр|описание|значение""")
    await setup_class.str_variable_add.set()

@dp.message_handler(state=setup_class.str_variable_add)
async def str_variable_add_parametr(message: types.Message, state: FSMContext):
    parametr = message.text.split("|")[0]
    description = message.text.split("|")[1]
    str_value = message.text.split("|")[2]
    add_string_to_base(parametr, description, str_value)
    await message.answer(text="👌🏻 Переменная добавлена!", reply_markup=admin_back_kb("variables_setup"))
    await state.finish()

@dp.message_handler(state=setup_class.str_variable_view)
async def str_variable_view_parametr(message: types.Message, state: FSMContext):
    STR = get_string_from_base(message.text)
    if STR:
        await message.answer(text=f"<code>{message.text}:</code>\n{STR['value']}", reply_markup=admin_back_kb("variables_setup"))
    else:
        await message.answer(text=f"⚠️ Нет такой строки!", reply_markup=admin_back_kb("variables_setup"))
    await state.finish()

#Кнопки. Посмотреть.
@dp.callback_query_handler(text="btn_view", state="*")
async def admin_call_btn_view(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    settings = get_all_strings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range (len(settings)):
        if "btn_" in settings[i]['parametr']:
            if i < len(settings):
                STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}\n"
            else:
                STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}"
    await call.message.answer(text=STR)
    await setup_class.button_view.set()

@dp.message_handler(state=setup_class.button_view)
async def btn_view_parametr(message: types.Message, state: FSMContext):
    STR = get_string_from_base(message.text)
    if STR:
        await message.answer(text=f"<code>{message.text}:</code>\n{STR['value']}", reply_markup=admin_back_kb("interface_setup"))
    else:
        await message.answer(text=f"⚠️ Нет такой строки!", reply_markup=admin_back_kb("interface_setup"))
    await state.finish()

#Кнопки. Создать.
@dp.callback_query_handler(text="btn_add", state="*")
async def admin_call_btn_add(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    #await call.message.answer(text=in_devel, reply_markup=admin_back_kb(None))
    await call.message.answer(text="""✏️ Введите данные в виде:
        Параметр|описание|значение""")
    await setup_class.button_add.set()

@dp.message_handler(state=setup_class.button_add)
async def btn_add_parametr(message: types.Message, state: FSMContext):
    parametr = message.text.split("|")[0]
    description = message.text.split("|")[1]
    str_value = message.text.split("|")[2]
    add_string_to_base(parametr, description, str_value)
    await message.answer(text="👌🏻 Переменная добавлена!", reply_markup=admin_back_kb("interface_setup"))
    await state.finish()

#Посмотреть переменную из таблицы settings
@dp.callback_query_handler(text="variable_view", state="*")
async def admin_call_variable_view(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    settings = get_all_settings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range (len(settings)):
        if i < len(settings):
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}\n"
        else:
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}"

    if len(STR) < 4096:
        await call.message.answer(STR)
    else:
        MSG = STR.split("\n")
        MSG_PARTS = split_messages(MSG, "\n")
        for i in range (len(MSG_PARTS)):
            await call.message.answer(MSG_PARTS[i])
    await setup_class.variable_view.set()

@dp.message_handler(state=setup_class.variable_view)
async def variable_view_parametr(message: types.Message, state: FSMContext):
    STR = get_setting_from_base(message.text)
    if STR:
        await message.answer(text=f"<code>{message.text}:</code>\n{STR['value']}", reply_markup=admin_back_kb("variables_setup"))
    else:
        await message.answer(text=f"⚠️ Нет такой строки!", reply_markup=admin_back_kb("variables_setup"))
    await state.finish()

#Добавить переменную в таблицу settings
@dp.callback_query_handler(text="variable_add", state="*")
async def admin_call_variable_add(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    #await call.message.answer(text=in_devel, reply_markup=admin_back_kb(None))
    await call.message.answer(text="""✏️ Введите данные в виде:
        Параметр|описание|значение""")
    await setup_class.variable_add.set()

@dp.message_handler(state=setup_class.variable_add)
async def variable_add_parametr(message: types.Message, state: FSMContext):
    parametr = message.text.split("|")[0]
    description = message.text.split("|")[1]
    str_value = message.text.split("|")[2]
    add_setting_to_base(parametr, description, str_value)
    await message.answer(text="👌🏻 Переменная добавлена!", reply_markup=admin_back_kb("variables_setup"))
    await state.finish()

###############################################################################################
#############################       Управление  админами       ################################
###############################################################################################

@dp.callback_query_handler(text="admins_setup", state="*")
async def admin_call_admins_setup(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer(text="👑 Управление админами:", reply_markup=setup_admins())
    #await setup_class.variable_add.set()

@dp.callback_query_handler(text_startswith="admin:", state="*")
async def admin_call_add_del_admins(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    action = call.data.split(':')[1]
    await state.update_data(action=action)
    if action == 'add':
        await call.message.answer('👑 Введите ID или ник пользователя, которого хотите сделать админом:', reply_markup=admin_back_kb("admins_setup"))
        await setup_class.set_admin.set()
    elif action == 'del':
        await call.message.answer('👑 удалить пользователя из админов:', reply_markup=del_admin_kb())

@dp.message_handler(state=setup_class.set_admin)
async def admin_add_admin(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    action = state_data.get('action')

    if action == 'add':
        user_id_str = message.text.strip()  # Удаление лишних пробелов
        if user_id_str.isdigit():
            add_admin(user_id_str)
            await message.answer(f'✅ Пользователь с ID {user_id_str} стал админом!', reply_markup=admin_back_kb("admins_setup"))
        else:
            user = await find_user(user_id_str)  # Предполагается, что find_user ищет по username
            if user:
                usr_str = await get_user_string_without_first_name(user)
                add_admin(str(user['id']))
                await message.answer(f'✅ Пользователь {usr_str} стал админом!', reply_markup=admin_back_kb("admins_setup"))
            else:
                await message.answer(f'⚠️ Пользователь {user_id_str} не найден в базе. Введите ID нового пользователя!')
                await setup_class.set_admin.set()

    # Обработчик в случае других действий или для завершения изменения состояния
    else:
        await message.answer('⚠️ Некорректное действие. Пожалуйста, попробуйте еще раз.')

@dp.callback_query_handler(text_startswith="del_admin:", state="*")
async def admin_call_del_admin_by_id(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    id_to_del = call.data.split(':')[1]
    del_admin(id_to_del)
    await call.message.answer('❎ Пользователь удален из админов!', reply_markup=admin_back_kb("admins_setup"))

#Исключения.
@dp.callback_query_handler(text="spam_exclude", state="*")
async def admin_call_spam_exclude(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer('👑 Введите ID или ник пользователя, которого хотите исключить из рассылки:', reply_markup=admin_back_kb("admins_setup"))
    await setup_class.spam_exclude.set()

@dp.message_handler(state=setup_class.spam_exclude)
async def admin_add_spam_exclude(message: types.Message, state: FSMContext):
    user_id_str = message.text.strip()  # Удаление лишних пробелов
    if user_id_str.isdigit():
        add_spam_exclude(user_id_str)
        await message.answer(f'✅ Пользователь с ID {user_id_str} исключен из рассылки!', reply_markup=admin_back_kb("admins_setup"))
    else:
        user = await find_user(user_id_str)  # Предполагается, что find_user ищет по username
        if user:
            usr_str = await get_user_string_without_first_name(user)
            add_spam_exclude(str(user['id']))
            await message.answer(f'✅ Пользователь {usr_str} исключен из рассылки!', reply_markup=admin_back_kb("admins_setup"))
        else:
            await message.answer(f'⚠️ Пользователь {user_id_str} не найден в базе. Введите ID нового пользователя!')
            await setup_class.spam_exclude.set()

@dp.callback_query_handler(text="report_exclude", state="*")
async def admin_call_report_exclude(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    await call.message.answer('👑 Введите ID или ник пользователя, которого хотите исключить из отчетов:', reply_markup=admin_back_kb("admins_setup"))
    await setup_class.report_exclude.set()

@dp.message_handler(state=setup_class.report_exclude)
async def admin_add_report_exclude(message: types.Message, state: FSMContext):
    user_id_str = message.text.strip()  # Удаление лишних пробелов
    if user_id_str.isdigit():
        add_report_exclude(user_id_str)
        await message.answer(f'✅ Пользователь с ID {user_id_str} исключен из отчетов!', reply_markup=admin_back_kb("admins_setup"))
    else:
        user = await find_user(user_id_str)  # Предполагается, что find_user ищет по username
        if user:
            usr_str = await get_user_string_without_first_name(user)
            add_report_exclude(str(user['id']))
            await message.answer(f'✅ Пользователь {usr_str} исключен из отчетов!', reply_markup=admin_back_kb("admins_setup"))
        else:
            await message.answer(f'⚠️ Пользователь {user_id_str} не найден в базе. Введите ID нового пользователя!')
            await setup_class.spam_exclude.set()

###############################################################################################
#############################              Прайс               ################################
###############################################################################################

#Редактирование прайса
@dp.callback_query_handler(text_startswith="price_edit:", state="*")
async def admin_call_price_edit(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    service = call.data.split(':')[1]
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    price = get_price(f"price_{service}")

    await state.update_data(service=service, price=price)

    if service=="avito_pf" or service == "seo"  or service == 'avito_del_review':
        await call.message.answer(f"Актуальная цена {price} ₽. Введите новое значение в ₽:")
        await setup_class.price_edit.set()
    else:
        await call.message.answer(f"Прайс для сервиса \"Отзывы {services[service]}\":", reply_markup=edit_price_kb(service, price, 3))


@dp.callback_query_handler(text_startswith="edit_price-", state="*")
async def admin_call_edit_price_function(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    service = call.data.split('-')[1]
    price_item = call.data.split('-')[2]
    k = price_item.split(':')[0]
    v = price_item.split(':')[1]
    price = get_price(f"price_{service}")
    await state.update_data(key=k)
    rev_dec = declension_review(int(k))
    f_old_price = format_decimal(int(v))
    await call.message.answer(f"Редактирование цены на <b>{k} {rev_dec}</b>. Для сервиса \"{services[service]}\" Старая цена: <b>{f_old_price} ₽</b>. Введите новую цену:")
    await setup_class.price_edit.set()

@dp.message_handler(state=setup_class.price_edit)
async def price_edit_function(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    service = state_data['service']
    price = state_data['price']

    if message.text.isdigit():
        if service == 'avito_pf' or service == 'seo' or service == 'avito_del_review':
            edit_setting(f"price_{service}", message.text)
        else:
            key = state_data['key']
            price = get_price(f'price_{service}')
            price[key] = int(message.text)
            new_price = str(price)
            edit_setting(f"price_{service}", new_price)
        await message.answer("💰 Прайс успешно изменен!", reply_markup=admin_back_kb("price_setup"))
        await state.finish()
    else:
        await message.answer('⚠️ Неверное значение! Цена должна быть числом!')


#Минимальны платеж
@dp.callback_query_handler(text="min_amount", state="*")
async def admin_call_min_amount(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')
    min_amo = int(get_setting('min_amount'))
    f_min_amo = format_decimal(min_amo)
    await call.message.answer(f'Сейчас минимальный платеж составляет {f_min_amo} ₽. Введите новое значение:')
    await setup_class.min_amount.set()

@dp.message_handler(state=setup_class.min_amount)
async def price_min_amount(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        edit_setting("min_amount", message.text)
        f_min_amo = format_decimal(message.text)
        await message.answer(f"💰 Минимальный платеж изменен и составляет {f_min_amo} ₽.", reply_markup=admin_back_kb("price_setup"))
        await state.finish()
    else:
        await message.answer('⚠️ Неверное значение! Цена должна быть числом!')
    await state.finish()

###############################################################################################
#############################        Прогрес-бар (inDevel)     ################################
###############################################################################################

import queue
import threading
import time

def long_function(q): # некая функция, которая выполняется какое-то время,
    orders = all_orders()
    n = 0
    percents = 0
    for order in orders:
        n += 1
        percents = n/len(orders) * 10
        q.put_nowait(int(percents))

    """
    n=0
    while n<10:
        #time.sleep(2)
        n=n+1
        q.put_nowait(n)  # собственно какой-то способ как отдавать на каждой итерации переменную
    """

@dp.message_handler(commands=['start_progress'])
async def start_progress(message: types.Message, state: FSMContext):
    await message.answer("Запуск длительной операции...")
    await state.set_state(ProgressStates.progress.state)

    qe = queue.Queue()
    t = threading.Thread(target=long_function, args=[qe])
    t.start()

    # Пример длительной операции с обновлением прогресса
    total_steps = 10
    msg = await message.answer('[                    ] начинаем.')
    while t.is_alive(): # пока функция выполняется
        n = qe.get()
        #'█'
        #◼️
        progress_bar = '[' + '◼️' * int(n) + '  ' * (total_steps - n) + ']'
        await bot.edit_message_text(f'{progress_bar} {n * 10}% завершено.', chat_id=message.chat.id, message_id=msg.message_id)
    """
    for step in range(total_steps + 1):
        # Формируем текст индикатора прогресса
        progress_bar = '[' + '█' * step + '  ' * (total_steps - step) + ']'
        #msg = await message.answer(f'{progress_bar} {step * 10}% завершено.')
        await bot.edit_message_text(f'{progress_bar} {step * 10}% завершено.', chat_id=message.chat.id, message_id=msg.message_id)
        # Имитируем длительную задачу
        while t.is_alive(): # пока функция выполняется
            n = qe.get()
            await asyncio.sleep(n)  # Задержка 1 секунда для имитации работы
        #await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    """

    await message.answer("Операция завершена!")
    await state.finish()

@dp.message_handler(commands=['globals'])
async def globals(message: types.Message, state: FSMContext):
    await message.answer(globals())