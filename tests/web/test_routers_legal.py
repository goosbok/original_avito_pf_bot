"""Tests for /privacy and /offer static legal pages."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    from web.main import app
    return TestClient(app)


def test_privacy_returns_200_html(client):
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Политика конфиденциальности" in r.text


def test_offer_returns_200_html(client):
    r = client.get("/offer")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Публичная оферта" in r.text


def test_privacy_sets_cache_control(client):
    r = client.get("/privacy")
    assert "max-age=300" in r.headers.get("cache-control", "")


def test_offer_sets_cache_control(client):
    r = client.get("/offer")
    assert "max-age=300" in r.headers.get("cache-control", "")
