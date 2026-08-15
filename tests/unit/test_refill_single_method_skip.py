"""refill(): пропуск выбора способа оплаты, если включён только один метод."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_message(text="500", chat_id=111, message_id=50, user_id=777):
    message = MagicMock()
    message.text = text
    message.chat.id = chat_id
    message.message_id = message_id
    message.from_user.id = user_id
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_refill_skips_choice_when_only_yookassa_enabled(tmp_db):
    from handlers.refill import refill

    message = _make_message()
    state = MagicMock()
    state.finish = AsyncMock()

    with patch("services.payment_methods.get_enabled", return_value=["yookassa"]), \
         patch("handlers.refill._handle_yookassa_payment", new=AsyncMock()) as handle_yk, \
         patch("handlers.refill._handle_manual_payment", new=AsyncMock()) as handle_manual:
        await refill(message, state, user_id=777)

    message.answer.assert_not_called()
    handle_manual.assert_not_called()
    handle_yk.assert_called_once()
    args, kwargs = handle_yk.call_args
    assert args[:3] == (state, 500, 777)
    assert kwargs["tg_id"] == 777


@pytest.mark.asyncio
async def test_refill_skips_choice_when_only_manual_enabled(tmp_db):
    from handlers.refill import refill

    message = _make_message()
    state = MagicMock()
    state.finish = AsyncMock()

    with patch("services.payment_methods.get_enabled", return_value=["manual"]), \
         patch("handlers.refill._handle_yookassa_payment", new=AsyncMock()) as handle_yk, \
         patch("handlers.refill._handle_manual_payment", new=AsyncMock()) as handle_manual:
        await refill(message, state, user_id=777)

    message.answer.assert_not_called()
    handle_yk.assert_not_called()
    handle_manual.assert_called_once()
    args, kwargs = handle_manual.call_args
    assert args[:3] == (state, 500, 777)
    assert kwargs["tg_id"] == 777


@pytest.mark.asyncio
async def test_refill_shows_choice_when_multiple_methods_enabled(tmp_db):
    from handlers.refill import refill

    message = _make_message()
    state = MagicMock()
    proxy_data = {}
    state.proxy = MagicMock(return_value=AsyncMock())
    state.proxy.return_value.__aenter__ = AsyncMock(return_value=proxy_data)
    state.proxy.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("services.payment_methods.get_enabled", return_value=["manual", "yookassa"]), \
         patch("handlers.refill._handle_yookassa_payment", new=AsyncMock()) as handle_yk, \
         patch("handlers.refill._handle_manual_payment", new=AsyncMock()) as handle_manual:
        await refill(message, state, user_id=777)

    handle_yk.assert_not_called()
    handle_manual.assert_not_called()
    message.answer.assert_called_once()
    assert proxy_data.get("price") == 500


@pytest.mark.asyncio
async def test_refill_deletes_prompt_and_own_message(tmp_db):
    """Промпт "введите сумму" (profile.ref_bal) и сообщение юзера с суммой
    должны удаляться сразу — иначе промпт остаётся висеть в чате и
    накапливается при повторном заходе в "Пополнить баланс" (см. отчёт)."""
    from handlers.refill import refill
    import handlers.refill as refill_mod

    message = _make_message(message_id=50)
    state = MagicMock()
    state.finish = AsyncMock()

    with patch("services.payment_methods.get_enabled", return_value=["yookassa"]), \
         patch("handlers.refill._handle_yookassa_payment", new=AsyncMock()), \
         patch.object(refill_mod, "bot") as bot_mock:
        bot_mock.delete_message = AsyncMock()
        await refill(message, state, user_id=777)

    deleted_ids = {call.kwargs["message_id"] for call in bot_mock.delete_message.call_args_list}
    assert deleted_ids == {49, 50}  # 49 = промпт (message_id - 1), 50 = сообщение юзера


@pytest.mark.asyncio
async def test_select_payment_method_passes_tg_id_and_old_message(tmp_db):
    from handlers.refill import select_payment_method

    call = MagicMock()
    call.data = "pay_method:yookassa"
    call.message = MagicMock()
    call.from_user.id = 777

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"price": 500})

    with patch("services.payment_methods.is_enabled", return_value=True), \
         patch("handlers.refill._handle_yookassa_payment", new=AsyncMock()) as handle_yk:
        await select_payment_method(call, state, user_id=777)

    handle_yk.assert_called_once()
    args, kwargs = handle_yk.call_args
    assert args[:3] == (state, 500, 777)
    assert kwargs["tg_id"] == 777
    assert kwargs["old_message"] is call.message
