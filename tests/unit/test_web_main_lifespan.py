"""Lifespan регистрирует order-links cron-задачи."""
import asyncio
from unittest.mock import AsyncMock, patch


def test_lifespan_starts_deadline_and_dispatcher_loops(tmp_db):
    async def _drive():
        with patch("web.main.run_deadline_loop", new=AsyncMock()) as dline, \
             patch("web.main.run_dispatcher_loop", new=AsyncMock()) as dispatcher, \
             patch("web.main.run_expiry_loop", new=AsyncMock()):
            from web.main import lifespan, app
            async with lifespan(app):
                await asyncio.sleep(0)
            dline.assert_called()
            dispatcher.assert_called()

    asyncio.run(_drive())
