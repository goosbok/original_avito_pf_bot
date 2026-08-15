"""Regression test: services.auth_telegram._send_telegram_message does a
synchronous httpx.post with no offload. web/routers/auth_telegram.py's
POST /request-code calls it directly from an async handler — a hung/slow
Telegram Bot API call would freeze the whole event loop (bot polling,
apscheduler jobs, all API-container HTTP traffic), exactly like the
YooKassa outage on 2026-07-20 (see tests/unit/test_refill_yookassa_offload.py)."""
import asyncio
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

from web.schemas import OTPRequestBody


def _seed_user(tmp_db: Path, tg_id: int) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (tg_id, "bob", "Bob", 0, "2026-01-01"),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2026-01-01')",
            (tg_id, str(tg_id)),
        )
        con.commit()


async def test_request_code_endpoint_does_not_block_event_loop(tmp_db: Path):
    from web.routers.auth_telegram import request_code

    _seed_user(tmp_db, 777)

    def blocking_send(bot_token, telegram_id, text):
        time.sleep(0.3)  # stand-in for a hung/slow call to the Telegram Bot API

    ticks: list[float] = []

    async def ticker() -> None:
        for _ in range(10):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.03)

    with patch("services.auth_telegram._send_telegram_message", side_effect=blocking_send):
        await asyncio.gather(
            ticker(),
            request_code(OTPRequestBody(identifier="777")),
        )

    # If _send_telegram_message's blocking sleep ran directly on the event
    # loop, the ticker would be starved for ~0.3s straight instead of ticking
    # every ~0.03s. asyncio.to_thread keeps the loop free while the thread blocks.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.15, f"event loop was blocked by _send_telegram_message: gaps={gaps}"
