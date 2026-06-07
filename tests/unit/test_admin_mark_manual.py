"""Админ-кнопка «Отправил все manual» (Спек §5.2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_db):
    """Ensure the production schema (incl. `settings`) is in place before
    handlers.admin_orders is imported.  The module transitively loads
    keyboards.users_menu which calls get_price() at module level — that
    query will fail if the `settings` table doesn't exist yet."""
    pass  # just depending on tmp_db is enough


@pytest.mark.asyncio
async def test_mark_manual_confirm_dispatches_and_replies(tmp_db):
    from handlers.admin_orders import mark_manual_confirm

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    call.from_user.id = 42
    state = AsyncMock()

    with patch("handlers.admin_orders.mark_all_manual_in_work",
               return_value=(7, [])) as mock:
        await mark_manual_confirm(call, state)

    mock.assert_called_once_with(admin_id=42)
    state.finish.assert_awaited()
    call.message.answer.assert_awaited()
    text = call.message.answer.await_args.args[0]
    assert "7" in text


@pytest.mark.asyncio
async def test_mark_manual_confirm_fires_notify_for_transitions():
    from handlers.admin_orders import mark_manual_confirm

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    call.from_user.id = 42
    state = AsyncMock()

    with patch("handlers.admin_orders.mark_all_manual_in_work",
               return_value=(3, [(101, "paid", "done")])), \
         patch("handlers.admin_orders.get_order",
               return_value={"increment": 101, "user_id": 999, "status": "done"}), \
         patch("handlers.admin_orders.notify_order_status_changed",
               new=AsyncMock()) as notif:
        await mark_manual_confirm(call, state)

    notif.assert_awaited_once()
    kwargs = notif.call_args.kwargs
    assert kwargs["order_id"] == 101
    assert kwargs["user_id"] == 999
    assert kwargs["old_status"] == "paid"
    assert kwargs["new_status"] == "done"


@pytest.mark.asyncio
async def test_mark_manual_prompt_asks_confirmation_with_count(tmp_db):
    from handlers.admin_orders import mark_manual_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.count_pending_manual_links",
               return_value=5), \
         patch("handlers.admin_orders.MarkManual.confirm") as mock_state_confirm:
        mock_state_confirm.set = AsyncMock()
        await mark_manual_prompt(call, state)
    text = call.message.answer.await_args.args[0]
    assert "5" in text  # сколько будет переведено
