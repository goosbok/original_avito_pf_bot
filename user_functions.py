import colorama
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.types import InputMediaVideo
from aiogram.utils.markdown import hlink
from aiogram import types
#from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, IDFilter
from aiogram.dispatcher.filters.state import State, StatesGroup

from data import config
from data.config import price_google, price_yandex, price_vk, price_flamp, price_2gis, price_avito, services
from handlers.admin_functions import get_user_string_without_first_name, get_user_string_with_first_name
from data.loader import dp, bot
from keyboards.inline_keyboards import *
from utils.other_functions import send_admins
from utils.sqlite3 import get_user, add_refill, user_orders_all, add_order, get_order, update_user, get_users_last_order, delete_user, get_refill

from handlers.admin_functions import *
#from handlers.robokassa import *
from utils.yookassa_refil import create_invoice, check_payment_status
import asyncio

class FSMToken(StatesGroup):
    promik = State()

class avito(StatesGroup):
    delete_review = State()

def str2bool(value):
  return value.lower() in ("yes", "true", "1")

###Добавлено
@dp.message_handler(commands="id")
async def cmd_id(message: types.Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")

@dp.message_handler(commands="delme")
async def cmd_delme(message: types.Message):
    user_id = message.from_user.id
    try:
        delete_user(id=user_id)
        await message.answer(f"Пользователь с <b>ID {user_id}</b> удален!")
    except Exception as e:
        print(f"{colorama.Fore.RED}Error:{colorama.Fore.RESET}\n{e}")

@dp.message_handler(commands="cancel", state="*")
@dp.message_handler(Text(equals="отмена", ignore_case=True), state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Действие отменено", reply_markup=types.ReplyKeyboardRemove())
###/Добавлено


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
        await call.message.answer(tasks_text, reply_markup=get_menu_kb())
    elif text == 'qna':
        await call.message.answer(qna_text, reply_markup=qna_kb())
    elif text == 'rules':
        await call.message.answer(rules_text, reply_markup=get_menu_kb())
    elif text == 'start':
        button = InlineKeyboardButton(
            text="🎥Видео инструкция",
            #url='https://youtu.be/PY7aPa8-H7Q'
            callback_data="how_to"
        )
        keyboard = get_menu_kb()
        keyboard["inline_keyboard"].insert(0, [button])
        await call.message.answer(how_to_start_text, reply_markup=keyboard)
    elif text == 'support':
        await call.message.answer(suppport_text, reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="qna:", state='*')
async def info(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    q = data[1]
    if q == '1':
        await call.message.answer(q1_text, reply_markup=qna_kb())
    elif q == '2':
        await call.message.answer(q2_text, reply_markup=qna_kb())
    elif q == '3':
        await call.message.answer(q3_text, reply_markup=qna_kb())
    elif q == '4':
        await call.message.answer(q4_text, reply_markup=qna_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")


@dp.callback_query_handler(text_startswith="user:", state='*')
async def user(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    action = data[1]
    if action == 'profile':
        await call.message.answer("Личный кабинет:", reply_markup=profile_kb())
    elif action == 'tarif':
        await call.message.answer(tarifs_text, reply_markup=tarifs_kb())
    elif action == 'promo':
        await call.message.answer("Введите промокод:", reply_markup=menu_btn_kb())
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

            await message.answer(f"<b>✅ Промокод на {promocode['price']}₽ успешно активирован!\n\n💰 Ваш новый баланс {balance}</b>", reply_markup=get_menu_kb())

            for admin in ADMINS:
                try:
                    await bot.send_message(admin,
                                    f"<b>🐼 Промокод <code>{code}</code> активировал пользователь <a href='tg://user?id={user_id}'>{user_id}</a> (@{user.username})!\n\n💰 Его новый баланс {balance}</b>", parse_mode="html")
                except Exception as e:
                    print(f"Error sending message:\n{e}")

        elif promocode['isactivated'] == 1:
            await message.answer(f"<b>❌ Промокод уже активирован!</b>", reply_markup=get_menu_kb())
        elif promocode['isactivated'] == 2:
            users_str = ""
            if not promocode['prom_users']:
                users_str = user_id
                update_promocode(increment=promocode['increment'], prom_users=users_str)
                balance = get_balancik(message.from_user.id)
                balance = balance + int(promocode['price'])
                add_balance(balance, user_id)

                await message.answer(f"<b>✅Промокод на {promocode['price']}₽ успешно активирован!\n\n💰 Ваш новый баланс {balance}</b>", reply_markup=get_menu_kb())

                for admin in ADMINS:
                    try:
                        await bot.send_message(admin,
                                        f"<b>🐼 Промокод <code>{code}</code> активировал пользователь <a href='tg://user?id={user_id}'>{user_id}</a> (@{user.username})!\n\n💰 Его новый баланс {balance}</b>", parse_mode="html")
                    except Exception as e:
                        print(f"Error sending message:\n{e}")
            else:
                users_array = promocode['prom_users'].split(",")

                if str(user_id) not in users_array:
                    users_array.append(str(user_id))
                    users_str = ','.join(users_array)

                    update_promocode(increment=promocode['increment'], prom_users=users_str)
                    balance = get_balancik(message.from_user.id)
                    balance = balance + int(promocode['price'])
                    add_balance(balance, user_id)

                    await message.answer(f"<b>✅Промокод на {promocode['price']}₽ успешно активирован!\n\n💰 Ваш новый баланс {balance}</b>", reply_markup=get_menu_kb())

                    for admin in ADMINS:
                        try:
                            await bot.send_message(admin,
                                            f"<b>🐼 Промокод <code>{code}</code> активировал пользователь <a href='tg://user?id={user_id}'>{user_id}</a> (@{user.username})!\n\n💰 Его новый баланс {balance}</b>", parse_mode="html")
                        except Exception as e:
                            print(f"Error sending message:\n{e}")
                else:
                    await message.answer(f"⚠️Вы уже активировали промокод <b>{code}</b>!", reply_markup=get_menu_kb())
        else:
            print("Не успешно: значение найдено в таблице promocodes, но неизвестное состояние isactivated.")
    else:
        await message.answer("<b>❌ Промокод не найден!</b>", reply_markup=get_menu_kb())
        print("Не успешно: значение не найдено в таблице promocodes.")

@dp.callback_query_handler(text_startswith="profile:", state='*')
async def profile(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    action = data[1]
    if action == 'show_bal':
        user = get_user(id=call.from_user.id)
        await call.message.answer(show_bal_text(user['balance']), reply_markup=profile_kb())
    elif action == 'ref_bal':
        await state.set_state("refill_balance")
        await call.message.answer(refill_balance_text, reply_markup=menu_btn_kb())
    elif action == 'listord':
        try:
            orders = user_orders_all(call.from_user.id)
            orders_array = listord_array(orders)
            await call.message.answer(f"Страница 1 из {len(orders)}\n{orders_array[0]}", reply_markup=show_user_order_by_index(len(orders)-1, len(orders)))
        except Exception as e:
            await call.message.answer(f"⚠️ Ошибка!\n{e}", reply_markup=user_back_kb('users_man'))
    elif action == 'ordstatus':
        await state.set_state("check_order")
        await call.message.answer("Введите номер заказа", reply_markup=menu_btn_kb())
    elif action == 'getref':
        await call.message.answer(get_ref_text(call.from_user.id), reply_markup=menu_btn_kb())

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
    try:
        index = int(call.data.split(":")[1])
        orders = user_orders_all(call.from_user.id)
        orders_array = listord_array(orders)
        await call.message.answer(f"Страница {index+1} из {len(orders)}\n{orders_array[index]}", reply_markup=show_user_order_by_index(index, len(orders)))
    except Exception as e:
        await call.message.answer_sticker('CAACAgIAAxkBAAKsKWZiGSMCSvVs8Fxo5jM0pmfuxIMAA9M4AAL9VolLYmPxna-48Sk1BA')
        await call.message.answer("⚠️ Ошибка:\n{e}")

@dp.callback_query_handler(text="user_show_all_orders", state="*")
async def user_call_show_all_orders(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print('Error deleting message!')

    orders = user_orders_all(call.from_user.id)
    if orders:
        orders_array = listord_array(orders)
        await call.message.answer_sticker('CAACAgIAAxkBAAKsRmZiHByCAAGHv2QnvB5WC0gOcM2S6QACdEIAAucOkEtX70Rr-qnYCDUE')
        for order in orders_array:
            await call.message.answer(order)
    else:
        await call.message.answer_sticker('CAACAgIAAxkBAAKsTGZiHN5_OkQDOquJfFQslnkHwYavAAIwOQACTbCJS_QvdBkhGwOcNQQ')
        await call.message.answer("⚠️ Ошибка получения заказов пользователя!")

@dp.callback_query_handler(text_startswith="tarifs:", state='*')
async def tarif(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    tarif = data[1]
    if tarif == "pf":
        image = f"images/avito_pf.jpg"
        with open(image, 'rb') as photo:
            await call.message.answer_photo(photo=photo, caption="Выберите вариант:", reply_markup=pf_kb())
    if tarif == "reviews":
        await call.message.answer("""Делаем с гарантией 100% ! Если после оставления отзыв - у вас его удалила по любым причинам, то если напишите нам в поддержку - незамедлительно получите новый !""")

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="pf:", state='*')
async def pf(call: CallbackQuery, state: FSMContext):
    await state.finish()
    data = call.data.split(":")
    tarif = data[1]
    if tarif == 'day':
        await call.message.answer(pf_day_text, reply_markup=pf_day_kb())
    elif tarif == 'week':
        await call.message.answer(pf_week_text, reply_markup=pf_week_kb())
    elif tarif == 'month':
        await call.message.answer(pf_month_text, reply_markup=pf_month_kb())
    elif "day-" in tarif:
        async with state.proxy() as data:
            print(data)
            data['fix'] = call.data.split("-")[1]
            data['period'] = "одним днём"
            data['count'] = config.prices[tarif]
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix)
        await state.set_state("place_order")
        await call.message.answer(pf_links, reply_markup=menu_btn_kb())
    elif "week-" in tarif:
        async with state.proxy() as data:
            data['fix'] = call.data.split("-")[1]
            data['period'] = "на неделю"
            data['count'] = config.prices[tarif]
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * 7)
        await state.set_state("place_order")
        await call.message.answer(pf_links, reply_markup=menu_btn_kb())
    elif "month-" in tarif:
        async with state.proxy() as data:
            data['fix'] = call.data.split("-")[1]
            data['period'] = "на месяц"
            data['count'] = config.prices[tarif]
            count = int(data['count'])
            fix = float(data['fix'])
            data['total_price'] = int(count * fix * 30)
        await state.set_state("place_order")
        await call.message.answer(pf_links, reply_markup=menu_btn_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.message_handler(text_startswith="http", state='place_order')
async def place_order(message: Message, state: FSMContext):
    links = message.text.split('\n')
    async with state.proxy() as data:
        data['links'] = links
        data['total_price'] *= len(links)
    await state.set_state("order_checkout")
    msg = await message.answer("Накручиваем запросы контактов?", reply_markup=yes_no_contact_kb())
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="contact:", state='*')
async def order_contact_set(call: CallbackQuery, state: FSMContext):
    answer = str2bool(call.data.split(":")[1])

    async with state.proxy() as data:
        data['contact'] = answer
    if 'total_price' in data:
        await call.message.answer(f"Подтвердите списание {data['total_price']} руб.", reply_markup=yes_no_order_kb())
        await call.message.delete()
    else:
        await call.message.answer_sticker('CAACAgIAAxkBAAKsKWZiGSMCSvVs8Fxo5jM0pmfuxIMAA9M4AAL9VolLYmPxna-48Sk1BA')
        await call.message.answer("⚠️ Произошла ошибка! Попробуйте еще раз!", reply_markup=get_menu_kb())

@dp.callback_query_handler(text="order_confirm", state='*')
async def confirm_order(call: CallbackQuery, state: FSMContext):
    user = get_user(id=call.from_user.id)
    async with state.proxy() as data:
        if user['balance'] >= data['total_price']:
            update_user(id=user['id'], balance=user['balance']-data['total_price'])
            add_order(user_id=user['id'],
                      price=data['total_price'],
                      position_name=f"ПФ {data['period']} - {data['fix']}",
                      status="Размещён",
                      links=str(data['links']).replace(']','').replace('[',''),
                      contacts=data['contact'])
            # TODO: Сделать админу эксель-табличку
            await send_admins(new_order_text(get_users_last_order(user['id'])))
            await call.message.answer(f"✅ Заказ успешно размещён!\n🧊 Номер заказа: <code>{get_users_last_order(user['id'])['increment']}</code>",
                                      reply_markup=get_menu_kb())
        else:
            await state.reset_data()
            await call.message.answer("Недостаточно средств!", reply_markup=get_menu_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text_startswith="menu", state='*')
async def to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.answer("Выберите действие", reply_markup=get_menu_kb())

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
            msg = await message.answer(order_status_txt(order['increment'], order['status']),
                                       reply_markup=menu_btn_kb())
        else:
            msg = await message.answer("Это не Ваш заказ", reply_markup=menu_btn_kb())
    except TypeError:
        msg = await message.answer(nosuchorder, reply_markup=menu_btn_kb())

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
    except:
        print("Error deleting message!")


@dp.message_handler(lambda message: message.text.isdigit(), state="refill_balance")
async def refill(message: Message, state: FSMContext):
    amount = int(message.text)
    if amount < 1:
        await state.finish()
        msg = await message.answer(moremoney, reply_markup=menu_btn_kb())
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        except:
            print("Error deleting message!")
    else:
        await message.answer_sticker("CAACAgIAAxkBAAKsC2ZiFkw2x6LCIMANpdUYdwFmX6XnAAIuQQACL3WRSy5s2sn5ZuS8NQQ")
        msg = await message.answer(f"Пополняем баланс на {amount} руб.?", reply_markup=yes_no_kb())
        async with state.proxy() as data:
            data['price'] = amount
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        #await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 2)
    except:
        print("Error deleting message!")

# Ваш обработчик для кнопки "Оплатить подписку навсегда"
@dp.callback_query_handler(text_startswith="refil:confirm", state="refill_balance")
async def refill_balance(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    async with state.proxy() as data:
        amount=data['price']
    # Получаем user_id пользователя, чтобы сгенерировать уникальный URL оплаты
    user_id = call.from_user.id

    is_refill = get_refill(user_id)

    # Генерируем URL оплаты
    payment_url, payment_id = create_invoice(user_id, int(amount))

    # Отправляем сообщение с кнопкой на оплату
    await bot.send_message(chat_id=user_id, text=f"для оплаты <b>{amount}</b> руб. нажмите:", reply_markup=yookassa_kb(int(amount), payment_url))

    success = await check_payment_status(payment_id)
    #success = True

    # Используем callback_query.message.answer вместо message.answer
    if success:
        usr = get_user(id=user_id)
        ref_user=get_user(id=str(usr['ref_id']))
        try:
            update_user(id=user_id, balance=usr['balance'] + int(amount))
            add_refill(int(amount), user_id)
            user_string = await get_user_string_without_first_name(usr)
            await bot.send_message(chat_id=user_id, text=f"Платеж <b>{int(amount)} руб.</b> прошел. Баланс {user_string}: <b>{usr['balance'] + int(amount)} руб.</b>")
            await send_admins(f"Платеж <b>{int(amount)} руб.</b> прошел. Баланс {user_string}: <b>{usr['balance'] + int(amount)} руб.</b>")
            print(f"Юзер {usr['id']}: {usr['user_name']} пополнил баланс на {amount} руб.")
            """
            Начисляем рефу за реферала
            #if usr['balance'] == 0:
            #print(get_refill(user_id))
            """
            if not usr['is_vip']:
                if not is_refill:
                    if ref_user is not None:
                        update_user(id=str(usr['ref_id']), balance=ref_user['balance'] + int(amount * 0.3))
                        add_refill(int(amount * 0.3), usr['ref_id'])
                        await bot.send_message(chat_id=str(usr['ref_id']), text=f"Ваш баланс пополнен на <b>{amount * 0.3}руб.</b> руб и составляет <b>{ref_user['balance'] + int(amount * 0.3)}руб.</b>")
                        ref_user_str = await get_user_string_without_first_name(ref_user)
                        print(f"Юзер {ref_user_str} получил пополнение на {amount * 0.3} руб.")
                    else:
                        print(f"Юзер {usr['id']}: {usr['user_name']} не имет рефера!")
            else:
                ref_user_str = await get_user_string_without_first_name(ref_user)
                print("Реферал пользователя {ref_user_str} пополнил баланс на {amount} руб.")
        except Exception as e:
            await bot.send_message(chat_id=user_id, text=f"⚠️ Ошибка!\n{e}")
    else:
        await bot.send_message(chat_id=user_id, text=f"Платеж не прошел или был отменен, чтобы оплатить подписку попробуйте снова или свяжитесь с админом @{config.support_tag}")

@dp.callback_query_handler(text="reviews", state='*')
async def call_reviews_button(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except exception as e:
        print(f"Error deleting message\n{e}")
    await state.finish()
    #await call.message.answer("На какой площадке хотите опубликовать отзыв?", reply_markup=reviews_kb())
    with open('images/logo_small.jpg', 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption="На какой площадке хотите опубликовать отзыв?", reply_markup=reviews_kb())

@dp.callback_query_handler(text_startswith="reviews:", state="*")
async def call_reviews_service(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except exception as e:
        print(f"Error deleting message\n{e}")
    service = call.data.split(":")[1]

    if service == "vk":
        STR = reviews_vk
        price = price_vk
    elif service == "yandex":
        STR = reviews_yandex
        price = price_yandex
    elif service == "avito":
        STR = reviews_avito
        price = price_avito
    elif service == "2gis":
        STR = reviews_2gis
        price = price_2gis
    elif service == "flamp":
        STR = reviews_flamp
        price = price_flamp
    elif service == "google":
        STR = reviews_google
        price = price_google

    await state.update_data(service=service, price=price)
    image = f"images/review_{service}.jpg"
    with open(image, 'rb') as photo:
        await call.message.answer_photo(photo=photo, caption=STR, reply_markup=reviews_count(service))

@dp.callback_query_handler(text_startswith="rev_price:", state="*")
async def call_reviews_service(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except exception as e:
        print(f"Error deleting message\n{e}")

    param = call.data.split(":")[1]
    state_data = await state.get_data()
    service = services[f"{state_data['service']}"]
    price = state_data['price']
    amount = int(price[param])*int(param)
    await state.update_data(reviews_count=param, amount=amount)

    await call.message.answer_sticker("CAACAgIAAxkBAAEBGddmdJq9_ugDE0dm_I6o5PUn3zBC6AACLkEAAi91kUsubNrJ-WbkvDUE")
    STR = rviews_text(param, service, price[param], amount)
    await call.message.answer(STR, reply_markup=yes_no_reviews())

@dp.callback_query_handler(text="rev_confirm", state='*')
async def call_confirm_review(call: CallbackQuery, state: FSMContext):
    user = get_user(id=call.from_user.id)
    state_data = await state.get_data()
    amount = state_data['amount']
    service = state_data['service']
    if user['balance'] >= int(amount):
        update_user(id=user['id'], balance=user['balance']-int(amount))
        add_order_reviews(user_id=user['id'], price=amount, service=service, status="Размещен")
        await send_admins(new_order_review_text(get_users_last_order_reviews(user['id'])))
        await call.message.answer(f"✅ Заказ успешно размещён!\n🧊 Номер заказа: <code>{get_users_last_order_reviews(user['id'])['increment']}</code>",
                                      reply_markup=get_menu_kb())
    else:
        await state.reset_data()
        await call.message.answer("Недостаточно средств!", reply_markup=get_menu_kb())

    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

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
        await call.message.answer("Выберите действие:", reply_markup=get_menu_kb())
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")

@dp.callback_query_handler(text="avito_del_review", state='*')
async def call_avito_del_review(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        print("Error deleting message!")
    await call.message.answer(delete_review)
    await avito.delete_review.set()

@dp.message_handler(text_startswith="https:", state=avito.delete_review)
async def avito_del_review(message: types.Message, state: FSMContext):
    link = message.text
    user = get_user(id=message.from_user.id)
    amount = 7000
    service = 'avito'
    if user['balance'] >= amount:
        update_user(id=user['id'], balance=user['balance']-int(amount))
        add_order_delreview(user_id=user['id'], price=amount, service=service, link=link, status="Размещен")
        await send_admins(new_order_delreview_text(get_users_last_order_delreviews(user['id'])))
        await message.answer(f"✅ Заказ успешно размещён!\n🧊 Номер заказа: <code>{get_users_last_order_delreviews(user['id'])['increment']}</code>",
                                      reply_markup=get_menu_kb())
    else:
        await state.reset_data()
        await message.answer("Недостаточно средств!", reply_markup=get_menu_kb())