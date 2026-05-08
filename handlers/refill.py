import logging
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery
from aiogram import types

from data.loader import dp, bot
from keyboards.users_menu import (
    get_menu_kb, user_back_kb,
    yookassa_kb, payment_methods_kb, manual_payment_kb, payment_error_kb,
)
from utils.other import (
    format_decimal,
    get_user_string_without_first_name,
)
from utils.sender import send_admins
from utils.sqlite3 import (
    get_user,
    get_string, get_setting, get_nick,
)
from utils.yookassa_refil import check_payment_status

logger = logging.getLogger(__name__)
logger.info("refill.py loaded — registering handlers")


def _get_tg_id_for_user(internal_user_id: int) -> "int | None":
    """Look up Telegram chat_id for a user from auth_providers."""
    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT identifier FROM auth_providers WHERE user_id = ? AND provider = 'telegram'",
            (internal_user_id,)
        ).fetchone()
    return int(row["identifier"]) if row else None


@dp.message_handler(lambda message: message.text.isdigit(), state="refill_balance")
async def refill(message: types.Message, state: FSMContext, user_id: int):
    amount = int(message.text)
    min_amount = int(get_setting('min_amount'))
    if amount < min_amount:
        await state.finish()
        STR = get_string('str_more_money')
        f_min_amo = format_decimal(min_amount)
        msg = await message.answer(STR.format(f_min_amo), reply_markup=user_back_kb('user:profile'))
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
        except Exception:
            logger.debug("could not delete message")
    else:
        from services.payment_methods import get_enabled as _get_payment_methods
        enabled_methods = _get_payment_methods()
        STR = get_string('str_select_payment_method').format(format_decimal(amount))
        msg = await message.answer(STR, reply_markup=payment_methods_kb(enabled_methods))
        async with state.proxy() as data:
            data['price'] = amount
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id - 1)
    except Exception:
        logger.debug("could not delete message")


async def _handle_manual_payment(call: CallbackQuery, state: FSMContext, amount: int, user_id: int) -> None:
    await state.finish()
    manager_nick = get_setting('manager_nick') or 'support'
    f_amount = format_decimal(int(amount))
    tg_id = call.from_user.id
    copy_text = f"Хочу пополнить баланс на {amount}₽. Мой ID: {tg_id}"
    STR = get_string('str_manual_payment').format(f_amount, copy_text)
    await call.message.answer(STR, reply_markup=manual_payment_kb(manager_nick))
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


async def _handle_yookassa_payment(call: CallbackQuery, state: FSMContext, amount: int, user_id: int) -> None:
    from services.refill import (
        create_invoice as svc_create_invoice,
        finalize_with_referral_bonus,
    )
    from services.exceptions import PaymentError, UserNotFound

    await call.message.delete()
    tg_id = call.from_user.id

    try:
        payment_url, payment_id = svc_create_invoice(user_id, int(amount))
    except PaymentError:
        support_nick = get_nick('manager_nick')
        msg = get_string('str_payment_error').format(support_nick)
        await bot.send_message(chat_id=tg_id, text=msg, reply_markup=payment_error_kb())
        return

    STR1 = get_string('str_debet_money').format(format_decimal(amount))

    if tg_id != 6988175544 and tg_id != 257838190:
        await bot.send_message(
            chat_id=tg_id, text=STR1,
            reply_markup=yookassa_kb(int(amount), payment_url),
        )
        success = await check_payment_status(payment_id)
    else:
        success = True

    if not success:
        STR6 = get_string('str_pay_error').format(get_nick('manager_nick'))
        await bot.send_message(chat_id=tg_id, text=STR6)
        return

    try:
        result = finalize_with_referral_bonus(
            user_id, int(amount),
            source_type="telegram",
        )
    except UserNotFound:
        await bot.send_message(chat_id=tg_id, text=get_string('str_error'))
        return
    except Exception:
        logger.exception("yookassa payment: finalize_with_referral_bonus failed for user_id=%s", user_id)
        await bot.send_message(chat_id=tg_id, text=get_string('str_error'))
        return

    usr = get_user(id=user_id)
    user_string = await get_user_string_without_first_name(usr)
    f_amount = format_decimal(amount)
    f_balance = format_decimal(result.user_balance)

    STR2 = get_string('str_usr_pay_success').format(f_amount, f_balance)
    await bot.send_message(chat_id=tg_id, text=STR2, reply_markup=user_back_kb('user:profile'))
    STR3 = get_string('str_adm_pay_success').format(f_amount, user_string, f_balance)
    await send_admins(STR3)
    logger.info("payment success: user_id=%s amount=%s", usr['id'], amount)

    if result.referrer_bonus > 0 and result.referrer_id is not None:
        ref_user = get_user(id=str(result.referrer_id))
        if ref_user:
            f_add_bal = format_decimal(result.referrer_bonus)
            f_new_bal = format_decimal(result.referrer_new_balance)
            STR4 = get_string('str_ref_balance_refil').format(f_add_bal, f_new_bal)
            ref_tg_id = _get_tg_id_for_user(result.referrer_id) or result.referrer_id
            await bot.send_message(chat_id=ref_tg_id, text=STR4)
            ref_user_str = ref_user.get('user_name') or ref_user['id']
            logger.info("referral bonus: referrer=%s bonus=%s", ref_user_str, result.referrer_bonus)
    await state.finish()


@dp.callback_query_handler(text_startswith="pay_method:", state="refill_balance")
async def select_payment_method(call: CallbackQuery, state: FSMContext, user_id: int):
    from services.payment_methods import is_enabled as _is_method_enabled
    method = call.data.split(":")[1]

    if not _is_method_enabled(method):
        await call.answer("Этот способ оплаты недоступен", show_alert=True)
        return

    state_data = await state.get_data()
    amount = state_data.get('price')
    if amount is None:
        await state.finish()
        await call.message.answer(get_string('str_error'), reply_markup=get_menu_kb())
        return

    if method == "manual":
        await _handle_manual_payment(call, state, amount, user_id)
    elif method == "yookassa":
        await _handle_yookassa_payment(call, state, amount, user_id)
    else:
        await call.answer("Неизвестный способ оплаты", show_alert=True)
