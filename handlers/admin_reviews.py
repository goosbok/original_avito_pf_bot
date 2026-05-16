import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from data.loader import dp, bot
from data.config import services
from utils.sqlite3 import (
    get_order_reviews, get_order_delreviews,
    all_orders_reviews, all_orders_delreviews,
    user_orders_all_reviews, user_orders_all_delreviews,
    edit_order_reviews, edit_order_delreviews,
    get_setting, get_string, get_report_exclude,
)
from utils.other import get_user_string_without_first_name, format_decimal
from design import (
    magic_report, reviews_array, del_reviews_array,
    sheet_complete,
)
from keyboards.inline_keyboards import (
    reviews_man_kb, show_admin_review_by_index,
    admin_back_kb, gsheets_url,
)
from utils.googlesheets import create_reviews_report
from .admin_base import find_user

logger = logging.getLogger(__name__)


class reviews(StatesGroup):
    user = State()
    close = State()


class del_reviews(StatesGroup):
    user = State()
    close = State()


###############################################################################################
#############################             Отзывы               ################################
###############################################################################################

@dp.callback_query_handler(text="reviews_man", state="*")
async def call_reviews_man(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    all_orders = all_orders_reviews()

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
        logger.debug("could not delete message")

    await call.message.answer(magic_report)
    await reviews.user.set()


@dp.message_handler(state=reviews.user)
async def user_all_reviews(message: types.Message, state: FSMContext):
    try:
        rev_arr = []
        user = await find_user(message.text)
        if not user:
            await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
        orders = user_orders_all_reviews(user['id'])
        if not orders:
            await message.answer("⚠️ У пользователя нет заказов на отзывы.", reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
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
            else:
                status = order['status']
            f_price = format_decimal(order['price'])
            STR = STR.format(order['increment'], f_price, usr_str, service, status, order['date'], order['link'])
            rev_arr.append(STR)

        await message.answer(rev_arr[-1], reply_markup=show_admin_review_by_index(len(orders)-1, len(orders)))
        await state.update_data(orders=orders, array=rev_arr)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка получения заказов пользователя!\n{e}", reply_markup=admin_back_kb('reviews_man'))
        await state.finish()


@dp.callback_query_handler(text_startswith="review:", state="*")
async def admin_call_show_review_by_index(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug("could not delete message", exc_info=True)
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
        logger.debug("could not delete message")
    state_data = await state.get_data()
    orders = state_data['orders']
    orders_array = state_data['array']
    if orders:
        orders_array = reviews_array(orders)
        for order in orders_array:
            await call.message.answer(order)
        await call.message.answer("Выберите действие:", reply_markup=admin_back_kb('reviews_man'))
    else:
        await call.message.answer("⚠️ Ошибка получения заказов пользователя!", reply_markup=admin_back_kb('reviews_man'))


@dp.callback_query_handler(text="reviw_close", state="*")
async def admin_call_review_close(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    await call.message.answer("⚙️ Введите номер заказа:")
    await reviews.close.set()


@dp.message_handler(state=reviews.close)
async def review_close(message: types.Message, state: FSMContext):
    from utils.sqlite3 import get_tg_id_for_user
    try:
        review = get_order_reviews(message.text)
        if not review:
            await message.answer(f'⚠️ Заказ {message.text} не найден!', reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
        if review['status'] == 'Posted':
            edit_order_reviews('Completed', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('reviews_man'))
            tg_id = get_tg_id_for_user(review['user_id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"<b>🎉 Ваш заказ номер {review['increment']} на сервисе {review['service']} успешно выполнен!</b>")
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f'⚠️ Ошибка получения заказа\n{e}', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()


@dp.callback_query_handler(text="reviews_sheet", state="*")
async def admin_call_reviews_gsheets(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
    orders = all_orders_reviews()
    STICKER = get_setting('wait_sticker')
    msg = await call.message.answer("Идет генерация отчета.")
    stick = await call.message.answer_sticker(STICKER) if STICKER else None
    try:
        report_url = create_reviews_report(orders)
        await call.message.answer(sheet_complete, reply_markup=gsheets_url(report_url))
    except Exception:
        logger.exception('googlesheets: failed to create reviews report')
        await call.message.answer("⚠️ Ошибка при генерации отчета!", reply_markup=admin_back_kb('reviews_man'))
    finally:
        try:
            await bot.delete_message(chat_id=call.message.chat.id, message_id=msg.message_id)
            if stick:
                await bot.delete_message(chat_id=call.message.chat.id, message_id=stick.message_id)
        except:
            pass


@dp.callback_query_handler(text="del_rev_user_search", state='*')
async def call_del_rev_user_search(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

    await call.message.answer(magic_report)
    await del_reviews.user.set()


@dp.message_handler(state=del_reviews.user)
async def del_reviews_search(message: types.Message, state: FSMContext):
    try:
        user = await find_user(message.text)
        if not user:
            await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
        orders = user_orders_all_delreviews(user['id'])
        if not orders:
            await message.answer("⚠️ У пользователя нет заказов на удаление отзывов.", reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
        rev_arr = del_reviews_array(orders=orders)
        await message.answer(rev_arr[-1], reply_markup=show_admin_review_by_index(len(orders)-1, len(orders)))
        await state.update_data(orders=orders, array=rev_arr)
    except Exception as e:
        from design import main_menu
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
        logger.debug("could not delete message")
    await call.message.answer("⚙️ Введите номер заказа:")
    await del_reviews.close.set()


@dp.message_handler(state=del_reviews.close)
async def del_review_close(message: types.Message, state: FSMContext):
    from utils.sqlite3 import get_tg_id_for_user
    try:
        del_review = get_order_delreviews(message.text)
        if not del_review:
            await message.answer(f'⚠️ Заказ {message.text} не найден!', reply_markup=admin_back_kb('reviews_man'))
            await state.finish()
            return
        if del_review['status'] == 'Posted':
            edit_order_delreviews('Completed', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('reviews_man'))
            tg_id = get_tg_id_for_user(del_review['user_id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"<b>🎉 Ваш заказ на удаление негативного отзыва номер {del_review['increment']} на сервисе {del_review['service']} успешно выполнен!</b>")
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f'⚠️ Ошибка получения заказа\n{e}', reply_markup=admin_back_kb('reviews_man'))
        await state.finish()
