"""Integration: вход по СМС-коду."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def test_request_code_returns_200_and_stub_stores_code(client):
    from services import sms
    sms._reset_for_tests()
    resp = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert resp.status_code == 200
    gw = sms.get_gateway()
    assert "+79991234567" in gw.last_codes


def test_verify_code_returns_jwt(client):
    from services import sms
    sms._reset_for_tests()
    client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    gw = sms.get_gateway()
    code = gw.last_codes["+79991234567"]
    resp = client.post("/api/auth/phone/verify", json={"phone": "+79991234567", "code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"


def test_verify_wrong_code_returns_400(client):
    from services import sms
    sms._reset_for_tests()
    client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    resp = client.post("/api/auth/phone/verify", json={"phone": "+79991234567", "code": "000000"})
    assert resp.status_code == 400


def test_request_code_cooldown_returns_429(client):
    from services import sms
    sms._reset_for_tests()
    r1 = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert r2.status_code == 429


def test_invalid_phone_returns_400(client):
    resp = client.post("/api/auth/phone/request-code", json={"phone": "not-a-phone"})
    assert resp.status_code == 400


def test_verify_creates_user_with_verified_phone_provider(client, tmp_db):
    """После успешного verify в auth_providers есть запись с provider='phone' verified=1."""
    import sqlite3
    from services import sms
    sms._reset_for_tests()
    client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    gw = sms.get_gateway()
    code = gw.last_codes["+79991234567"]
    client.post("/api/auth/phone/verify", json={"phone": "+79991234567", "code": code})
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row is not None
    assert row[1] == 1  # verified
