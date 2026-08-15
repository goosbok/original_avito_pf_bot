from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("me@example.com", "password123", first_name="Me")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    return TestClient(app), uid, {"Authorization": f"Bearer {token}"}


def test_me_returns_profile(authed):
    client, uid, headers = authed
    r = client.get("/api/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == uid
    assert body["first_name"] == "Me"
    assert body["balance"] == 0


def test_me_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/me")
    assert r.status_code == 401


def test_providers_lists_email(authed):
    client, _, headers = authed
    r = client.get("/api/me/providers", headers=headers)
    assert r.status_code == 200
    providers = r.json()
    assert any(p["provider"] == "email" for p in providers)
