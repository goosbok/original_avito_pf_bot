import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.routers.auth.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.routers.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.deps.JWT_SECRET", "x" * 32)

    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 0, "2026-05-02"),
        )
        con.commit()

    from web.auth import create_jwt
    token = create_jwt(user_id=42, secret="x" * 32)

    from web.main import app
    client = TestClient(app)
    return SimpleNamespace(
        client=client, token=token,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_create_refill_returns_payment_url(authed) -> None:
    with patch(
        "web.routers.refill.create_invoice",
        return_value=("https://pay/aaa", "pay-1"),
    ):
        response = authed.client.post(
            "/api/refill", json={"amount": 500}, headers=authed.headers,
        )
    assert response.status_code == 200
    assert response.json() == {"payment_id": "pay-1", "payment_url": "https://pay/aaa"}


def test_create_refill_requires_positive_amount(authed) -> None:
    response = authed.client.post(
        "/api/refill", json={"amount": 0}, headers=authed.headers,
    )
    assert response.status_code == 422


def test_create_refill_requires_auth(authed) -> None:
    response = authed.client.post("/api/refill", json={"amount": 500})
    assert response.status_code == 401


def test_status_pending_does_not_credit(authed, tmp_db: Path) -> None:
    fake_payment = SimpleNamespace(status="pending", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake_payment):
        response = authed.client.get(
            "/api/refill/pay-X/status", headers=authed.headers,
        )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("SELECT * FROM refills").fetchall()
    assert rows == []


def test_status_succeeded_credits_balance_idempotent(authed, tmp_db: Path) -> None:
    fake_payment = SimpleNamespace(status="succeeded", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake_payment):
        r1 = authed.client.get("/api/refill/pay-Y/status", headers=authed.headers)
        r2 = authed.client.get("/api/refill/pay-Y/status", headers=authed.headers)

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["status"] == "succeeded"
    assert r2.json()["status"] == "succeeded"

    with sqlite3.connect(tmp_db) as con:
        balance = con.execute("SELECT balance FROM users WHERE id = 42").fetchone()[0]
        refills = con.execute("SELECT amount, payment_id FROM refills").fetchall()
    assert balance == 500
    assert refills == [(500, "pay-Y")]


def test_status_failed_for_canceled(authed) -> None:
    fake = SimpleNamespace(status="canceled", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake):
        response = authed.client.get("/api/refill/pay-Z/status", headers=authed.headers)
    assert response.json()["status"] == "failed"
