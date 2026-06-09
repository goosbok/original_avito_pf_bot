"""Тесты payment_notifications — извлечённые из handlers/refill.py уведомления."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services.db import connect


def _make_user_with_telegram(user_id: int, chat_id: int, *, username: str = "u"):
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (?, 0, ?, 'X', '2026-06-09')",
            (user_id, username),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (?, 'telegram', ?, '2026-06-09', 1)",
            (user_id, str(chat_id)),
        )
        con.commit()


@pytest.mark.asyncio
async def test_notify_user_success_sends_to_chat_id(tmp_db: Path, monkeypatch):
    _make_user_with_telegram(42, chat_id=10000042)
    monkeypatch.setattr(
        "services.payment_notifications.get_string",
        lambda _p: "баланс пополнен: {} / {}",
    )

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_user_success(user_id=42, amount=500, new_balance=500)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs or {}
    args = mock_send.call_args.args
    # chat_id может быть позиционно или kwarg — поддержим оба.
    chat_id = kwargs.get("chat_id") or (args[0] if args else None)
    assert chat_id == 10000042


@pytest.mark.asyncio
async def test_notify_user_success_silent_if_no_telegram_provider(tmp_db: Path):
    """Web-only юзер без TG-привязки: notify не падает, send_message НЕ вызывается."""
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (777, 0, NULL, 'Web', '2026-06-09')"
        )
        con.commit()

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_user_success(user_id=777, amount=500, new_balance=500)
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_user_success_swallows_send_errors(tmp_db: Path, monkeypatch):
    """Юзер заблокировал бота → send_message бросает. notify не должно падать."""
    _make_user_with_telegram(42, chat_id=10000042)
    monkeypatch.setattr(
        "services.payment_notifications.get_string",
        lambda _p: "баланс пополнен: {} / {}",
    )

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = Exception("Bot was blocked by the user")
        # Не падаем
        await notify_user_success(user_id=42, amount=500, new_balance=500)


@pytest.mark.asyncio
async def test_notify_admins_success_posts_to_orders(tmp_db: Path, monkeypatch):
    _make_user_with_telegram(42, chat_id=10000042, username="testuser")
    monkeypatch.setattr(
        "services.payment_notifications.get_string",
        lambda _p: "admin: {} {} {}",
    )

    from services.payment_notifications import notify_admins_success
    with patch("services.payment_notifications.send_admins", new_callable=AsyncMock) as mock_admin:
        await notify_admins_success(user_id=42, amount=500, new_balance=500)

    mock_admin.assert_called_once()
    args, kwargs = mock_admin.call_args
    assert args[1] == "orders" or kwargs.get("category") == "orders"


@pytest.mark.asyncio
async def test_notify_referrer_sends_to_referrer_chat(tmp_db: Path, monkeypatch):
    _make_user_with_telegram(100, chat_id=999999, username="referrer")
    monkeypatch.setattr(
        "services.payment_notifications.get_string",
        lambda _p: "реф бонус: {} / {}",
    )

    from services.payment_notifications import notify_referrer
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_referrer(referrer_id=100, bonus=150, new_balance=150)

    mock_send.assert_called_once()
