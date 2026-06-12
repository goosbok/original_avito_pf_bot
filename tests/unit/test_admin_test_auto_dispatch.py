"""Админ-кнопка «🧪 Test auto-dispatch» — FSM handler tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_db):
    """Подтянуть schema через tmp_db до import handlers."""
    pass


@pytest.mark.asyncio
async def test_prompt_resets_state_and_asks_for_id(tmp_db):
    """Callback test_auto_dispatch — сбрасывает state, спрашивает ID."""
    from handlers.admin_orders import test_auto_dispatch_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.TestAutoDispatch.order_id") as fsm_state:
        fsm_state.set = AsyncMock()
        await test_auto_dispatch_prompt(call, state)

    state.finish.assert_awaited()
    call.message.answer.assert_awaited()
    args, kwargs = call.message.answer.call_args
    assert "Введите ID" in (args[0] if args else kwargs.get("text", ""))
