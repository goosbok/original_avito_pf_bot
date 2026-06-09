"""Fetch Avito ad preview meta (og:image + og:image:alt) for the order form.

All requests go through the RU-VPS proxy (`AVITO_PROXY_URL`) because Avito
blocks Hetzner/datacenter egress with 403. The proxy is an nginx location
with hardcoded upstream `www.avito.ru` and a shared-secret header check
(`X-Pf-Secret`). See `infra-pf-bot-domain` memory + the deploy task in this plan.

Result is consumed only by the order-create form for one session — no DB cache.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from data.config import AVITO_PROXY_SECRET, AVITO_PROXY_URL

logger = logging.getLogger(__name__)

# Concurrency cap so a single 20-link form doesn't fan out 20 simultaneous
# requests to Avito through the proxy. 5 keeps wall-clock low while staying
# polite — Avito anti-bot doesn't flag this volume from one residential IP.
_CONCURRENCY = 5

_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)

# Regex-only parsing — BS4 is not a project dep and og: tags have a stable shape
# in Avito's React-rendered HTML.
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', re.IGNORECASE
)
# Avito puts the `content=` attribute on either side of `property=`, so we also
# match the inverse order.
_OG_IMAGE_RE_INV = re.compile(
    r'<meta[^>]*content="([^"]+)"[^>]*property="og:image"', re.IGNORECASE
)
_OG_IMAGE_ALT_RE = re.compile(
    r'<meta[^>]*property="og:image:alt"[^>]*content="([^"]+)"', re.IGNORECASE
)
_OG_IMAGE_ALT_RE_INV = re.compile(
    r'<meta[^>]*content="([^"]+)"[^>]*property="og:image:alt"', re.IGNORECASE
)


def _parse_og(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (og:image, og:image:alt) from Avito's HTML. Returns (None, None) if missing."""
    img_match = _OG_IMAGE_RE.search(html) or _OG_IMAGE_RE_INV.search(html)
    alt_match = _OG_IMAGE_ALT_RE.search(html) or _OG_IMAGE_ALT_RE_INV.search(html)
    image = img_match.group(1) if img_match else None
    title = alt_match.group(1) if alt_match else None
    return image, title


def _proxy_url(target_url: str) -> str:
    """Build full proxy URL for the nginx location (`/_internal/avito-fetch`).

    We build the URL as a STRING (not via httpx `params=`) on purpose: httpx
    percent-encodes `/` in query values to `%2F`, which our nginx regex check
    (`^/[A-Za-z0-9._/?&=%~,+:!*'()@$;-]+$`) then rejects with 400. Passing a
    pre-built URL keeps `/` literal.
    """
    parsed = urlparse(target_url)
    path_with_query = parsed.path
    if parsed.query:
        path_with_query += "?" + parsed.query
    return f"{AVITO_PROXY_URL}/_internal/avito-fetch?path={path_with_query}"


def _proxy_headers() -> dict:
    return {"X-Pf-Secret": AVITO_PROXY_SECRET}


async def _fetch_one(url: str, client: httpx.AsyncClient) -> dict:
    """Fetch preview for a single Avito URL. Always returns a result dict (never raises)."""
    base = {"url": url, "status": "fetch_failed", "image_url": None, "title": None}
    try:
        html_resp = await client.get(
            _proxy_url(url),
            headers=_proxy_headers(),
        )
        if html_resp.status_code != 200:
            logger.info("avito preview: html status=%s url=%s", html_resp.status_code, url)
            return base
        image, title = _parse_og(html_resp.text)
        if not image:
            base["status"] = "not_found"
            return base
        # Resolve the 301 from /img/share/auto/{id} → CDN URL so the browser
        # loads the JPEG in one hop instead of two.
        cdn_url = image
        try:
            head_resp = await client.head(
                _proxy_url(image),
                headers=_proxy_headers(),
            )
            if 300 <= head_resp.status_code < 400:
                location = head_resp.headers.get("location")
                if location:
                    cdn_url = location
        except (httpx.HTTPError, asyncio.TimeoutError):
            # HEAD optimization is best-effort — if it fails, the share URL still
            # works (browser will follow 301 itself).
            logger.info("avito preview: HEAD failed for og:image, falling back", exc_info=True)
        return {"url": url, "status": "ok", "image_url": cdn_url, "title": title}
    except (httpx.HTTPError, asyncio.TimeoutError):
        logger.info("avito preview: fetch failed url=%s", url, exc_info=True)
        return base


async def fetch_previews(urls: list[str]) -> list[dict]:
    """Fetch previews for many URLs concurrently (capped). Order is preserved.

    Result shape per URL:
        {"url": str, "status": "ok"|"not_found"|"fetch_failed",
         "image_url": str|None, "title": str|None}
    """
    if not urls:
        return []
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        async def _bounded(u: str) -> dict:
            async with sem:
                return await _fetch_one(u, client)

        return await asyncio.gather(*[_bounded(u) for u in urls])
