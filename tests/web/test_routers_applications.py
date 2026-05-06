from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("dev@example.com", "password123")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    return TestClient(app), uid, {"Authorization": f"Bearer {token}"}


def test_create_app_returns_plaintext_key(authed):
    client, _, headers = authed
    r = client.post("/api/applications", json={"name": "MyBot"}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "MyBot"
    assert body["api_key"].startswith("sk_live_")
    assert "api_key_prefix" in body


def test_list_apps_returns_created(authed):
    client, _, headers = authed
    client.post("/api/applications", json={"name": "App1"}, headers=headers)
    client.post("/api/applications", json={"name": "App2"}, headers=headers)
    r = client.get("/api/applications", headers=headers)
    assert r.status_code == 200
    names = {a["name"] for a in r.json()}
    assert {"App1", "App2"} <= names


def test_revoke_app_returns_204(authed):
    client, _, headers = authed
    r = client.post("/api/applications", json={"name": "TempApp"}, headers=headers)
    app_id = r.json()["id"]
    r2 = client.delete(f"/api/applications/{app_id}", headers=headers)
    assert r2.status_code == 204


def test_revoke_unowned_app_404(authed, tmp_db: Path, monkeypatch):
    client, _, _ = authed
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid_b = auth_email.register("other@example.com", "password123")
    from web.auth import create_jwt
    headers_b = {"Authorization": f"Bearer {create_jwt(uid_b)}"}
    r = client.post("/api/applications", json={"name": "OtherApp"}, headers=headers_b)
    app_id = r.json()["id"]
    # Try to revoke with user_a's token
    _, _, headers_a = authed
    r2 = client.delete(f"/api/applications/{app_id}", headers=headers_a)
    assert r2.status_code == 404


def test_create_requires_auth(authed):
    client, _, _ = authed
    r = client.post("/api/applications", json={"name": "NoAuth"})
    assert r.status_code == 401
