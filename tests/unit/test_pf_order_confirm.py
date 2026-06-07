"""confirm_order должен использовать services.orders, не legacy add_order."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_confirm_order_uses_service_layer_not_legacy(tmp_db):
    import sqlite3
    # seed a user with sufficient balance
    with sqlite3.connect(str(tmp_db)) as con:
        con.execute("INSERT INTO users(id, balance, user_name) "
                    "VALUES (777, 5000, 'tester')")
        con.commit()

    from handlers.pf_order import confirm_order

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    call.from_user.id = 777

    # FSMContext.proxy() must async-context-manage; use AsyncMock chain
    # state must be async-compatible for await state.finish() etc.
    state = MagicMock()
    state.finish = AsyncMock()
    state.reset_data = AsyncMock()
    proxy_data = {
        'total_price': 100,
        'days': 3,
        'fix': 100,
        'links': ['https://avito.ru/a', 'https://avito.ru/b'],
        'contact': True,
    }
    state.proxy = MagicMock(return_value=AsyncMock())
    state.proxy.return_value.__aenter__ = AsyncMock(return_value=proxy_data)
    state.proxy.return_value.__aexit__ = AsyncMock(return_value=None)

    def _get_string_side_effect(key):
        # str_new_order_text needs 9 positional slots; str_order_confirm needs 1
        if key == 'str_order_confirm':
            return "Заказ {} создан!"
        return "{}" * 9

    with patch("handlers.pf_order.create_unpaid", return_value=42) as cu, \
         patch("handlers.pf_order.pay_with_balance") as pwb, \
         patch("handlers.pf_order._get_order",
               return_value={
                   "increment": 42, "user_id": 777, "price": 100,
                   "position_name": "3/100", "status": "paid",
                   "contacts": True, "date": "2026-06-07T10:00:00+00:00",
               }), \
         patch("handlers.pf_order._list_order_links",
               return_value=[
                   {"url": "https://avito.ru/a", "status": "pending"},
                   {"url": "https://avito.ru/b", "status": "pending"},
               ]), \
         patch("handlers.pf_order.send_admins", new=AsyncMock()), \
         patch("handlers.pf_order.get_string", side_effect=_get_string_side_effect), \
         patch("handlers.pf_order.track_step"), \
         patch("handlers.pf_order.get_user",
               return_value={"id": 777, "balance": 5000, "user_name": "tester"}):
        await confirm_order(call, state, user_id=777)

    cu.assert_called_once()
    kwargs = cu.call_args.kwargs
    assert kwargs["user_id"] == 777
    assert kwargs["links"] == ['https://avito.ru/a', 'https://avito.ru/b']
    assert kwargs["days"] == 3
    assert kwargs["fix_count"] == 100
    assert kwargs["contacts"] is True
    pwb.assert_called_once_with(order_id=42, user_id=777)
