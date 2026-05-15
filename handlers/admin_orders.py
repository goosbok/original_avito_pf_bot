import logging
import math
import io
from datetime import datetime

import matplotlib.pyplot as plt

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp, bot
from data.config import services
from utils.sqlite3 import (
    get_user, get_order, edit_order, delete_order, all_orders, all_orders_by_status,
    user_orders_all,
    get_user_all_refills, all_refills,
    get_string, get_setting,
    get_report_exclude,
    all_orders_reviews, all_orders_delreviews,
    user_orders_all_delreviews,
    get_tg_id_for_user,
)
from utils.other import (
    get_user_string_without_first_name, get_user_string_with_first_name,
    get_days_suffix, format_decimal, split_messages, decline_order,
)
from design import (
    listord_array, order_text,
    magic_ref, magic_report, magic_gen_str,
    sheet_complete, user_not_in_base,
)
from keyboards.inline_keyboards import (
    orders_kb, admin_back_kb, gsheets_url, magic_kb,
    show_admin_order_by_index,
    magic_general_kb, magic_referals_kb, refill_ref_kb,
    money_by_years, money_by_month, months_names,
)
from utils.googlesheets import create_orders_report, create_refills_report
from .admin_base import find_user, generate_random_string

logger = logging.getLogger(__name__)


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


###############################################################################################
#############################          Заказы Авито ПФ         ################################
###############################################################################################

@dp.callback_query_handler(text="orders_man", state='*')
async def orders_man(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
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
    STR = f"♾️ Всего <b>{orders_cnt} {ord_dec}</b>\n✅ Выполнено: {completed_cnt}\n✍🏻 Не выполнено {posted_cnt}\nВсего заработано <b>{f_payed} ₽</b>\n⚙️ Управление заказами:"
    await call.message.answer(STR, reply_markup=orders_kb())

    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


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
        logger.debug("could not delete message")
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
            if not orders:
                await message.answer(f"⚠️ У пользователя нет заказов.", reply_markup=admin_back_kb('orders_man'))
                await state.finish()
                return
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
        logger.debug("could not delete message")
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    if orders:
        orders_array = listord_array(orders)
        for order in orders_array:
            await call.message.answer(order)
        await call.message.answer("Выберите действие:", reply_markup=admin_back_kb('orders_man'))
    else:
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
    links = ''
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
        logger.debug("could not delete message")
    await bot.send_message(chat_id=call.from_user.id, text=f"⚙️ Введите ID заказа:")
    await Order1.order.set()


@dp.message_handler(state=Order1.order)
async def order_finish(message: types.Message, state: FSMContext):
    order = message.text
    edit_order(status="Completed", order=order)
    order1 = get_order(order)
    internal_id = order1['user_id']
    tg_id = get_tg_id_for_user(internal_id)
    if tg_id:
        await bot.send_message(chat_id=tg_id, text=f"✅ Ваш заказ №{order} выполнен.")
    await bot.send_message(chat_id=message.from_user.id, text="✅ Успешно")
    await state.finish()


@dp.callback_query_handler(text="gsheets")
async def gsheets(call: types.CallbackQuery, state: FSMContext):
    from utils.googlesheets import create_sheet
    chat_id = call.message.chat.id

    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    STICKER = get_setting('wait_sticker')
    msg = await bot.send_message(chat_id=chat_id, text="⏳ Идет генерация отчета.")
    stick = await bot.send_sticker(chat_id=chat_id, sticker=STICKER) if STICKER else None

    try:
        sheet_url = create_sheet()
        await bot.send_message(chat_id=chat_id, text=sheet_complete, reply_markup=gsheets_url(sheet_url))
    except Exception as e:
        logger.exception('googlesheets: failed to create sheet')
        await bot.send_message(chat_id=chat_id, text="⚠️ Ошибка при генерации отчета!")
    finally:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            if stick:
                await bot.delete_message(chat_id=chat_id, message_id=stick.message_id)
        except:
            pass


@dp.callback_query_handler(text_startswith="orders_", state="*")
async def admin_call_orders_by_status(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    action = call.data.split('_')[1]
    if action == "completed":
        sort_orders = all_orders_by_status('Completed')
    elif action == "posted":
        sort_orders = all_orders_by_status('Posted')
    else:
        await call.message.answer("⚠️ Неизвестное действие.", reply_markup=admin_back_kb('orders_man'))
        return
    if not sort_orders:
        await call.message.answer("⚠️ Заказов с таким статусом нет.", reply_markup=admin_back_kb('orders_man'))
        return
    orders_array = listord_array(sort_orders)
    cnt = len(orders_array)
    await state.update_data(orders=sort_orders, array=orders_array)
    await call.message.answer(f"Страница {cnt} из {cnt}\n{orders_array[cnt-1]}",
        reply_markup=show_admin_order_by_index(cnt - 1, cnt, page='orders_man', all_orders=False))


@dp.callback_query_handler(text="magic", state="*")
async def magic_menu(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🔮 волшебное меню", reply_markup=magic_kb())
    await state.update_data(page=call.data)
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


@dp.callback_query_handler(text_startswith="magic:", state="*")
async def magic_start(call: types.CallbackQuery, state: FSMContext):
    param = call.data.split(':')[1]
    state_data = await state.get_data()
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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
        if len(state_data['report']['referals']) < 4096:
            await call.message.answer(state_data['report']['referals'], reply_markup=magic_referals_kb(page, show_orders, show_refills))
        else:
            MSG = state_data['report']['referals'].split(",")
            MSG_PARTS = split_messages(MSG, ",")
            for i in range(len(MSG_PARTS)):
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
        logger.debug("could not delete message", exc_info=True)

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
    from data import config as _config
    user = get_user(id=user_id)
    if user:
        if user['magic'] is None:
            magic_str = generate_random_string(10)
            from utils.sqlite3 import update_user
            update_user(id=user_id, magic=magic_str, is_vip=1)
            link = f"{_config.botlink}?start={magic_str}"
            name = await get_user_string_with_first_name(user)
            STR = f"{magic_gen_str.format(name, link)}"
            return STR
        else:
            magic_str = user['magic']
            link = f"{_config.botlink}?start={magic_str}"
            name = await get_user_string_with_first_name(user)
            STR = f"{magic_gen_str.format(name, link)}"
            return STR
    else:
        return None


async def gen_magic_report(user_id):
    from data import config as _config
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

        users_list = []
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

        simply_ref_link = f"{_config.botlink}?start={user_id}"
        if referals_count != 0:
            report['general'] += f"\n🐹 рефералы: <b>{referals_count}</b>"
        report['general'] += f"\nРеферальная ссылка:\n🔗{simply_ref_link}"

        if user['magic']:
            link = f"{_config.botlink}?start={user['magic']}"
            report['general'] += f"\nВолшебная ссылка:\n🔗{link}"
        else:
            report['general'] += "\n🚫 Не имеет VIP-статуса"

        refills_list = all_refills()
        user_refil_count = 0
        user_total_sum = 0
        for refill in refills_list:
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

        if referals_count != 0:
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
                STICKER = get_setting('wait_sticker')
                msg = await message.answer("Идет генерация отчета.")
                stick = await message.answer_sticker(STICKER) if STICKER else None
                await message.answer(sheet_complete, reply_markup=gsheets_url(create_orders_report(user['id'])))
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
                    if stick:
                        await bot.delete_message(chat_id=message.chat.id, message_id=stick.message_id)
                except:
                    pass
            else:
                await message.answer("⚠️ Пользователь не оставил заказов!")
        elif magic_command == "refills":
            refills_list = get_user_all_refills(user['id'])
            if refills_list:
                STICKER = get_setting('wait_sticker')
                msg = await message.answer("Идет генерация отчета.")
                stick = await message.answer_sticker(STICKER) if STICKER else None
                await message.answer(sheet_complete, reply_markup=gsheets_url(create_refills_report(user['id'])))
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
                    if stick:
                        await bot.delete_message(chat_id=message.chat.id, message_id=stick.message_id)
                except:
                    pass
            else:
                await message.answer("⚠️ Пользователь не вносил деньги!")
    else:
        await message.answer(f"{user_not_in_base.format(param)}")


@dp.callback_query_handler(text_startswith="refills:", state="*")
async def call_user_all_refills(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug("could not delete message", exc_info=True)

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
    finance_report[str(user_id)] = f"💰 <b>Финансовый отчет по пользователю:</b>\n<u>{user_name_str}</u>\n"
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
            finance_report[str(referal_id)] = f"💰 <b>Финансовый отчет по пользователю:</b>\n<u>{referal_name_str}</u>\n"
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


@dp.callback_query_handler(text="money_by_year", state="*")
async def call_money_by_year(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug("could not delete message", exc_info=True)

    refills_list = all_refills()
    await state.update_data(refills=refills_list)

    years_array = []
    for refill in refills_list:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")
        if refill_date.year not in years_array:
            years_array.append(refill_date.year)

    await call.message.answer("Выберите год из списка:", reply_markup=money_by_years(years_array))


@dp.callback_query_handler(text_startswith="year:", state="*")
async def call_money_by_month(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug("could not delete message", exc_info=True)

    year = call.data.split(':')[1]
    state_data = await state.get_data()
    refills_list = state_data['refills']

    months_array = []
    for refill in refills_list:
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
        logger.debug("could not delete message", exc_info=True)

    month = call.data.split(':')[1]
    state_data = await state.get_data()
    refills_list = state_data['refills']
    months_array = state_data['months']

    total_month_money = 0
    total_money = 0
    days = []
    amounts = []

    year = state_data.get('year')

    for refill in refills_list:
        refill_date = datetime.strptime(refill['date'], "%d.%m.%Y %H:%M:%S")
        if refill_date.month == int(month) and refill_date.year == int(year):
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
