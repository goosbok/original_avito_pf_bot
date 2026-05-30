"""Tests for utils/sender.py — category-routed admin notifications."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


def _patch_common(monkeypatch):
    """Reset the bot mock and chat id for every test."""
    mock_send = AsyncMock(return_value="sent-message-sentinel")
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    return mock_send


def test_send_admins_routes_questions_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)

    from utils import sender
    result = asyncio.run(sender.send_admins("hi", "questions"))

    mock_send.assert_called_once_with(
        chat_id=-100500,
        text="hi",
        message_thread_id=3,
        parse_mode=None,
        disable_web_page_preview=True,
    )
    assert result == "sent-message-sentinel"


def test_send_admins_routes_orders_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)

    from utils import sender
    asyncio.run(sender.send_admins("order!", "orders"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 5


def test_send_admins_routes_errors_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)

    from utils import sender
    asyncio.run(sender.send_admins("boom", "errors"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 7


def test_send_admins_routes_new_users_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils import sender
    asyncio.run(sender.send_admins("hello new user", "new_users"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 9


def test_send_admins_falls_back_to_errors_topic_when_unset(monkeypatch):
    """When the requested category's topic is unset, route to errors topic with prefix."""
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)

    from utils import sender
    result = asyncio.run(sender.send_admins("orphan question", "questions"))

    assert result == "sent-message-sentinel"
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["message_thread_id"] == 7
    assert "Не задан топик для questions" in kwargs["text"]
    assert "orphan question" in kwargs["text"]


def test_send_admins_returns_none_when_both_target_and_errors_unset(monkeypatch):
    """If both the requested topic and the errors topic are unset, drop the message."""
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 0)

    from utils import sender
    result = asyncio.run(sender.send_admins("orphan", "questions"))

    assert result is None
    mock_send.assert_not_called()


def test_send_admins_does_not_recurse_when_errors_itself_unset(monkeypatch):
    """If category=='errors' and its own topic is unset, just drop (don't loop forever)."""
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 0)

    from utils import sender
    result = asyncio.run(sender.send_admins("alert", "errors"))

    assert result is None
    mock_send.assert_not_called()


def test_send_admins_forwards_parse_mode(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)

    from utils import sender
    asyncio.run(sender.send_admins("<b>x</b>", "questions", parse_mode="HTML"))

    assert mock_send.call_args.kwargs["parse_mode"] == "HTML"


def test_send_admins_rejects_unknown_category(monkeypatch):
    _patch_common(monkeypatch)

    from utils import sender
    with pytest.raises(ValueError, match="unknown category"):
        asyncio.run(sender.send_admins("nope", "not_a_category"))  # type: ignore[arg-type]
