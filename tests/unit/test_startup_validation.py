"""Tests for utils.sender startup-topic validation."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


# ── assert_errors_topic_configured (sync, must actually exit) ───────────────

def test_assert_errors_topic_raises_when_unset(monkeypatch):
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 0)

    from utils.sender import assert_errors_topic_configured
    with pytest.raises(SystemExit, match="SUPPORT_THREAD_ERRORS"):
        assert_errors_topic_configured()


def test_assert_errors_topic_passes_when_set(monkeypatch):
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)

    from utils.sender import assert_errors_topic_configured
    assert_errors_topic_configured()  # no exception


# ── warn_missing_support_topics (async, soft warnings) ──────────────────────

def test_warn_sends_one_per_missing_category(monkeypatch):
    """All three non-errors categories missing → 3 warnings into errors thread."""
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 0)

    from utils.sender import warn_missing_support_topics
    asyncio.run(warn_missing_support_topics())

    assert mock_send.call_count == 3
    for call in mock_send.call_args_list:
        assert call.kwargs["message_thread_id"] == 7
        assert "⚠️" in call.kwargs["text"]


def test_warn_silent_when_all_categories_set(monkeypatch):
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import warn_missing_support_topics
    asyncio.run(warn_missing_support_topics())

    mock_send.assert_not_called()


def test_warn_survives_network_error(monkeypatch, caplog):
    """If send_admins raises during a warning, log and continue — do NOT propagate."""
    import logging
    failing_send = AsyncMock(side_effect=RuntimeError("network down"))
    monkeypatch.setattr("data.loader.bot.send_message", failing_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import warn_missing_support_topics
    with caplog.at_level(logging.WARNING):
        asyncio.run(warn_missing_support_topics())  # must NOT raise

    assert any("warn_missing_support_topics" in r.message for r in caplog.records)
