import logging
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp
from keyboards.users_menu import get_menu_kb, menu_btn_kb
from utils.other import (
    get_user_string_without_first_name,
    format_decimal,
)
from utils.sender import send_admins
from utils.sqlite3 import (
    get_user,
    get_string,
    get_balancik, add_balance,
    get_promocode, activate_promocode, update_promocode,
)

logger = logging.getLogger(__name__)
logger.info("promocodes.py loaded — registering handlers")


class FSMToken(StatesGroup):
    promik = State()


@dp.callback_query_handler(text="user:promo", state='*')
async def user_promo(call: CallbackQuery, state: FSMContext):
    logger.info("user:promo callback: tg_id=%s", call.from_user.id)
    await state.finish()
    STR = get_string('str_input_promo')
    await call.message.answer(STR, reply_markup=menu_btn_kb())
    await FSMToken.promik.set()
    try:
        await call.message.delete()
    except Exception:
        logger.debug("user:promo: could not delete message")


@dp.message_handler(state=FSMToken.promik)
async def promik(message: types.Message, state: FSMContext, user_id: int):
    code = message.text
    promocode = get_promocode(code=code)
    await state.finish()
    if promocode:
        if promocode['isactivated'] == 0:
            activate_promocode(code)
            balance = get_balancik(user_id)
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
                balance = get_balancik(user_id)
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
                    balance = get_balancik(user_id)
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
            logger.warning("promik: unknown isactivated=%s for code=%s user=%s", promocode['isactivated'], code, user_id)
    else:
        STR = get_string('str_promo_bad')
        await message.answer(STR, reply_markup=get_menu_kb())
        logger.warning("promik: code not found in db code=%s user=%s", code, user_id)
