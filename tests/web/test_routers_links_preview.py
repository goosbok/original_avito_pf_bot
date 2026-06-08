"""Tests for POST /api/orders/links/preview.

Mocks services.avito_preview.fetch_previews to avoid real network in CI.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    from web.main import app
    return TestClient(app)


def test_preview_happy_path(client):
    """One ok URL, one fetch_failed URL — both returned in input order."""
    fake = AsyncMock(return_value=[
        {"url": "https://www.avito.ru/a", "status": "ok",
         "image_url": "https://cdn/a.jpg", "title": "Phone A"},
        {"url": "https://www.avito.ru/b", "status": "fetch_failed",
         "image_url": None, "title": None},
    ])
    with patch("web.routers.orders.fetch_previews", fake):
        resp = client.post(
            "/api/orders/links/preview",
            json={"urls": ["https://www.avito.ru/a", "https://www.avito.ru/b"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["previews"]) == 2
    assert body["previews"][0]["status"] == "ok"
    assert body["previews"][0]["title"] == "Phone A"
    assert body["previews"][1]["status"] == "fetch_failed"


def test_preview_rejects_non_avito_url(client):
    resp = client.post(
        "/api/orders/links/preview",
        json={"urls": ["https://example.com/x"]},
    )
    assert resp.status_code == 422


def test_preview_rejects_empty_list(client):
    resp = client.post("/api/orders/links/preview", json={"urls": []})
    assert resp.status_code == 422


def test_preview_rejects_over_20_urls(client):
    urls = [f"https://www.avito.ru/x{i}" for i in range(21)]
    resp = client.post("/api/orders/links/preview", json={"urls": urls})
    assert resp.status_code == 422
