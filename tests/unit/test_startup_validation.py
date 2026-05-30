"""Tests for utils.sender.validate_support_topics()."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


def test_fails_fast_when_errors_topic_missing(monkeypatch):
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import validate_support_topics
    with pytest.raises(SystemExit, match="SUPPORT_THREAD_ERRORS"):
        asyncio.run(validate_support_topics())


def test_passes_when_only_errors_topic_set(monkeypatch):
    """Errors topic alone is enough to start; warnings for missing categories go to it."""
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 0)

    from utils.sender import validate_support_topics
    asyncio.run(validate_support_topics())

    # Three warning sends (one per missing non-errors category), all into the errors thread.
    assert mock_send.call_count == 3
    for call in mock_send.call_args_list:
        assert call.kwargs["message_thread_id"] == 7
        assert "⚠️" in call.kwargs["text"]


def test_no_warnings_when_all_topics_set(monkeypatch):
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import validate_support_topics
    asyncio.run(validate_support_topics())

    mock_send.assert_not_called()
