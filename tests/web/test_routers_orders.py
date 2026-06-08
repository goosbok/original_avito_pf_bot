"""Tests for /api/orders endpoints.

Покрывает «классические» эндпоинты роутера:
- GET /api/orders/pf/price (public)
- GET /api/orders (auth required)
- POST /api/orders/pf — новый unpaid-flow (создание + список доступных методов)

Полный flow создание → оплата → polling статуса лежит в
`test_order_pf_flow.py` — здесь только базовые проверки маршрутизации/валидации.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    # yookassa нужен для available_methods (см. comment в test_order_pf_flow).
    monkeypatch.setattr("services.payment_probe.SHOP_ID", 12345, raising=False)
    monkeypatch.setattr("services.payment_probe.SECRET_KEY", "test_secret", raising=False)
    from services import auth_email
    uid = auth_email.register("user@example.com", "password123", first_name="User")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    client = TestClient(app)
    return client, uid, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_with_balance(authed, tmp_db):
    client, uid, headers = authed
    from services.db import connect
    with connect() as con:
        con.execute("UPDATE users SET balance = 10000 WHERE id = ?", (uid,))
        con.commit()
    return client, uid, headers


def test_get_pf_price_no_auth(authed):
    client, _, _ = authed
    r = client.get("/api/orders/pf/price")
    assert r.status_code == 200
    body = r.json()
    assert "price_per_unit" in body
    assert isinstance(body["price_per_unit"], int)
    assert body["price_per_unit"] >= 1


def test_list_orders_empty(authed):
    client, _, headers = authed
    r = client.get("/api/orders", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


def test_list_orders_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/orders")
    assert r.status_code == 401


def test_create_pf_unpaid_returns_methods(authed_with_balance, monkeypatch):
    client, _, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://www.avito.ru/item/123"],
            "days": 3,
            "fix_count": 5,
            "contacts": False,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["order_id"] > 0
    # 1 * 5 * 3 * 1
    assert body["price"] == 15
    assert "balance" in body["available_methods"]
    assert "yookassa" in body["available_methods"]


def test_create_pf_no_balance_but_yookassa_available(authed, monkeypatch):
    client, _, headers = authed
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 9999999)

    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://www.avito.ru/item/123"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    # Юзер без баланса всё равно может создать unpaid и оплатить yookassa.
    assert r.status_code == 201, r.text
    body = r.json()
    assert "balance" not in body["available_methods"]
    assert "yookassa" in body["available_methods"]


def test_create_pf_order_invalid_link(authed_with_balance):
    client, _, headers = authed_with_balance
    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://www.example.com/not-avito"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    assert r.status_code == 422


def test_create_pf_order_rejects_avito_substring_in_query(authed_with_balance):
    """Defense-in-depth: don't allow a non-avito host with avito.ru in the query."""
    client, _, headers = authed_with_balance
    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://evil.com/?ref=avito.ru"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    assert r.status_code == 422


def test_create_pf_order_rejects_avito_subdomain_prefix(authed_with_balance):
    """Defense-in-depth: don't allow a domain that just starts with avito.ru.*."""
    client, _, headers = authed_with_balance
    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://avito.ru.evil.com/x"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    assert r.status_code == 422


def test_list_orders_after_create(authed_with_balance, monkeypatch):
    client, _, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    r = client.post(
        "/api/orders/pf",
        headers=headers,
        json={
            "links": ["https://www.avito.ru/item/1", "https://www.avito.ru/item/2"],
            "days": 2,
            "fix_count": 5,
            "contacts": True,
            "agreed_privacy": True,
            "agreed_offer": True,
        },
    )
    assert r.status_code == 201, r.text

    r = client.get("/api/orders", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["price"] == 1 * 5 * 2 * 2


def test_list_orders_pagination(authed_with_balance, monkeypatch):
    client, _, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    for _ in range(5):
        client.post(
            "/api/orders/pf",
            headers=headers,
            json={
                "links": ["https://www.avito.ru/item/1"],
                "days": 1,
                "fix_count": 5,
                "contacts": False,
                "agreed_privacy": True,
                "agreed_offer": True,
            },
        )

    r = client.get("/api/orders?page=1&page_size=3", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["page"] == 1

    r2 = client.get("/api/orders?page=2&page_size=3", headers=headers)
    body2 = r2.json()
    assert len(body2["items"]) == 2
