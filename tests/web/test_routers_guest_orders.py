"""Tests for /api/guest-orders/* endpoints."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    from web.main import app
    return TestClient(app)


def _fake_payment(url="https://pay.yookassa.ru/pay/abc", pid="pay-guest-1"):
    return (url, pid)


# ── payment-available ────────────────────────────────────────────────────────

def test_payment_available_false_when_yookassa_disabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: False)
    r = client.get("/api/guest-orders/payment-available")
    assert r.status_code == 200
    assert r.json() == {"available": False}


def test_payment_available_true_when_enabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: True)
    r = client.get("/api/guest-orders/payment-available")
    assert r.status_code == 200
    assert r.json() == {"available": True}


# ── POST /api/guest-orders/pf ────────────────────────────────────────────────

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: True)
    monkeypatch.setattr("web.routers.guest_orders.get_pf_price_per_unit", lambda: 6)


VALID_BODY = {
    "links": ["https://www.avito.ru/item/123"],
    "days": 7,
    "fix_count": 30,
    "contacts": False,
    "phone": "+79991234567",
    "agreed_privacy": True,
    "agreed_offer": True,
}


def test_create_guest_order_success(client, enabled, monkeypatch):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/abc", "pay-1"),
    )
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["guest_order_id"] > 0
    assert body["payment_url"] == "https://pay/abc"


def test_create_guest_order_503_when_payment_disabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: False)
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    assert r.status_code == 503


def test_create_guest_order_invalid_link(client, enabled):
    body = {**VALID_BODY, "links": ["https://www.example.com/not-avito"]}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_empty_phone(client, enabled):
    body = {**VALID_BODY, "phone": ""}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_fix_count_too_low(client, enabled):
    body = {**VALID_BODY, "fix_count": 3}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_price_calculated_correctly(client, enabled, monkeypatch):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/x", "pay-x"),
    )
    monkeypatch.setattr("web.routers.guest_orders.get_pf_price_per_unit", lambda: 6)
    body = {**VALID_BODY, "days": 7, "fix_count": 30}
    # price = 30 * 7 * 1 (link) * 6 = 1260
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 201
    gid = r.json()["guest_order_id"]
    from services.guest_orders import get_guest_order
    order = get_guest_order(gid)
    assert order["price"] == 1260


def test_create_guest_order_requires_agreed_privacy(client, enabled):
    body = {**VALID_BODY, "agreed_privacy": False}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 400
    assert "политику" in r.json()["detail"].lower() or "согласи" in r.json()["detail"].lower()


def test_create_guest_order_requires_agreed_offer(client, enabled):
    body = {**VALID_BODY, "agreed_offer": False}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 400


def test_create_guest_order_missing_agreed_fields_returns_422(client, enabled):
    body = {k: v for k, v in VALID_BODY.items() if k not in ("agreed_privacy", "agreed_offer")}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


# ── GET /api/guest-orders/{id}/status ────────────────────────────────────────

def _create_order_with_payment(client, enabled, monkeypatch, payment_id="pay-2"):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/x", payment_id),
    )
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    return r.json()["guest_order_id"]


def test_status_pending_when_yookassa_returns_pending(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "pending"

    with patch("yookassa.Payment") as MockPayment, \
         patch("yookassa.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_status_paid_when_yookassa_returns_succeeded(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "succeeded"

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.guest_orders._notify_guest_order_paid", _noop)

    with patch("yookassa.Payment") as MockPayment, \
         patch("yookassa.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paid"
    assert body["order_id"] == gid


def test_status_paid_is_idempotent(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "succeeded"

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.guest_orders._notify_guest_order_paid", _noop)

    with patch("yookassa.Payment") as MockPayment, \
         patch("yookassa.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r1 = client.get(f"/api/guest-orders/{gid}/status")
        r2 = client.get(f"/api/guest-orders/{gid}/status")

    assert r1.json()["status"] == "paid"
    assert r2.json()["status"] == "paid"


def test_status_failed_when_yookassa_canceled(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "canceled"

    with patch("yookassa.Payment") as MockPayment, \
         patch("yookassa.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_status_404_for_unknown_order(client):
    r = client.get("/api/guest-orders/99999/status")
    assert r.status_code == 404
