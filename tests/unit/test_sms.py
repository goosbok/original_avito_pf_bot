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


def test_smspilot_gateway_sends_code(monkeypatch):
    captured = {}

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "send": [{"server_id": "1", "phone": "79001234567", "status": "0"}],
                "balance": "10.00",
            }

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setenv("SMSPILOT_APIKEY", "test-key")
    monkeypatch.setattr("httpx.post", fake_post)

    from services.sms import SmspilotGateway
    gw = SmspilotGateway()
    gw.send_code("+79001234567", "4521")

    assert captured["url"] == "https://smspilot.ru/api.php"
    assert captured["data"]["apikey"] == "test-key"
    assert captured["data"]["to"] == "79001234567"  # без ведущего +
    assert captured["data"]["send"] == "Code 4521"  # согласованный шаблон
    assert captured["data"]["format"] == "json"
    assert captured["data"]["lang"] == "ru"
    assert "from" not in captured["data"]  # физлицу своё имя не положено
    assert captured["timeout"] is not None  # явный socket timeout


def test_smspilot_gateway_raises_on_error_response(monkeypatch):
    """Ошибка приходит с HTTP 200 — разбирать нужно тело, не статус."""

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "error": {
                    "code": "8",
                    "description": "Insufficient funds",
                    "description_ru": "Недостаточно средств",
                }
            }

    monkeypatch.setenv("SMSPILOT_APIKEY", "test-key")
    monkeypatch.setattr("httpx.post", lambda *a, **kw: _FakeResponse())

    from services.sms import SmspilotGateway
    gw = SmspilotGateway()
    with pytest.raises(RuntimeError, match="8"):
        gw.send_code("+79001234567", "4521")


def test_smspilot_gateway_requires_apikey(monkeypatch):
    monkeypatch.delenv("SMSPILOT_APIKEY", raising=False)
    from services.sms import SmspilotGateway
    with pytest.raises(ValueError, match="SMSPILOT_APIKEY"):
        SmspilotGateway()


def test_get_gateway_returns_smspilot_when_env_set(monkeypatch):
    monkeypatch.setenv("SMS_GATEWAY", "smspilot")
    monkeypatch.setenv("SMSPILOT_APIKEY", "test-key")
    from services.sms import SmspilotGateway, get_gateway
    gw = get_gateway()
    assert isinstance(gw, SmspilotGateway)
