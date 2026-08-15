"""Tests for utils/error_handler.py — no DB, no real Telegram."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_message_mock() -> AsyncMock:
    """Fake aiogram Message with an awaitable .answer()."""
    m = AsyncMock()
    m.answer = AsyncMock()
    return m


def _make_call_mock() -> AsyncMock:
    """Fake aiogram CallbackQuery with .message.answer()."""
    c = AsyncMock()
    c.message = AsyncMock()
    c.message.answer = AsyncMock()
    return c


# ── tests ──────────────────────────────────────────────────────────────────────

async def test_logs_at_error_level(caplog):
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        with caplog.at_level(logging.ERROR, logger="test.handler"):
            await report_handler_error(
                ValueError("db exploded"),
                logger=logging.getLogger("test.handler"),
                context={"handler": "test_fn", "user_id": 42},
            )

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected at least one ERROR log record"
    combined = " ".join(r.message for r in error_records)
    assert "db exploded" in combined
    assert "test_fn" in combined
    assert "42" in combined


async def test_calls_send_admins_with_exception_and_context():
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await report_handler_error(
            TypeError("unexpected None"),
            logger=logging.getLogger("test"),
            context={"handler": "order_confirm", "user_id": 99, "balance": 500},
        )

    mock_send.assert_called_once()
    alert_text: str = mock_send.call_args[0][0]
    assert "TypeError" in alert_text
    assert "order_confirm" in alert_text
    assert "99" in alert_text


async def test_replies_to_message_with_friendly_text():
    from utils.error_handler import report_handler_error, ERROR_MSG

    msg = _make_message_mock()
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        await report_handler_error(
            RuntimeError("oops"),
            logger=logging.getLogger("test"),
            context={"handler": "test"},
            reply_target=msg,
        )

    msg.answer.assert_called_once()
    replied_text: str = msg.answer.call_args[0][0]
    assert "ошибка" in replied_text.lower()
    # keyboard must be passed
    assert msg.answer.call_args.kwargs.get("reply_markup") is not None


async def test_replies_to_callback_query_via_message_answer():
    from utils.error_handler import report_handler_error

    call = _make_call_mock()
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        await report_handler_error(
            RuntimeError("cb fail"),
            logger=logging.getLogger("test"),
            context={"handler": "test"},
            reply_target=call,
        )

    call.message.answer.assert_called_once()


async def test_survives_send_admins_failure(caplog):
    """If send_admins raises, report_handler_error must not propagate the exception."""
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", side_effect=Exception("network timeout")):
        with caplog.at_level(logging.WARNING):
            await report_handler_error(  # must not raise
                ValueError("original"),
                logger=logging.getLogger("test"),
                context={"handler": "test"},
            )

    warn_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("send_admins" in m for m in warn_msgs)


async def test_survives_reply_failure(caplog):
    """If .answer() raises, report_handler_error must not propagate."""
    from utils.error_handler import report_handler_error

    msg = _make_message_mock()
    msg.answer.side_effect = Exception("telegram rate limit")
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        with caplog.at_level(logging.WARNING):
            await report_handler_error(
                ValueError("original"),
                logger=logging.getLogger("test"),
                context={"handler": "test"},
                reply_target=msg,
            )

    warn_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("reply" in m.lower() or "answer" in m.lower() for m in warn_msgs)
