"""Integration: POST /api/orders/pf → POST /pay → проверка статуса."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    # Гарантируем «yookassa включён» для тестов — payment_probe.is_yookassa_enabled
    # читает SHOP_ID/SECRET_KEY из data.config; в conftest стабе SHOP_ID=0.
    monkeypatch.setattr("services.payment_probe.SHOP_ID", 12345, raising=False)
    monkeypatch.setattr("services.payment_probe.SECRET_KEY", "test_secret", raising=False)
    from web.main import app
    return TestClient(app)


@pytest.fixture
def authed_client(client, tmp_db, monkeypatch):
    """TestClient + JWT-токен в Authorization для default-юзера."""
    from services import auth_email
    uid = auth_email.register("user@example.com", "password123", first_name="User")
    from web.auth import create_jwt
    token = create_jwt(uid)
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.user_id = uid  # type: ignore[attr-defined]
    return client


@pytest.fixture
def db_user_with_balance(authed_client, tmp_db):
    """Возвращает функцию, которая (опционально) выставляет balance и возвращает uid."""
    def _set(balance: int) -> int:
        from services.db import connect
        uid = authed_client.user_id  # type: ignore[attr-defined]
        with connect() as con:
            con.execute("UPDATE users SET balance = ? WHERE id = ?", (balance, uid))
            con.commit()
        return uid
    return _set


def test_authorized_user_creates_unpaid_and_pays_with_balance(
    authed_client, db_user_with_balance, monkeypatch
):
    db_user_with_balance(balance=1000)
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    resp = authed_client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    oid = data["order_id"]
    assert "balance" in data["available_methods"]
    assert "yookassa" in data["available_methods"]

    resp = authed_client.post(f"/api/orders/pf/{oid}/pay", json={"method": "balance"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paid"


def test_guest_with_phone_only_sees_yookassa_method_only(client, monkeypatch):
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)
    resp = client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
        "phone": "+79991234567",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["available_methods"] == ["yookassa"]


def test_guest_without_phone_gets_400(client, monkeypatch):
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)
    resp = client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
    })
    assert resp.status_code == 400, resp.text


def test_missing_privacy_consent_returns_400(authed_client, monkeypatch):
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)
    resp = authed_client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": False, "agreed_offer": True,
    })
    assert resp.status_code == 400, resp.text
