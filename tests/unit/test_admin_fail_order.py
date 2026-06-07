"""Админ-кнопка «Отметить заказ failed» (Спек §5.4)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_db):
    """Ensure the production schema (incl. `settings`) is in place before
    handlers.admin_orders is imported."""
    pass  # just depending on tmp_db is enough


@pytest.mark.asyncio
async def test_fail_order_prompt_asks_for_order_id():
    from handlers.admin_orders import fail_order_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.FailOrder.order_id") as mock_fsm_state:
        mock_fsm_state.set = AsyncMock()
        await fail_order_prompt(call, state)
    state.set.assert_not_called()  # сначала выставит FSM-state — проверяем через bot.send_message
    call.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_fail_order_collect_reason_then_confirm(tmp_db):
    """Полный flow: id → reason → confirm → fail_remaining_links."""
    from handlers.admin_orders import fail_order_confirm

    message = MagicMock()
    message.text = "yes"
    message.from_user.id = 42
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "order_id": 123, "reason": "manual cancel"
    })

    with patch("handlers.admin_orders.fail_remaining_links",
               return_value=("paid", "failed")) as mock, \
         patch("handlers.admin_orders.notify_order_status_changed",
               new=AsyncMock()) as notif, \
         patch("handlers.admin_orders.get_order",
               return_value={"increment": 123, "user_id": 1, "status": "paid"}):
        await fail_order_confirm(message, state)

    mock.assert_called_once_with(order_id=123, reason="manual cancel",
                                 admin_id=42)
    notif.assert_awaited()
    state.finish.assert_awaited()
