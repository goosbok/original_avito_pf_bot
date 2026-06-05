"""Тесты SmsGateway: stub-реализация и фабрика."""
import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_gateway_singleton():
    """Сбрасываем singleton фабрики между тестами — кейсы с monkeypatch на env
    должны получать свежий get_gateway()."""
    from services import sms
    sms._reset_for_tests()
    yield
    sms._reset_for_tests()


def test_stub_gateway_logs_and_stores_code(caplog):
    from services.sms import StubSmsGateway
    gw = StubSmsGateway()
    with caplog.at_level(logging.INFO, logger="services.sms"):
        gw.send_code("+79991234567", "4521")
    assert gw.last_codes["+79991234567"] == "4521"
    assert any("4521" in rec.message for rec in caplog.records)


def test_get_gateway_returns_stub_when_env_not_set(monkeypatch):
    monkeypatch.delenv("SMS_GATEWAY", raising=False)
    from services.sms import StubSmsGateway, get_gateway
    gw = get_gateway()
    assert isinstance(gw, StubSmsGateway)


def test_get_gateway_returns_stub_when_env_set_to_stub(monkeypatch):
    monkeypatch.setenv("SMS_GATEWAY", "stub")
    from services.sms import StubSmsGateway, get_gateway
    gw = get_gateway()
    assert isinstance(gw, StubSmsGateway)


def test_get_gateway_raises_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("SMS_GATEWAY", "magic_provider_999")
    from services.sms import get_gateway
    with pytest.raises(ValueError, match="unknown SMS_GATEWAY"):
        get_gateway()
