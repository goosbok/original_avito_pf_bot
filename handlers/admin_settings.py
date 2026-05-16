import logging
import io
import asyncio
import queue
import threading
import time
import string
import math
from datetime import timedelta, datetime

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.dispatcher.filters.state import State, StatesGroup

from data import config
from data.config import services
from data.loader import dp, bot

from utils.sqlite3 import (
    get_string, get_setting, get_price,
    get_setting_from_base, get_string_from_base,
    get_all_strings, get_all_settings,
    add_string_to_base, add_setting_to_base,
    edit_string, edit_setting,
    edit_price,
    get_admins, add_admin, del_admin,
    get_spam_exclude, add_spam_exclude,
    get_report_exclude, add_report_exclude,
    all_orders, get_tg_id_for_user,
)

from utils.other import (
    format_decimal, str2bool, split_messages, declension_review,
    get_user_string_without_first_name,
)
from keyboards.inline_keyboards import (
    setup_kb, setup_variables_kb, setup_strings_kb,
    str_visual_edit_kb, btn_visual_edit_kb,
    payment_setup_kb, payment_methods_admin_kb,
    setup_admins, del_admin_kb,
    admin_back_kb,
    edit_price_kb,
)
from .admin_base import find_user

logger = logging.getLogger(__name__)


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


###############################################################################################
#############################           Настройки              ################################
###############################################################################################

#Настройки
@dp.callback_query_handler(text="settings", state="*")
async def admin_call_settings(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer("⚙️ Вы в пункте \"Настройки\". Выбирите вариант:", reply_markup=setup_kb())

#Касса/цены
@dp.callback_query_handler(text="price_setup", state="*")
async def admin_call_price_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    pay_work = str2bool(get_setting('payment_work'))
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
        logger.debug("could not delete message")
    pay_work = str2bool(get_setting('payment_work'))
    if pay_work:
       STR = "Касса сейчас работает. Отключаем?"
    else:
       STR = "Касса сейчас отключена. Включить?"
    await call.message.answer(text=STR, reply_markup=payment_setup_kb(str(not pay_work)))


@dp.callback_query_handler(text="payment_methods_setup", state="*")
async def admin_call_payment_methods_setup(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer(
        "💳 Способы оплаты:",
        reply_markup=payment_methods_admin_kb()
    )


@dp.callback_query_handler(text_startswith="payment_method_toggle:", state="*")
async def admin_call_payment_method_toggle(call: types.CallbackQuery, state: FSMContext):
    from services.payment_methods import set_enabled, is_enabled
    method = call.data.split(":")[1]
    currently_enabled = is_enabled(method)
    try:
        set_enabled(method, not currently_enabled)
    except ValueError as e:
        await call.answer(str(e), show_alert=True)
        return
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer(
        "💳 Способы оплаты:",
        reply_markup=payment_methods_admin_kb()
    )


#Интерфейс
@dp.callback_query_handler(text="interface_setup", state="*")
async def admin_call_interface_setup(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer(text="⚙️ Вы в пункте \"Интерфейс\". Выбирите вариант:", reply_markup=setup_strings_kb())

def _captions_array():
    return [s for s in get_all_strings() if 'str_' in s['parametr']]


def _btn_array():
    return [s for s in get_all_strings() if 'btn_' in s['parametr']]


#Визуальный редактор строк
@dp.callback_query_handler(text="str_visual_edit", state="*")
async def admin_call_str_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    captions_array = _captions_array()
    if not captions_array:
        await call.message.answer("⚠️ Нет сохранённых строк для редактирования. Сначала добавьте строку через «Переменные».", reply_markup=admin_back_kb('interface_setup'))
        return
    await call.message.answer(f"Страница 1 из {len(captions_array)}\n{captions_array[0]['value']}", reply_markup=str_visual_edit_kb(0, len(captions_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="caption:", state="*")
async def admin_call_str_visual_edit_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    index = int(call.data.split(":")[1])
    captions_array = _captions_array()
    if not captions_array or index >= len(captions_array):
        await call.message.answer("⚠️ Список строк пуст или индекс вне диапазона.", reply_markup=admin_back_kb('interface_setup'))
        return
    await call.message.answer(f"Страница {index+1} из {len(captions_array)}\n{captions_array[index]['value']}", reply_markup=str_visual_edit_kb(index, len(captions_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="edit:", state="*")
async def admin_call_str_visual_edit_param(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    index = int(call.data.split(":")[1])
    await state.update_data(index=index)
    await call.message.answer("Введите новое значение:")
    await setup_class.string_edit.set()

@dp.message_handler(state=setup_class.string_edit)
async def str_edit_value(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    index = state_data['index']
    # Must use the *filtered* captions array — the keyboard's index references
    # captions_array, not the full strings table.
    captions_array = _captions_array()
    if not captions_array or index >= len(captions_array):
        await message.answer("⚠️ Не удалось определить редактируемую строку.", reply_markup=admin_back_kb('interface_setup'))
        await state.finish()
        return
    select_string = captions_array[index]
    edit_string(select_string['parametr'], message.text)
    await message.answer("Строка успешно изменена!", reply_markup=admin_back_kb(f'caption:{index}'))
    await state.finish()

#Визуальный редактор кнопок
@dp.callback_query_handler(text="btn_visual_edit", state="*")
async def admin_call_btn_visual_edit(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    btn_array = _btn_array()
    if not btn_array:
        await call.message.answer("⚠️ Нет сохранённых кнопок для редактирования. Сначала добавьте кнопку через «Переменные».", reply_markup=admin_back_kb('interface_setup'))
        return
    await call.message.answer(f"Страница 1 из {len(btn_array)}\n{btn_array[0]['value']}", reply_markup=btn_visual_edit_kb(0, len(btn_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="btn:", state="*")
async def admin_call_btn_visual_edit_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    index = int(call.data.split(":")[1])
    btn_array = _btn_array()
    if not btn_array or index >= len(btn_array):
        await call.message.answer("⚠️ Список кнопок пуст или индекс вне диапазона.", reply_markup=admin_back_kb('interface_setup'))
        return
    await call.message.answer(f"Страница {index+1} из {len(btn_array)}\n{btn_array[index]['value']}", reply_markup=btn_visual_edit_kb(index, len(btn_array), 'interface_setup'))

@dp.callback_query_handler(text_startswith="btn_edit:", state="*")
async def admin_call_btn_visual_edit_param(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    index = int(call.data.split(":")[1])
    await state.update_data(index=index)
    await call.message.answer("Введите новое значение:")
    await setup_class.btn_edit.set()

@dp.message_handler(state=setup_class.btn_edit)
async def btn_edit_value(message: types.Message, state: FSMContext):
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
        logger.debug("could not delete message")
    await call.message.answer('Меню \"Переменные\". Выберите действие:', reply_markup=setup_variables_kb())

#Посмотреть переменную
@dp.callback_query_handler(text="str_variable_view", state="*")
async def admin_call_str_variable_view(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    settings = get_all_strings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range(len(settings)):
        if i < len(settings):
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}\n"
        else:
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}"

    if len(STR) < 4096:
        await call.message.answer(STR)
    else:
        MSG = STR.split("\n")
        MSG_PARTS = split_messages(MSG, "\n")
        for i in range(len(MSG_PARTS)):
            await call.message.answer(MSG_PARTS[i])
    await setup_class.str_variable_view.set()

#Добавить переменную
@dp.callback_query_handler(text="str_variable_add", state="*")
async def admin_call_str_variable_add(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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
        logger.debug("could not delete message")
    settings = get_all_strings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range(len(settings)):
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
        logger.debug("could not delete message")
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
        logger.debug("could not delete message")
    settings = get_all_settings()
    STR = "✏️ Введите переменную, которую хотите посмотреть:\n"
    for i in range(len(settings)):
        if i < len(settings):
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}\n"
        else:
            STR += f"<code>{settings[i]['parametr']}</code>\n{settings[i]['description']}"

    if len(STR) < 4096:
        await call.message.answer(STR)
    else:
        MSG = STR.split("\n")
        MSG_PARTS = split_messages(MSG, "\n")
        for i in range(len(MSG_PARTS)):
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
        logger.debug("could not delete message")
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
        logger.debug("could not delete message")
    await call.message.answer(text="👑 Управление админами:", reply_markup=setup_admins())

@dp.callback_query_handler(text_startswith="admin:", state="*")
async def admin_call_add_del_admins(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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
        user_id_str = message.text.strip()
        if user_id_str.isdigit():
            add_admin(user_id_str)
            await message.answer(f'✅ Пользователь с ID {user_id_str} стал админом!', reply_markup=admin_back_kb("admins_setup"))
        else:
            user = await find_user(user_id_str)
            if user:
                usr_str = await get_user_string_without_first_name(user)
                # Admins are keyed by TG ID; resolve internal ID → TG ID.
                tg_id = get_tg_id_for_user(user['id'])
                add_admin(str(tg_id) if tg_id else str(user['id']))
                await message.answer(f'✅ Пользователь {usr_str} стал админом!', reply_markup=admin_back_kb("admins_setup"))
            else:
                await message.answer(f'⚠️ Пользователь {user_id_str} не найден в базе. Введите ID нового пользователя!')
                await setup_class.set_admin.set()
    else:
        await message.answer('⚠️ Некорректное действие. Пожалуйста, попробуйте еще раз.')

@dp.callback_query_handler(text_startswith="del_admin:", state="*")
async def admin_call_del_admin_by_id(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    id_to_del = call.data.split(':')[1]
    del_admin(id_to_del)
    await call.message.answer('❎ Пользователь удален из админов!', reply_markup=admin_back_kb("admins_setup"))

#Исключения.
@dp.callback_query_handler(text="spam_exclude", state="*")
async def admin_call_spam_exclude(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer('👑 Введите ID или ник пользователя, которого хотите исключить из рассылки:', reply_markup=admin_back_kb("admins_setup"))
    await setup_class.spam_exclude.set()

@dp.message_handler(state=setup_class.spam_exclude)
async def admin_add_spam_exclude(message: types.Message, state: FSMContext):
    user_id_str = message.text.strip()
    if user_id_str.isdigit():
        add_spam_exclude(user_id_str)
        await message.answer(f'✅ Пользователь с ID {user_id_str} исключен из рассылки!', reply_markup=admin_back_kb("admins_setup"))
    else:
        user = await find_user(user_id_str)
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
        logger.debug("could not delete message")
    await call.message.answer('👑 Введите ID или ник пользователя, которого хотите исключить из отчетов:', reply_markup=admin_back_kb("admins_setup"))
    await setup_class.report_exclude.set()

@dp.message_handler(state=setup_class.report_exclude)
async def admin_add_report_exclude(message: types.Message, state: FSMContext):
    user_id_str = message.text.strip()
    if user_id_str.isdigit():
        add_report_exclude(user_id_str)
        await message.answer(f'✅ Пользователь с ID {user_id_str} исключен из отчетов!', reply_markup=admin_back_kb("admins_setup"))
    else:
        user = await find_user(user_id_str)
        if user:
            usr_str = await get_user_string_without_first_name(user)
            add_report_exclude(str(user['id']))
            await message.answer(f'✅ Пользователь {usr_str} исключен из отчетов!', reply_markup=admin_back_kb("admins_setup"))
        else:
            await message.answer(f'⚠️ Пользователь {user_id_str} не найден в базе. Введите ID нового пользователя!')
            await setup_class.report_exclude.set()

###############################################################################################
#############################              Прайс               ################################
###############################################################################################

#Редактирование прайса
@dp.callback_query_handler(text_startswith="price_edit:", state="*")
async def admin_call_price_edit_service(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    service = call.data.split(':')[1]
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    price = get_price(f"price_{service}")

    await state.update_data(service=service, price=price)

    if service == "avito_pf" or service == "seo" or service == 'avito_del_review':
        await call.message.answer(f"Актуальная цена {price} ₽. Введите новое значение в ₽:")
        await setup_class.price_edit.set()
    else:
        await call.message.answer(f"Прайс для сервиса \"Отзывы {services[service]}\":", reply_markup=edit_price_kb(service, price, 3))


@dp.callback_query_handler(text_startswith="edit_price-", state="*")
async def admin_call_edit_price_function(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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


#Минимальный платеж
@dp.callback_query_handler(text="min_amount", state="*")
async def admin_call_min_amount(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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

###############################################################################################
#############################        Прогрес-бар (inDevel)     ################################
###############################################################################################

def long_function(q):
    orders = all_orders()
    n = 0
    percents = 0
    for order in orders:
        n += 1
        percents = n / len(orders) * 10
        q.put_nowait(int(percents))


@dp.message_handler(commands=['start_progress'])
async def start_progress(message: types.Message, state: FSMContext):
    await message.answer("Запуск длительной операции...")
    await state.set_state(ProgressStates.progress.state)

    qe = queue.Queue()
    t = threading.Thread(target=long_function, args=[qe])
    t.start()

    total_steps = 10
    msg = await message.answer('[                    ] начинаем.')
    while t.is_alive():
        n = qe.get()
        progress_bar = '[' + '◼️' * int(n) + '  ' * (total_steps - n) + ']'
        await bot.edit_message_text(f'{progress_bar} {n * 10}% завершено.', chat_id=message.chat.id, message_id=msg.message_id)

    await message.answer("Операция завершена!")
    await state.finish()

@dp.message_handler(commands=['globals'])
async def globals_handler(message: types.Message, state: FSMContext):
    await message.answer(str(globals()))
