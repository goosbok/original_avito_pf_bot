"""Tests for email registration and login endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    """Create a test client with JWT secret monkeypatched."""
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def test_register_returns_jwt(client):
    """Test successful registration returns a JWT token."""
    r = client.post("/api/auth/email/register", json={
        "email": "alice@example.com",
        "password": "password123",
        "first_name": "Alice",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_register_duplicate_email_409(client):
    """Test registering with duplicate email returns 409."""
    payload = {"email": "dup@example.com", "password": "password123"}
    client.post("/api/auth/email/register", json=payload).raise_for_status()
    r = client.post("/api/auth/email/register", json=payload)
    assert r.status_code == 409


def test_register_invalid_email_422(client):
    """Test registering with invalid email returns 422."""
    r = client.post("/api/auth/email/register", json={
        "email": "not-an-email", "password": "password123",
    })
    assert r.status_code == 422  # pydantic validation


def test_register_short_password_422(client):
    """Test registering with short password returns 422."""
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com", "password": "short",
    })
    assert r.status_code == 422


def test_login_success(client):
    """Test successful login returns a JWT token."""
    client.post("/api/auth/email/register", json={
        "email": "login@example.com", "password": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "login@example.com", "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_401(client):
    """Test login with wrong password returns 401."""
    client.post("/api/auth/email/register", json={
        "email": "user@example.com", "password": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "user@example.com", "password": "wrongpass",
    })
    assert r.status_code == 401


def test_login_unknown_email_401(client):
    """Test login with unknown email returns 401."""
    r = client.post("/api/auth/email/login", json={
        "email": "nobody@example.com", "password": "password123",
    })
    assert r.status_code == 401
