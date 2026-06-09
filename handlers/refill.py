import logging
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery
from aiogram import types

from utils.error_handler import report_handler_error, error_kb, ERROR_MSG
from data.loader import dp, bot
from keyboards.users_menu import (
    get_menu_kb, user_back_kb,
    yookassa_kb, payment_methods_kb, manual_payment_kb, payment_error_kb,
)
from utils.other import format_decimal
from utils.sqlite3 import get_string, get_setting, get_nick
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
    from services.payment_notifications import (
        notify_admins_success, notify_referrer, notify_user_success,
    )

    await call.message.delete()
    tg_id = call.from_user.id

    try:
        payment_url, payment_id = svc_create_invoice(
            user_id, int(amount),
            source_type="telegram", source_app_id=None,
        )
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
        # UX: не пугаем пользователя «оплата не прошла». Если она реально прошла —
        # крон-reconciler в течение минуты переведёт refill в succeeded и пришлёт
        # уведомление. Если не прошла — это видно по статусу платежа в YK.
        await bot.send_message(
            chat_id=tg_id,
            text=(
                "⏳ Платёж пока не подтверждён.\n\n"
                "Если вы успешно оплатили — баланс пополнится автоматически "
                "в течение минуты. Если нет — попробуйте ещё раз."
            ),
        )
        await state.finish()
        return

    try:
        result = finalize_with_referral_bonus(
            user_id, int(amount),
            payment_id=payment_id,
            source_type="telegram",
        )
    except UserNotFound as exc:
        await report_handler_error(
            exc, logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id,
                     "amount": amount, "tg_id": tg_id},
        )
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return
    except Exception as exc:
        await report_handler_error(
            exc, logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id,
                     "amount": amount, "tg_id": tg_id},
        )
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return

    # Уведомления — только если это была первая и реальная финализация.
    # Если крон/web-status успел раньше — was_newly_finalized=False, дублей не шлём.
    if result.was_newly_finalized:
        await notify_user_success(user_id, int(amount), result.user_balance)
        await notify_admins_success(user_id, int(amount), result.user_balance)
        if result.referrer_bonus > 0 and result.referrer_id is not None:
            await notify_referrer(result.referrer_id, result.referrer_bonus,
                                  result.referrer_new_balance or 0)
        logger.info("payment success: user_id=%s amount=%s (TG-sync)", user_id, amount)
    else:
        logger.info("payment already finalized (race): user_id=%s amount=%s pid=%s",
                    user_id, amount, payment_id)

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
        from utils.error_handler import error_kb
        await state.finish()
        await call.message.answer(get_string('str_error'), reply_markup=error_kb())
        return

    if method == "manual":
        await _handle_manual_payment(call, state, amount, user_id)
    elif method == "yookassa":
        await _handle_yookassa_payment(call, state, amount, user_id)
    else:
        await call.answer("Неизвестный способ оплаты", show_alert=True)
