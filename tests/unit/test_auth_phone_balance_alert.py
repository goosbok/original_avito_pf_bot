"""Алерты админам про баланс SMSPILOT — send_admins мокается на уровне
utils.sender.send_admins (тот же паттерн, что в test_payment_probe.py),
т.к. импортируется лениво внутри функции-алерта."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.sms import SmspilotGateway


class _FakeLowBalanceGateway:
    """Успешная отправка, баланс ниже порога."""

    def __init__(self, balance: float) -> None:
        self.last_balance = balance

    def send_code(self, phone: str, code: str) -> None:
        pass


class _FakeFailingGateway:
    def send_code(self, phone: str, code: str) -> None:
        raise RuntimeError("SMSPILOT error 8: Недостаточно средств")


async def test_low_balance_triggers_alert(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))

    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "150.0" in alert or "150.00" in alert
    assert mock_send.call_args[0][1] == "errors"


async def test_low_balance_alert_suppressed_by_cooldown(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))
        await request_code(RequestCodeBody(phone="+79001234568"))

    mock_send.assert_called_once()  # второй вызов подавлен кулдауном


async def test_balance_above_threshold_does_not_alert(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(500.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await request_code(RequestCodeBody(phone="+79001234567"))

    mock_send.assert_not_called()


async def test_send_failure_triggers_alert_and_still_returns_502(tmp_db, monkeypatch):
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code
    from fastapi import HTTPException

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeFailingGateway())
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_COOLDOWN_MIN", 60)

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        with pytest.raises(HTTPException) as exc_info:
            await request_code(RequestCodeBody(phone="+79001234567"))

    assert exc_info.value.status_code == 502
    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "Недостаточно средств" in alert
    assert "+790***4567" in alert  # телефон замаскирован: +79001234567 → +790***4567


async def test_send_admins_failure_does_not_break_request_code(tmp_db, monkeypatch, caplog):
    """send_admins сам упал — эндпоинт всё равно должен доработать штатно."""
    import logging
    from services import sms
    from web.routers.auth_phone import RequestCodeBody, request_code

    monkeypatch.setattr(sms, "get_gateway", lambda: _FakeLowBalanceGateway(150.0))
    monkeypatch.setattr("data.config.SMS_BALANCE_ALERT_THRESHOLD_RUB", 200)

    with patch("utils.sender.send_admins", side_effect=Exception("network down")):
        with caplog.at_level(logging.WARNING):
            result = await request_code(RequestCodeBody(phone="+79001234567"))

    assert result == {"ok": True}
    assert any("send_admins" in r.message for r in caplog.records)
