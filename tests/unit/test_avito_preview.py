"""Unit tests for services.avito_preview parsing & URL building.

Network is never touched here — we mock httpx.AsyncClient. The tests assert:
- regex extracts og:image and og:image:alt from real-shape HTML;
- fetch_previews returns one dict per input URL, preserving order;
- fetch_failed / not_found statuses are produced on the right inputs;
- the proxy URL is built correctly (path arg, X-Pf-Secret header).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services import avito_preview


SAMPLE_HTML = """
<html><head>
<meta data-rh="true" property="og:image" content="https://www.avito.ru/img/share/auto/50528771800" />
<meta data-rh="true" property="og:image:alt" content="iPhone 14 Pro Max, 1 ТБ" />
<meta data-rh="true" property="og:title" content="SEO long title" />
</head></html>
"""


def test_parse_og_extracts_image_and_alt():
    image, title = avito_preview._parse_og(SAMPLE_HTML)
    assert image == "https://www.avito.ru/img/share/auto/50528771800"
    assert title == "iPhone 14 Pro Max, 1 ТБ"


def test_parse_og_returns_none_when_missing():
    image, title = avito_preview._parse_og("<html><head></head></html>")
    assert image is None
    assert title is None


def test_proxy_params_preserves_query_string():
    """CDN signed URLs carry `?cqp=...` — nginx needs the full path-with-query."""
    p = avito_preview._proxy_params("https://www.avito.ru/img/share/auto/123?cqp=sig&t=1")
    assert p == {"path": "/img/share/auto/123?cqp=sig&t=1"}


def test_proxy_params_handles_no_query():
    """Path-only URLs don't get a trailing '?'."""
    p = avito_preview._proxy_params("https://www.avito.ru/ekaterinburg/telefony/iphone")
    assert p == {"path": "/ekaterinburg/telefony/iphone"}


def test_proxy_headers_returns_shared_secret():
    """Header is required for nginx auth — empty default still produces the key."""
    from data import config

    h = avito_preview._proxy_headers()
    assert "X-Pf-Secret" in h
    assert h["X-Pf-Secret"] == config.AVITO_PROXY_SECRET


@pytest.mark.asyncio
async def test_fetch_preview_ok():
    """Happy path: GET returns og:image, HEAD returns 301 Location to CDN."""
    client = AsyncMock()
    html_resp = MagicMock(status_code=200, text=SAMPLE_HTML)
    head_resp = MagicMock(
        status_code=301,
        headers={"location": "https://00.img.avito.st/image/1/abc?cqp=sig"},
    )
    client.get = AsyncMock(return_value=html_resp)
    client.head = AsyncMock(return_value=head_resp)

    result = await avito_preview._fetch_one(
        "https://www.avito.ru/ekaterinburg/telefony/iphone_14_pro_max_1_tb_7868289489",
        client,
    )

    assert result["status"] == "ok"
    assert result["title"] == "iPhone 14 Pro Max, 1 ТБ"
    assert result["image_url"] == "https://00.img.avito.st/image/1/abc?cqp=sig"
    assert result["url"].endswith("7868289489")


@pytest.mark.asyncio
async def test_fetch_preview_html_non_200_returns_fetch_failed():
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=502, text=""))

    result = await avito_preview._fetch_one("https://www.avito.ru/x", client)

    assert result["status"] == "fetch_failed"
    assert result["image_url"] is None
    assert result["title"] is None


@pytest.mark.asyncio
async def test_fetch_preview_no_og_image_returns_not_found():
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=MagicMock(status_code=200, text="<html><head></head></html>")
    )

    result = await avito_preview._fetch_one("https://www.avito.ru/x", client)

    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_fetch_preview_head_no_redirect_keeps_og_image():
    """If HEAD doesn't redirect (200 with no Location), keep the share URL as-is."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200, text=SAMPLE_HTML))
    client.head = AsyncMock(return_value=MagicMock(status_code=200, headers={}))

    result = await avito_preview._fetch_one("https://www.avito.ru/x", client)

    assert result["image_url"] == "https://www.avito.ru/img/share/auto/50528771800"


@pytest.mark.asyncio
async def test_fetch_previews_preserves_order_and_handles_per_url_errors():
    urls = [
        "https://www.avito.ru/ok",
        "https://www.avito.ru/bad",
    ]

    async def fake_fetch(url, client):
        if "bad" in url:
            return {"url": url, "status": "fetch_failed", "image_url": None, "title": None}
        return {"url": url, "status": "ok", "image_url": "https://cdn/img.jpg", "title": "OK"}

    with patch.object(avito_preview, "_fetch_one", side_effect=fake_fetch):
        results = await avito_preview.fetch_previews(urls)

    assert [r["url"] for r in results] == urls
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "fetch_failed"
