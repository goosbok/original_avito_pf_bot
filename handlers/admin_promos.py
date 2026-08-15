import logging

from aiogram import types
from aiogram.dispatcher import FSMContext

from data.loader import dp, bot
from utils.sqlite3 import (
    add_promocode, all_promocodes, get_promocode, update_promocode, del_promo,
)
from keyboards.inline_keyboards import promo_codes_kb, admin_back_kb
from .admin_base import Admin, generate_random_string

logger = logging.getLogger(__name__)


@dp.callback_query_handler(text="promo_codes", state='*')
async def promo_codes(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await state.update_data(page=call.data)
    user_id = call.from_user.id
    await bot.send_message(chat_id=user_id, text="⚙️ Управление промокодами:", reply_markup=promo_codes_kb())
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")


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
        logger.debug("could not delete message")
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
        logger.debug("could not delete message")
    all_promo = all_promocodes()
    if not all_promo:
        await call.message.answer("⚠️ Промокодов нет.", reply_markup=admin_back_kb(page))
        return
    prm = '\n'.join(['❎' if promo['isactivated'] == 1 else '✅' + f"<code>{promo['code']}</code> цена: {promo['price']} руб." for promo in all_promo])
    await call.message.answer(prm, reply_markup=admin_back_kb(page))


@dp.callback_query_handler(text="deactiv_promo")
async def del_promik(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")
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
        logger.debug("could not delete message")
    all_promo = all_promocodes()
    for code in all_promo:
        if code['isactivated'] == 1:
            del_promo(code['code'])

    all_promo = all_promocodes()
    await call.message.answer("✅Активированные промокоды удалены!")
    if not all_promo:
        await call.message.answer("⚠️ Промокодов нет.", reply_markup=admin_back_kb(page))
        return
    prm = '\n'.join(['❎' if promo['isactivated'] == 1 else '✅' + f"<code>{promo['code']}</code> цена: {promo['price']} руб." for promo in all_promo])
    await call.message.answer(prm, reply_markup=admin_back_kb(page))


@dp.callback_query_handler(text="add_custom_promo")
async def call_add_custom_promo(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except:
        logger.debug("could not delete message")

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
        return
    promocode_data = await state.get_data()
    code = promocode_data['new_prom']
    if add_promocode(code, int(price)):
        await message.answer(f"✅Успешно добавлен промокод <code>{code}</code>, стоимостью <b>{price} руб.</b>", reply_markup=admin_back_kb(page))
        promocode = get_promocode(code=code)
        update_promocode(increment=promocode['increment'], isactivated=2)
    else:
        await message.answer("❎Ошибка добавления промокода!", reply_markup=admin_back_kb(page))
    await state.finish()
