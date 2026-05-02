import hashlib
import hmac
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("web.config.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.routers.auth.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.routers.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.deps.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def _signed_widget_data(bot_token: str, user_id: int) -> dict:
    data = {"id": user_id, "first_name": "T", "auth_date": int(time.time())}
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return data


def test_telegram_login_returns_jwt(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    response = client.post("/api/auth/telegram", json=data)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20


def test_telegram_login_rejects_bad_signature(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    data["hash"] = "0" * 64
    response = client.post("/api/auth/telegram", json=data)
    assert response.status_code == 401


def test_me_returns_404_when_user_not_in_db(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    token = client.post("/api/auth/telegram", json=data).json()["access_token"]
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_me_returns_profile(client: TestClient, tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 1500, "2026-05-02"),
        )
        con.commit()

    data = _signed_widget_data("1234:dummy", user_id=42)
    token = client.post("/api/auth/telegram", json=data).json()["access_token"]
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": 42,
        "user_name": "tester",
        "first_name": "Test",
        "balance": 1500,
    }


def test_me_requires_auth(client: TestClient) -> None:
    response = client.get("/api/me")
    assert response.status_code == 401
