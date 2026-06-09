# Avito Link Preview Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain text list of pasted Avito links in the order creation form with rich preview cards (thumbnail + ad title + URL), so users see what they're about to order.

**Architecture:** Frontend (`OrderForm.jsx`) sends newly-added URLs to a backend endpoint `POST /api/orders/links/preview`. Backend calls Avito HTML through an internal nginx-proxy location on the existing RU-VPS (`139.28.222.146`, Moscow, already running `lk.pf-bot.com`), because Avito blocks Hetzner/datacenter IPs (403) but returns 200 to RU IPs. The backend parses `og:image` + `og:image:alt` from the HTML (regex, no BS4) and resolves the 301 to a CDN URL via HEAD. Result is in-memory only — no DB cache, no migration, no expiry. The user's browser then loads the actual JPEG directly from `*.img.avito.st` via `<img src>`.

**Tech Stack:** Python 3 + FastAPI + httpx (async) + Pydantic v2 (backend); vanilla React via Babel-standalone (frontend); nginx 1.24 (RU-VPS proxy).

---

## File Structure

**Backend:**
- Create: `services/avito_preview.py` — async fetch + parse module, depends only on httpx + stdlib `re`.
- Modify: `web/schemas.py` — add `LinkPreviewRequest`, `LinkPreviewItem`, `LinkPreviewResponse`.
- Modify: `web/routers/orders.py` — add `POST /api/orders/links/preview` endpoint (public, like the order create endpoint).
- Modify: `data/config.py` — add `AVITO_PROXY_URL`, `AVITO_PROXY_SECRET` env vars.

**Frontend:**
- Create: `web/static/components/LinkCard.jsx` — single card component (replaces `AddedLinksList`).
- Modify: `web/static/components/OrderForm.jsx` — replace `<AddedLinksList>` usage, add `linkMeta` Map state, fire preview batch on URL add.
- Modify: `web/static/index.html` — add `<script>` tag for the new component, remove the one for `AddedLinksList`.
- Delete: `web/static/components/AddedLinksList.jsx` — fully replaced.

**Infra (RU-VPS):**
- Modify on RU-VPS: `/etc/nginx/sites-available/pf-bot.com` — new `location = /_internal/avito-fetch` block inside the `server { server_name lk.pf-bot.com; ... }` block.

**Tests:**
- Create: `tests/unit/test_avito_preview.py` — unit test for `services/avito_preview.py` parsing logic (regex og: extraction, no real network).
- Create: `tests/web/test_routers_links_preview.py` — endpoint test with `services.avito_preview.fetch_previews` mocked.

---

## Task 1: Backend config — env vars for proxy URL and secret

**Files:**
- Modify: `data/config.py`

- [ ] **Step 1: Add env var declarations**

Open `data/config.py` and add the following lines next to the other `os.getenv(...)` declarations (e.g. right after the `SUPPORT_THREAD_QUESTIONS` line — the exact location does not affect behavior):

```python
# Avito link-preview proxy on the RU-VPS (139.28.222.146).
# Bypass: Avito blocks Hetzner egress (403) but the RU-VPS sits in Moscow and gets 200.
# The proxy is a single nginx location with a shared-secret header check.
AVITO_PROXY_URL: str = os.getenv("AVITO_PROXY_URL", "https://lk.pf-bot.com")
AVITO_PROXY_SECRET: str = os.getenv("AVITO_PROXY_SECRET", "")
```

- [ ] **Step 2: Commit**

```bash
git add data/config.py
git commit -m "feat(config): env vars for Avito preview proxy"
```

---

## Task 2: Backend service — `services/avito_preview.py`

**Files:**
- Create: `services/avito_preview.py`
- Create: `tests/unit/test_avito_preview.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_avito_preview.py`:

```python
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


SAMPLE_HTML = b"""
<html><head>
<meta data-rh="true" property="og:image" content="https://www.avito.ru/img/share/auto/50528771800" />
<meta data-rh="true" property="og:image:alt" content="iPhone 14 Pro Max, 1 ТБ" />
<meta data-rh="true" property="og:title" content="SEO long title" />
</head></html>
""".decode("utf-8")


def test_parse_og_extracts_image_and_alt():
    image, title = avito_preview._parse_og(SAMPLE_HTML)
    assert image == "https://www.avito.ru/img/share/auto/50528771800"
    assert title == "iPhone 14 Pro Max, 1 ТБ"


def test_parse_og_returns_none_when_missing():
    image, title = avito_preview._parse_og("<html><head></head></html>")
    assert image is None
    assert title is None


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
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_avito_preview.py -v
```

Expected: ImportError for `services.avito_preview` (module does not exist yet).

- [ ] **Step 3: Implement `services/avito_preview.py`**

Create `services/avito_preview.py`:

```python
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


def _proxy_params(target_url: str) -> dict:
    """Build query string for the nginx proxy location (`/_internal/avito-fetch`)."""
    parsed = urlparse(target_url)
    # Reassemble path + query into a single string the nginx side will append to
    # `https://www.avito.ru`. CDN signed URLs carry `?cqp=...` so we MUST preserve
    # the query — nginx-side `$arg_path` only captures up to first '?', so we send
    # the path-with-query as a separate header instead.
    path_with_query = parsed.path
    if parsed.query:
        path_with_query += "?" + parsed.query
    return {"path": path_with_query}


def _proxy_headers() -> dict:
    return {"X-Pf-Secret": AVITO_PROXY_SECRET}


async def _fetch_one(url: str, client: httpx.AsyncClient) -> dict:
    """Fetch preview for a single Avito URL. Always returns a result dict (never raises)."""
    base = {"url": url, "status": "fetch_failed", "image_url": None, "title": None}
    try:
        html_resp = await client.get(
            f"{AVITO_PROXY_URL}/_internal/avito-fetch",
            params=_proxy_params(url),
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
                f"{AVITO_PROXY_URL}/_internal/avito-fetch",
                params=_proxy_params(image),
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
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_avito_preview.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/avito_preview.py tests/unit/test_avito_preview.py
git commit -m "feat(preview): async Avito og:image fetcher via RU-VPS proxy"
```

---

## Task 3: API endpoint — `POST /api/orders/links/preview`

**Files:**
- Modify: `web/schemas.py` (add new request/response models)
- Modify: `web/routers/orders.py` (add new endpoint)
- Create: `tests/web/test_routers_links_preview.py`

- [ ] **Step 1: Add the Pydantic schemas**

In `web/schemas.py`, add right after the `PFOrderResponse` class (around line 175):

```python
class LinkPreviewRequest(BaseModel):
    """Batch request: parse preview meta for up to 20 Avito URLs."""
    urls: list[str] = Field(..., min_length=1, max_length=20)

    @field_validator("urls")
    @classmethod
    def urls_must_be_avito(cls, v: list[str]) -> list[str]:
        for u in v:
            if not _re.search(r'avito\.ru', u):
                raise ValueError(f"invalid avito link: {u}")
        return v


class LinkPreviewItem(BaseModel):
    url: str
    status: Literal["ok", "not_found", "fetch_failed"]
    image_url: Optional[str] = None
    title: Optional[str] = None


class LinkPreviewResponse(BaseModel):
    previews: list[LinkPreviewItem]
```

- [ ] **Step 2: Write the failing endpoint test**

Create `tests/web/test_routers_links_preview.py`:

```python
"""Tests for POST /api/orders/links/preview.

Mocks services.avito_preview.fetch_previews to avoid real network in CI.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_preview_happy_path(client):
    """One ok URL, one fetch_failed URL — both returned in input order."""
    fake = AsyncMock(return_value=[
        {"url": "https://www.avito.ru/a", "status": "ok",
         "image_url": "https://cdn/a.jpg", "title": "Phone A"},
        {"url": "https://www.avito.ru/b", "status": "fetch_failed",
         "image_url": None, "title": None},
    ])
    with patch("web.routers.orders.fetch_previews", fake):
        resp = await client.post(
            "/api/orders/links/preview",
            json={"urls": ["https://www.avito.ru/a", "https://www.avito.ru/b"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["previews"]) == 2
    assert body["previews"][0]["status"] == "ok"
    assert body["previews"][0]["title"] == "Phone A"
    assert body["previews"][1]["status"] == "fetch_failed"


@pytest.mark.asyncio
async def test_preview_rejects_non_avito_url(client):
    resp = await client.post(
        "/api/orders/links/preview",
        json={"urls": ["https://example.com/x"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_rejects_empty_list(client):
    resp = await client.post("/api/orders/links/preview", json={"urls": []})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_rejects_over_20_urls(client):
    urls = [f"https://www.avito.ru/x{i}" for i in range(21)]
    resp = await client.post("/api/orders/links/preview", json={"urls": urls})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
docker compose --profile test run --rm test pytest tests/web/test_routers_links_preview.py -v
```

Expected: 404 from FastAPI for unknown path, OR import-error if `fetch_previews` isn't imported in `web.routers.orders` yet. Either way: FAIL.

- [ ] **Step 4: Add the endpoint to `web/routers/orders.py`**

Add the import near the other service imports at the top of `web/routers/orders.py`:

```python
from services.avito_preview import fetch_previews
```

Add the new schema imports to the existing schemas import block in the same file:

```python
from web.schemas import (
    LinkPreviewRequest,
    LinkPreviewResponse,
    # ... other existing imports stay
)
```

Add the new endpoint (place it next to the other `@router.post(...)` for orders, e.g. right after `create_pf`):

```python
@router.post("/links/preview", response_model=LinkPreviewResponse)
async def preview_links(body: LinkPreviewRequest) -> LinkPreviewResponse:
    """Fetch og:image + og:image:alt for a batch of Avito URLs.

    Public endpoint — the order form is reachable to guests too. We don't
    rate-limit here (250 orders/day, sequential users, max 20 URLs each).
    """
    previews = await fetch_previews(list(body.urls))
    return LinkPreviewResponse(previews=previews)
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
docker compose --profile test run --rm test pytest tests/web/test_routers_links_preview.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add web/schemas.py web/routers/orders.py tests/web/test_routers_links_preview.py
git commit -m "feat(api): POST /api/orders/links/preview endpoint"
```

---

## Task 4: Nginx proxy on RU-VPS — `/_internal/avito-fetch`

This task touches the RU-VPS (`139.28.222.146`). It cannot be tested locally; verification is `curl`-based after deploy. Run these steps manually — do NOT run nginx commands from any subagent that doesn't have ssh access.

**Files:**
- Modify on RU-VPS: `/etc/nginx/sites-available/pf-bot.com`

- [ ] **Step 1: Generate a long shared secret**

```bash
openssl rand -hex 32
```

Save the value somewhere safe — you'll paste it into BOTH the nginx config AND the Hetzner `.env` (Task 7).

- [ ] **Step 2: SSH to RU-VPS and back up nginx config**

```bash
ssh root@139.28.222.146 'cp /etc/nginx/sites-available/pf-bot.com /etc/nginx/sites-available/pf-bot.com.bak-$(date +%Y%m%d)'
```

- [ ] **Step 3: Inspect the existing `lk.pf-bot.com` server block to find insertion point**

```bash
ssh root@139.28.222.146 'grep -nE "server_name lk\.pf-bot\.com|location " /etc/nginx/sites-available/pf-bot.com'
```

Note the line number of the `server_name lk.pf-bot.com;` block — the new `location` goes inside that block, BEFORE the catch-all `location /` that proxies to Hetzner.

- [ ] **Step 4: Add the new location block**

SSH in (`ssh root@139.28.222.146`) and edit `/etc/nginx/sites-available/pf-bot.com`. Inside the `server { ... server_name lk.pf-bot.com; ... }` block, ABOVE the existing `location / { proxy_pass https://167.233.52.85; ... }`, paste:

```nginx
    # ---- Avito link-preview proxy (internal-only) ----
    # Used by Hetzner backend to fetch Avito HTML (og:image) because Hetzner
    # egress is 403'd by Avito but this Moscow VPS is not. Shared-secret
    # header prevents abuse. See docs/superpowers/plans/2026-06-08-avito-link-preview-card.md
    location = /_internal/avito-fetch {
        if ($http_x_pf_secret != "PASTE_SECRET_HERE") { return 403; }
        if ($arg_path !~ "^/[A-Za-z0-9._/?&=%~,+:!*'()@$;-]+$") { return 400; }

        proxy_pass https://www.avito.ru$arg_path;
        proxy_set_header Host "www.avito.ru";
        proxy_set_header User-Agent "TelegramBot (like TwitterBot)";
        proxy_set_header Accept-Language "ru-RU,ru;q=0.9";
        proxy_set_header Accept-Encoding "gzip, br";
        proxy_ssl_server_name on;
        proxy_ssl_name "www.avito.ru";

        # Avito HTML can be ~750 KB — bump buffers so nginx doesn't spool to disk.
        proxy_buffers 16 64k;
        proxy_buffer_size 64k;
        proxy_busy_buffers_size 128k;

        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
        proxy_send_timeout 5s;

        # Don't leak upstream errors as HTML pages.
        proxy_intercept_errors off;

        # Strip cookies/auth from caller — internal endpoint, no need to forward.
        proxy_set_header Cookie "";
        proxy_set_header Authorization "";
    }
```

Replace `PASTE_SECRET_HERE` with the secret from Step 1.

- [ ] **Step 5: Validate nginx config**

```bash
ssh root@139.28.222.146 'nginx -t'
```

Expected: `nginx: configuration file ... test is successful`. If it fails, fix the syntax and re-run.

- [ ] **Step 6: Reload nginx**

```bash
ssh root@139.28.222.146 'systemctl reload nginx'
```

- [ ] **Step 7: Verify from outside — missing/wrong secret returns 403**

```bash
curl -sI "https://lk.pf-bot.com/_internal/avito-fetch?path=/ekaterinburg/telefony/iphone_14_pro_max_1_tb_7868289489" -o /dev/null -w "%{http_code}\n"
```

Expected: `403`.

- [ ] **Step 8: Verify from outside — correct secret + real Avito URL returns 200**

```bash
curl -sI -H "X-Pf-Secret: PASTE_SECRET_HERE" "https://lk.pf-bot.com/_internal/avito-fetch?path=/ekaterinburg/telefony/iphone_14_pro_max_1_tb_7868289489" -o /dev/null -w "%{http_code}\n"
```

Expected: `200`.

- [ ] **Step 9: Verify it returns Avito HTML with og:image**

```bash
curl -s -H "X-Pf-Secret: PASTE_SECRET_HERE" "https://lk.pf-bot.com/_internal/avito-fetch?path=/ekaterinburg/telefony/iphone_14_pro_max_1_tb_7868289489" | grep -oE 'property="og:image"[^>]*content="[^"]+"' | head -1
```

Expected: a line like `property="og:image" content="https://www.avito.ru/img/share/auto/50528771800"`.

- [ ] **Step 10: Save secret for Task 7**

Copy the secret value into your local notes or password manager. You'll need it again when configuring the Hetzner `.env`.

---

## Task 5: Frontend — `LinkCard.jsx` component

**Files:**
- Create: `web/static/components/LinkCard.jsx`
- Modify: `web/static/index.html`

- [ ] **Step 1: Create the component file**

Create `web/static/components/LinkCard.jsx`:

```jsx
// LinkCard — preview card for a pasted Avito URL.
// Replaces the plain text list (AddedLinksList) used previously in OrderForm.
//
// Props:
//   url     — the Avito URL (canonical, already trimmed by parseAvitoUrls)
//   meta    — { status: 'loading'|'ok'|'not_found'|'fetch_failed', image_url?, title? }
//   onRemove — callback when user clicks "×"
//
// States rendered:
//   loading           → skeleton thumb + shimmer title placeholder
//   ok                → <img> from image_url, title shown
//   not_found / fetch_failed → green "A" placeholder, fallback title = url path
function LinkCard({ url, meta, onRemove }) {
  const status = (meta && meta.status) || 'loading';
  const hasImage = status === 'ok' && meta && meta.image_url;
  const titleText = (meta && meta.title) || _urlShortPath(url);

  return (
    <div
      onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '8px 10px',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm, 8px)',
        marginBottom: 8,
        background: 'var(--surface)',
        cursor: 'pointer',
        minWidth: 0,
      }}
    >
      <div style={{
        width: 56, height: 56, borderRadius: 8, flexShrink: 0,
        overflow: 'hidden', position: 'relative',
        background: 'linear-gradient(135deg, #00aa00 0%, #007f00 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {status === 'loading' && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.25) 50%, transparent 100%)',
            animation: 'linkcard-shimmer 1.2s linear infinite',
          }} />
        )}
        {hasImage ? (
          <img
            src={meta.image_url}
            alt=""
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <span style={{
            color: 'white', fontWeight: 800, fontSize: '1.5rem',
            fontFamily: 'Georgia, "Times New Roman", serif',
            visibility: status === 'loading' ? 'hidden' : 'visible',
          }}>A</span>
        )}
      </div>
      <div style={{ flex: '1 1 0', minWidth: 0 }}>
        <div style={{
          fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-1)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          opacity: status === 'loading' ? 0.4 : 1,
        }}>
          {status === 'loading' ? ' ' : titleText}
        </div>
        <div title={url} style={{
          fontSize: '0.7rem', color: 'var(--text-3)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'monospace', marginTop: 2,
        }}>
          {_urlShortPath(url)}
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(url); }}
        aria-label="Удалить ссылку"
        style={{
          flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--status-cancel-text, #999)',
          fontWeight: 700, fontSize: '1.2rem', padding: '0 6px', lineHeight: 1,
        }}
      >−</button>
    </div>
  );
}

function _urlShortPath(url) {
  try {
    const u = new URL(url);
    return u.pathname.length > 50 ? u.pathname.slice(0, 50) + '…' : u.pathname;
  } catch (_) {
    return url;
  }
}

// Inject shimmer keyframes once.
(function _injectShimmerStyles() {
  if (document.getElementById('linkcard-shimmer-style')) return;
  const s = document.createElement('style');
  s.id = 'linkcard-shimmer-style';
  s.textContent = '@keyframes linkcard-shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }';
  document.head.appendChild(s);
})();

Object.assign(window, { LinkCard });
```

- [ ] **Step 2: Wire the new component into `index.html`**

Open `web/static/index.html` and find the line that loads `AddedLinksList.jsx`. It looks like:

```html
<script type="text/babel" data-presets="react" src="/static/components/AddedLinksList.jsx"></script>
```

Replace that line with:

```html
<script type="text/babel" data-presets="react" src="/static/components/LinkCard.jsx"></script>
```

- [ ] **Step 3: Commit**

```bash
git add web/static/components/LinkCard.jsx web/static/index.html
git commit -m "feat(ui): LinkCard component with thumbnail placeholder"
```

---

## Task 6: Frontend — wire preview fetch into `OrderForm.jsx`

**Files:**
- Modify: `web/static/components/OrderForm.jsx`
- Delete: `web/static/components/AddedLinksList.jsx`

- [ ] **Step 1: Add `linkMeta` state + preview-fetching effect**

Open `web/static/components/OrderForm.jsx`. Find the line where `links` is declared (around line 88):

```jsx
const [links, setLinks] = useOrderState(() => Array.isArray(prefilledFrom?.links) ? prefilledFrom.links : []);
```

Right after it, add:

```jsx
// Preview meta for each URL — survives removeLink so re-paste is instant.
// Shape: { [url]: { status: 'loading'|'ok'|'not_found'|'fetch_failed', image_url?, title? } }
const [linkMeta, setLinkMeta] = useOrderState({});
```

- [ ] **Step 2: Trigger batch preview fetch when new links arrive**

Find `handleInputChange` (around line 130). Replace its body so it also kicks off a preview request for newly-added URLs:

```jsx
const handleInputChange = e => {
  const val = e.target.value;
  const parsed = parseAvitoUrls(val);
  const toAdd = parsed.filter(u => !links.includes(u));
  if (toAdd.length) {
    setLinks(prev => [...prev, ...toAdd]);
    // Mark new URLs as loading (skip URLs we already have meta for — re-add case).
    const newlyLoading = toAdd.filter(u => !linkMeta[u]);
    if (newlyLoading.length) {
      setLinkMeta(prev => {
        const next = { ...prev };
        for (const u of newlyLoading) next[u] = { status: 'loading' };
        return next;
      });
      _fetchPreviewsAndMerge(newlyLoading);
    }
  }
  setInputText(val);
};

const _fetchPreviewsAndMerge = async (urls) => {
  try {
    const data = await api.post('/api/orders/links/preview', { urls });
    if (!data || !Array.isArray(data.previews)) return;
    setLinkMeta(prev => {
      const next = { ...prev };
      for (const p of data.previews) {
        next[p.url] = {
          status: p.status,
          image_url: p.image_url || null,
          title: p.title || null,
        };
      }
      return next;
    });
  } catch (_) {
    // Network/server error — leave entries in 'loading' state, the card will
    // keep its placeholder. Best-effort feature, not blocking.
    setLinkMeta(prev => {
      const next = { ...prev };
      for (const u of urls) {
        if (next[u] && next[u].status === 'loading') {
          next[u] = { status: 'fetch_failed' };
        }
      }
      return next;
    });
  }
};
```

- [ ] **Step 3: Keep `removeLink` removing from links but NOT from linkMeta**

The existing `removeLink` already only mutates `links`. Leave it as-is:

```jsx
const removeLink = url => setLinks(prev => prev.filter(u => u !== url));
```

(That's intentional — `linkMeta` is keyed by URL and surviving allows instant re-paste.)

- [ ] **Step 4: Replace `<AddedLinksList>` with mapped `<LinkCard>`s**

Find every occurrence of `<AddedLinksList links={links} onRemove={removeLink} />` in this file (use the editor's search — there's typically one at around line 395). Replace each occurrence with:

```jsx
{links.length > 0 && (
  <div style={{ marginTop: 12 }}>
    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
      Добавленные объявления
    </div>
    {links.map(url => (
      <LinkCard key={url} url={url} meta={linkMeta[url]} onRemove={removeLink} />
    ))}
  </div>
)}
```

- [ ] **Step 5: Delete the old component file**

```bash
git rm web/static/components/AddedLinksList.jsx
```

- [ ] **Step 6: Manual UI check in the dev server**

Start the dev stack:

```bash
make up
```

Then in a browser open `https://localhost:443/order-new` (or wherever the OrderForm route is). Paste one or two real Avito URLs into the textarea. Verify in order:

1. A card appears instantly with skeleton-shimmer thumb.
2. Within ~1–3 seconds the thumb fills with the real Avito photo and the title appears.
3. Hovering shows the full URL in tooltip.
4. Clicking the card opens Avito in a new tab.
5. Clicking `−` removes the card without errors.
6. Pasting the same URL again brings it back **without re-fetching** (no skeleton flash) — verified via DevTools → Network tab (no new `/preview` POST).

If something looks broken, fix it inline and re-check.

- [ ] **Step 7: Mobile check (per `feedback_web_responsive_check` memory)**

Open Chrome DevTools → Toggle device toolbar → pick iPhone SE. Re-test step 6 — make sure the card layout doesn't break at narrow widths (title truncates, thumb stays 56×56, `−` button reachable).

- [ ] **Step 8: Commit**

```bash
git add web/static/components/OrderForm.jsx
git rm --cached web/static/components/AddedLinksList.jsx 2>/dev/null || true
git commit -m "feat(order-form): replace plain link list with LinkCard previews"
```

---

## Task 7: Deploy — wire env vars and ship

**Files (on prod Hetzner):**
- Modify: `.env` (production secrets file — see `deploy.md` memory)

- [ ] **Step 1: SSH to prod and add the new env vars**

Per `deploy.md` memory: prod is at `167.233.52.85` (Hetzner). SSH in and edit the `.env` file at the project root:

```bash
ssh root@167.233.52.85
cd /root/avito_pf_bot   # or wherever the repo lives — check existing path
```

Add two lines to `.env`:

```
AVITO_PROXY_URL=https://lk.pf-bot.com
AVITO_PROXY_SECRET=<the secret from Task 4 Step 1>
```

- [ ] **Step 2: Pull & rebuild from dev branch**

Follow the standard deploy pattern from `feedback_use_deploy_sh` and `deploy.md`:

```bash
git fetch origin dev
git checkout dev
git pull
./deploy.sh
```

`deploy.sh` handles `docker compose build` + `up -d --force-recreate` + landing copy.

- [ ] **Step 3: Smoke-test the new endpoint from prod**

```bash
curl -s -X POST https://lk.pf-bot.com/api/orders/links/preview \
    -H "Content-Type: application/json" \
    -d '{"urls": ["https://www.avito.ru/ekaterinburg/telefony/iphone_14_pro_max_1_tb_7868289489"]}' | python3 -m json.tool
```

Expected: a JSON with `previews[0].status == "ok"`, a non-empty `title`, and an `image_url` pointing to `*.img.avito.st`.

- [ ] **Step 4: Smoke-test the UI**

Open `https://lk.pf-bot.com/order-new` in your browser, paste a real Avito link, confirm a preview card with a real thumbnail appears within 1–3 seconds.

- [ ] **Step 5: Tail logs for any errors during first 10 minutes of real traffic**

```bash
ssh root@167.233.52.85 'docker compose logs -f --tail=200 web 2>&1 | grep -iE "avito|preview|error"'
```

Look for repeated `fetch_failed` (which would mean RU-VPS proxy is misconfigured or Avito started blocking again) and any `httpx.*Error` tracebacks.

---

## Notes for the implementer

**Why the in-memory map keys-by-URL (Task 6):** the URL has already been canonicalized by `parseAvitoUrls` (`split('?')[0]`, trim trailing punctuation, dedup), so two pastes of the "same" listing collapse to the same key.

**Why no DB cache:** 250 orders/day, sequential users, each user's URLs are unique to them — the cache hit rate would be ~0% across sessions. In-session repeat happens (user removes + re-pastes), and the in-memory map covers it.

**Why nginx-level proxy instead of a Python proxy app:** zero new processes on the RU-VPS, zero new dependencies. The only thing nginx has to do is forward HTTP with a different `Host` header — its native job.

**Why `og:image:alt` over `og:title`:** Avito's `og:title` is SEO-stuffed (`iPhone 14 Pro Max, 1 ТБ купить в Екатеринбурге по низкой цене | Электроника | Авито`). `og:image:alt` is the clean H1 (`iPhone 14 Pro Max, 1 ТБ`).

**Failure modes to leave alone:**
- Single URL returns `fetch_failed` → card shows placeholder + URL path. User can still submit the order. Don't retry — Avito may be rate-limiting, retrying makes it worse.
- Backend endpoint 500's → frontend shows placeholders for everything. Order submission still works (the preview endpoint is decoupled from `POST /api/orders/pf`).
- RU-VPS down → same as above, plus the entire site is down anyway (it's the reverse-proxy front-end).
