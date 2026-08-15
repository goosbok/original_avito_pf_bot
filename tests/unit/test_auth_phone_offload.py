"""Regression guard: SmsGateway.send_code — синхронный сетевой вызов. Будучи
вызванным напрямую внутри async-роутера, он заморозил бы весь event loop —
тот же класс бага, что уронил бота на 8+ часов 2026-07-20 (коммит 8b02e6c,
см. tests/unit/test_refill_yookassa_offload.py). Роутер обязан выносить его
через asyncio.to_thread."""
import asyncio
import time

from services import sms


class _BlockingGateway:
    def send_code(self, phone: str, code: str) -> None:
        time.sleep(0.3)  # заглушка вместо зависшего сетевого запроса


async def test_request_code_does_not_block_event_loop(tmp_db, monkeypatch):
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _BlockingGateway())

    ticks: list[float] = []

    async def ticker() -> None:
        for _ in range(10):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.03)

    await asyncio.gather(
        ticker(),
        request_code(RequestCodeBody(phone="+79001234567")),
    )

    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.15, f"event loop was blocked by send_code: gaps={gaps}"
