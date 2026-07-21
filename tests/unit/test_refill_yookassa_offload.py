"""Regression test for the 2026-07-20 outage: a slow/hung call to YooKassa
inside an aiogram handler blocked the whole asyncio event loop, freezing
Telegram polling *and* the apscheduler jobs for 8+ hours until a manual
restart. Root cause: services.refill.create_invoke (sync, requests-based
YooKassa SDK call with no socket timeout) was invoked directly on the event
loop instead of being offloaded to a thread — see handlers/refill.py and
utils/yookassa_refil.py."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_handle_yookassa_payment_does_not_block_event_loop(tmp_db):
    from handlers.refill import _handle_yookassa_payment
    import handlers.refill as refill_mod

    def blocking_create_invoice(user_id, amount, **kwargs):
        time.sleep(0.3)  # stand-in for a hung/slow network call to YooKassa
        return ("https://pay.example/x", "pid-1")

    ticks: list[float] = []

    async def ticker() -> None:
        for _ in range(10):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.03)

    state = MagicMock()
    state.finish = AsyncMock()

    with patch("services.refill.create_invoice", side_effect=blocking_create_invoice), \
         patch.object(refill_mod, "bot") as bot_mock, \
         patch("handlers.refill.check_payment_status", new=AsyncMock(return_value=False)):
        bot_mock.send_message = AsyncMock()

        # gather (not sequential await) so the ticker task can genuinely
        # interleave with the handler — a real "is the loop starved?" check.
        await asyncio.gather(
            ticker(),
            _handle_yookassa_payment(state, 500, 1, tg_id=777),
        )

    # If create_invoice's blocking sleep ran directly on the event loop, the
    # ticker would be starved for ~0.3s straight instead of ticking every
    # ~0.03s. asyncio.to_thread keeps the loop free while the thread blocks.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.15, f"event loop was blocked by create_invoice: gaps={gaps}"


async def test_check_payment_status_does_not_block_event_loop(tmp_db):
    from utils.yookassa_refil import check_payment_status

    fake_payment = MagicMock()
    fake_payment.status = "succeeded"

    def blocking_find_one(payment_id):
        time.sleep(0.3)
        return fake_payment

    ticks: list[float] = []

    async def ticker() -> None:
        for _ in range(10):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.03)

    with patch("utils.yookassa_refil.Payment") as mock_payment, \
         patch("utils.yookassa_refil.SHOP_ID", 1), \
         patch("utils.yookassa_refil.SECRET_KEY", "s"):
        mock_payment.find_one.side_effect = blocking_find_one

        results = await asyncio.gather(ticker(), check_payment_status("pid-1"))
        result = results[1]

    assert result is True
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.15, f"event loop was blocked by Payment.find_one: gaps={gaps}"
