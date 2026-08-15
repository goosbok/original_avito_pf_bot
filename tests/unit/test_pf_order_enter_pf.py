"""enter_pf_func / pf:enter-pf не должны падать без 'days' в FSM-данных.

KeyError: 'days' в проде (tg_id=901840907 23.07, tg_id=1112274823 04.08,
msg_text='15'): стейт стёрт «Назад»/меню (state.finish()), а старая
клавиатура pf_period_kb с кнопкой pf:enter-pf осталась в чате — юзер
попадает в EnterData.pf без days. Вместо падения — заново спросить период.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_message(text):
    message = MagicMock()
    message.text = text
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_enter_pf_without_days_reasks_period_not_crash(tmp_db):
    from handlers.pf_order import enter_pf_func, EnterData

    message = _make_message("15")
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})  # days отсутствует
    state.set_state = AsyncMock()

    with patch("handlers.pf_order.get_string",
               return_value="Введите период:") as gs, \
         patch("handlers.pf_order.track_step"):
        await enter_pf_func(message, state, user_id=901840907)

    gs.assert_any_call('str_enter_days')
    message.answer.assert_called_once()
    state.set_state.assert_awaited_once_with(EnterData.period.state)


@pytest.mark.asyncio
async def test_enter_pf_callback_without_days_reasks_period(tmp_db):
    """Гейт на входе: pf:enter-pf без days в стейте не ставит EnterData.pf,
    а сразу просит период (EnterData.period)."""
    from handlers.pf_order import pf, EnterData

    call = MagicMock()
    call.data = "pf:enter-pf"
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.set_state = AsyncMock()

    with patch("handlers.pf_order.get_string",
               return_value="Введите период:") as gs, \
         patch("handlers.pf_order.track_step"):
        await pf(call, state, user_id=901840907)

    gs.assert_any_call('str_enter_days')
    state.set_state.assert_awaited_once_with(EnterData.period.state)


@pytest.mark.asyncio
async def test_enter_pf_with_days_happy_path_unchanged(tmp_db):
    """Регрессия: с days в стейте ввод количества ПФ работает как раньше."""
    from handlers.pf_order import enter_pf_func

    message = _make_message("15")
    state = MagicMock()
    state.get_data = AsyncMock(return_value={'days': '7'})
    state.set_state = AsyncMock()
    proxy_data = {}
    state.proxy = MagicMock(return_value=AsyncMock())
    state.proxy.return_value.__aenter__ = AsyncMock(return_value=proxy_data)
    state.proxy.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("handlers.pf_order.get_price", return_value=12), \
         patch("handlers.pf_order.get_string", return_value="Пришлите ссылки"), \
         patch("handlers.pf_order.track_step"):
        await enter_pf_func(message, state, user_id=901840907)

    assert proxy_data['days'] == '7'
    assert proxy_data['fix'] == 15
    assert proxy_data['total_price'] == int(12 * 15.0 * 7)
    state.set_state.assert_awaited_once_with("place_order")
    message.answer.assert_called_once()
