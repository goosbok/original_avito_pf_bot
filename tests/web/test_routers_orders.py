"""Tests for /api/orders and /api/orders/pf endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
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


def test_create_pf_order_success(authed_with_balance, monkeypatch):
    client, uid, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/123"],
        "days": 3,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["order_id"] > 0
    assert body["total_price"] == 1 * 5 * 3 * 1
    assert body["status"] == "Posted"


def test_create_pf_order_insufficient_balance(authed, monkeypatch):
    client, _, headers = authed
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 9999999)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/123"],
        "days": 1,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 402


def test_create_pf_order_invalid_link(authed_with_balance):
    client, _, headers = authed_with_balance
    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.example.com/not-avito"],
        "days": 1,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 422


def test_list_orders_after_create(authed_with_balance, monkeypatch):
    client, uid, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/1", "https://www.avito.ru/item/2"],
        "days": 2,
        "fix_count": 5,
        "contacts": True,
    })

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

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    for _ in range(5):
        client.post("/api/orders/pf", headers=headers, json={
            "links": ["https://www.avito.ru/item/1"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
        })

    r = client.get("/api/orders?page=1&page_size=3", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["page"] == 1

    r2 = client.get("/api/orders?page=2&page_size=3", headers=headers)
    body2 = r2.json()
    assert len(body2["items"]) == 2
