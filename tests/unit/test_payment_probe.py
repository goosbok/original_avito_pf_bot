"""Tests for services/payment_probe.py — YooKassa SDK fully mocked."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _fake_payment(payment_id: str = "test-payment-id") -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    return p


# ── probe_yookassa ─────────────────────────────────────────────────────────────

def test_probe_ok_when_create_and_cancel_succeed():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.return_value = _fake_payment("pid-1")
        mock_payment.cancel.return_value = MagicMock()

        result = probe_yookassa()

    assert result.ok is True
    assert result.error_msg is None
    assert result.latency_ms >= 0
    mock_payment.create.assert_called_once()
    mock_payment.cancel.assert_called_once_with("pid-1")


def test_probe_fails_when_create_raises():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.side_effect = Exception("Unauthorized (401)")

        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "create failed" in result.error_msg
    assert "Unauthorized" in result.error_msg
    mock_payment.cancel.assert_not_called()


def test_probe_fails_when_cancel_raises():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.return_value = _fake_payment("pid-2")
        mock_payment.cancel.side_effect = Exception("Payment already captured")

        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "cancel failed" in result.error_msg
    assert "Payment already captured" in result.error_msg


def test_probe_fails_when_credentials_missing():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.SHOP_ID", 0), \
         patch("services.payment_probe.SECRET_KEY", ""):
        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "not configured" in result.error_msg


# ── probe_and_alert ────────────────────────────────────────────────────────────

async def test_probe_and_alert_sends_alert_on_failure():
    from services.payment_probe import probe_and_alert, ProbeResult

    failing = ProbeResult(ok=False, error_msg="create failed: BadRequest: receipt required", latency_ms=42.0)

    with patch("services.payment_probe.probe_yookassa", return_value=failing), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await probe_and_alert()

    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "Платёжка" in alert
    assert "receipt required" in alert


async def test_probe_and_alert_no_alert_on_success():
    from services.payment_probe import probe_and_alert, ProbeResult

    ok = ProbeResult(ok=True, latency_ms=120.0)

    with patch("services.payment_probe.probe_yookassa", return_value=ok), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await probe_and_alert()

    mock_send.assert_not_called()


async def test_probe_and_alert_skips_when_yookassa_disabled():
    from services.payment_probe import probe_and_alert

    with patch("services.payment_probe.is_yookassa_enabled", return_value=False), \
         patch("services.payment_probe.probe_yookassa") as mock_probe:
        await probe_and_alert()

    mock_probe.assert_not_called()


async def test_probe_and_alert_survives_send_admins_failure(caplog):
    from services.payment_probe import probe_and_alert, ProbeResult

    failing = ProbeResult(ok=False, error_msg="timeout", latency_ms=5000.0)

    with patch("services.payment_probe.probe_yookassa", return_value=failing), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", side_effect=Exception("network down")):
        with caplog.at_level(logging.WARNING):
            await probe_and_alert()  # must not raise

    assert any("send_admins" in r.message for r in caplog.records)
