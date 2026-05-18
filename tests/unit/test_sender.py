"""Tests for utils/sender.py."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock


def test_send_admins_sends_to_group(monkeypatch):
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    from utils import sender
    asyncio.run(sender.send_admins("hello group"))

    mock_send.assert_called_once_with(
        chat_id=-100500,
        text="hello group",
        disable_web_page_preview=True,
    )


def test_send_admins_does_not_loop_individuals(monkeypatch):
    """Must call bot.send_message exactly once, regardless of admin list size."""
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    from utils import sender
    asyncio.run(sender.send_admins("one call only"))

    assert mock_send.call_count == 1
