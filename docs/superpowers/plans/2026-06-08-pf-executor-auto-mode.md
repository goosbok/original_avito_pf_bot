# PF Executor Auto-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зажечь auto-режим в `services/order_links_dispatcher.py`. Заменить
stub'ы `pf_executor_api.submit_link` и `order_links_classifier.classify` на
реальную интеграцию с биза: classifier читает из локального кэша известных
объявлений, submit_link шлёт POST `add-tasks.php`. Кэш строится bulk-скрейпом
дашборда исполнителя (`/pf-avito/dashboard.php`) — один initial backfill за
90 дней + ежедневный refresh за 2 дня. Два feature-flag'а
(`PF_PHRASE_CACHE_REFRESH_ENABLED`, `PF_AUTO_DISPATCH_ENABLED`) — оба default
false. Структурные decision-логи в classifier + hourly метрика `auto_rate`.

**Architecture:** Кэш `avito_ad_phrase_cache` — единственная новая таблица.
Cookie-auth (login flow → `requests.Session`) исключительно для чтения
dashboard'а. X-API-KEY (новая env) для submit. Логика hot-path: `classifier`
делает чистый local SELECT — без внешних HTTP при оплате. Refresh-cron'ы
работают рядом с существующими `deadline`/`dispatcher` в lifespan'е web/main.py.

**Tech Stack:** Python 3 / aiogram 2 / SQLite / FastAPI / pytest. HTTP-клиент —
`requests` (sync, уже в `requirements.txt`). Парсер HTML — `beautifulsoup4`
(если ещё не в зависимостях, ставим в Task 1).

**Spec:** [docs/superpowers/specs/2026-06-08-pf-executor-auto-mode-design.md](../specs/2026-06-08-pf-executor-auto-mode-design.md)

**Tests:** запускать в docker через смонтированный worktree (см.
MEMORY.md / feedback_docker_tests):

```bash
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api pytest <path> -v
```

---

## File Structure

**Создаются:**
- `services/avito_url.py` — `extract_ad_id(url) -> str | None`.
- `services/avito_phrase_cache.py` — `lookup(ad_id)`, `upsert_many(rows)`,
  `last_refreshed_at()`.
- `services/biznesklondaik_client.py` — `login(session, login, password)`,
  `fetch_dashboard(session, date_from, date_to)`, `parse_dashboard_html(html)`.
- `services/avito_phrase_cache_refresh.py` — `refresh_recent(days=2)`,
  `run_refresh_loop()`.
- `services/auto_rate_metric.py` — `compute_recent_auto_rate(hours=1)`,
  `run_metric_loop()`.
- `scripts/backfill_avito_phrase_cache.py` — 90-day initial pull.
- `tests/fixtures/biznesklondaik_dashboard_sample.html` — захардкоженный
  фрагмент real-ответа (10-20 строк, чистим от PII).
- `tests/fixtures/biznesklondaik_login_form.html` — sample login-формы
  для теста парсинга csrf-токенов (если есть).
- `tests/unit/test_avito_url.py`
- `tests/unit/test_avito_phrase_cache.py`
- `tests/unit/test_biznesklondaik_client.py`
- `tests/unit/test_pf_executor_api_real.py`
- `tests/unit/test_order_links_classifier_cache.py`
- `tests/unit/test_avito_phrase_cache_refresh.py`
- `tests/unit/test_auto_rate_metric.py`
- `tests/unit/test_backfill_avito_phrase_cache.py`
- `tests/unit/test_order_links_dispatcher_auto.py`

**Модифицируются:**
- `.env.example` — `BIZA_*` секция + два feature-flag'а + tuning.
- `data/config.py` — экспорт новых env как атрибутов модуля.
- `utils/sqlite3.py` — `get_schema_statements()` добавить
  `avito_ad_phrase_cache`.
- `services/pf_executor_api.py` — переписать `submit_link` под реальный
  POST `add-tasks.php`, расширить сигнатуру `search_phrase`.
- `services/order_links_classifier.py` — переписать `classify` под cache
  lookup + feature flag + structured logging. Сигнатура остаётся
  `classify(url, order) -> str` или меняется на возврат tuple — см. T7.
- `services/order_links_dispatcher.py` — `_dispatch_one` достаёт phrase
  и пробрасывает в `submit_link`.
- `web/main.py` — добавить два `asyncio.create_task` в lifespan'е:
  `run_refresh_loop`, `run_metric_loop`.
- `requirements.txt` — `beautifulsoup4` (если ещё нет).

---

## Task 1: Env-config + таблица кэша

**Files:**
- Modify: `.env.example`, `data/config.py`, `utils/sqlite3.py`,
  `requirements.txt`
- Test: `tests/unit/test_db_schema.py` (расширить)

- [ ] **Step 1: Failing test для схемы**

В `tests/unit/test_db_schema.py` добавить:

```python
def test_avito_ad_phrase_cache_table(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute(
            "PRAGMA table_info(avito_ad_phrase_cache)"
        )}
    assert cols == {"ad_id", "search_link", "created_at", "cached_at"}

    with sqlite3.connect(tmp_db) as con:
        pk = [r[1] for r in con.execute(
            "PRAGMA table_info(avito_ad_phrase_cache)"
        ) if r[5] == 1]  # pk flag
    assert pk == ["ad_id"]
```

- [ ] **Step 2: Run — FAIL**

```bash
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api \
    pytest tests/unit/test_db_schema.py::test_avito_ad_phrase_cache_table -v
```

- [ ] **Step 3: Добавить таблицу в схему**

В `utils/sqlite3.py::get_schema_statements()` после кортежа для `order_links`:

```python
(
    "avito_ad_phrase_cache",
    "CREATE TABLE IF NOT EXISTS avito_ad_phrase_cache("
    "ad_id TEXT PRIMARY KEY,"
    "search_link TEXT NOT NULL,"
    "created_at TIMESTAMP NOT NULL,"
    "cached_at TIMESTAMP NOT NULL)",
    13,  # bump phase
),
```

Индексов отдельно не делаем — PK покрывает все запросы.

- [ ] **Step 4: Дополнить `.env.example`**

В конец файла добавить секцию:

```env
# ── Biznesklondaik PF executor (auto-mode) ────────────────────────────────────
# X-API-KEY для add-tasks.php (взять из docs.php их сервиса).
BIZA_API_KEY=
# Логин/пароль для скрейпа dashboard.php (read-only).
BIZA_LOGIN=
BIZA_PASSWORD=
# Базовые URL — менять только при миграции их инфры.
BIZA_API_BASE_URL=https://biznesklondaik.ru/fwdrjjkigor_new/api
BIZA_DASHBOARD_BASE_URL=https://biznesklondaik.ru/fwdrjjkigor_new/pf-avito

# Feature flags (оба default false).
# Включает nightly bulk-refresh кэша через scrape dashboard.
PF_PHRASE_CACHE_REFRESH_ENABLED=false
# Включает auto-режим в classifier'е (без него classifier всегда → manual).
PF_AUTO_DISPATCH_ENABLED=false

# Tuning.
PF_PHRASE_CACHE_CHUNK_DAYS=4          # окно при backfill
PF_PHRASE_CACHE_REFRESH_INTERVAL_H=24 # период refresh-cron'а
PF_DASHBOARD_REQUEST_DELAY_SEC=3      # пауза между чанками при backfill
PF_AUTO_RATE_METRIC_INTERVAL_H=1      # период метрики auto_rate
```

- [ ] **Step 5: Экспортировать env в `data/config.py`**

В `data/config.py` после существующих секций:

```python
# === Biznesklondaik PF executor (auto-mode) ===
BIZA_API_KEY: str = os.getenv("BIZA_API_KEY", "")
BIZA_LOGIN: str = os.getenv("BIZA_LOGIN", "")
BIZA_PASSWORD: str = os.getenv("BIZA_PASSWORD", "")
BIZA_API_BASE_URL: str = os.getenv(
    "BIZA_API_BASE_URL",
    "https://biznesklondaik.ru/fwdrjjkigor_new/api",
).rstrip("/")
BIZA_DASHBOARD_BASE_URL: str = os.getenv(
    "BIZA_DASHBOARD_BASE_URL",
    "https://biznesklondaik.ru/fwdrjjkigor_new/pf-avito",
).rstrip("/")

PF_PHRASE_CACHE_REFRESH_ENABLED: bool = (
    os.getenv("PF_PHRASE_CACHE_REFRESH_ENABLED", "false").lower() == "true"
)
PF_AUTO_DISPATCH_ENABLED: bool = (
    os.getenv("PF_AUTO_DISPATCH_ENABLED", "false").lower() == "true"
)

PF_PHRASE_CACHE_CHUNK_DAYS: int = int(
    os.getenv("PF_PHRASE_CACHE_CHUNK_DAYS", "4")
)
PF_PHRASE_CACHE_REFRESH_INTERVAL_H: int = int(
    os.getenv("PF_PHRASE_CACHE_REFRESH_INTERVAL_H", "24")
)
PF_DASHBOARD_REQUEST_DELAY_SEC: int = int(
    os.getenv("PF_DASHBOARD_REQUEST_DELAY_SEC", "3")
)
PF_AUTO_RATE_METRIC_INTERVAL_H: int = int(
    os.getenv("PF_AUTO_RATE_METRIC_INTERVAL_H", "1")
)
```

- [ ] **Step 6: BS4 в зависимости**

```bash
grep -q "beautifulsoup4" requirements.txt || echo "beautifulsoup4==4.12.3" >> requirements.txt
```

- [ ] **Step 7: Run — PASS + image rebuild**

```bash
docker compose build api
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api \
    pytest tests/unit/test_db_schema.py -v
```

- [ ] **Step 8: Commit**

```bash
git add utils/sqlite3.py data/config.py .env.example requirements.txt \
        tests/unit/test_db_schema.py
git commit -m "feat(pf-auto): schema for avito_ad_phrase_cache + biza env config"
```

---

## Task 2: `services/avito_url.py::extract_ad_id`

**Files:**
- Create: `services/avito_url.py`
- Create: `tests/unit/test_avito_url.py`

- [ ] **Step 1: Failing test**

`tests/unit/test_avito_url.py`:

```python
import pytest
from services.avito_url import extract_ad_id


@pytest.mark.parametrize("url, expected", [
    # стандартные
    ("https://www.avito.ru/moskva/kvartiry/1-k._kvartira_44_m_812_et_1234567890",
     "1234567890"),
    ("https://avito.ru/moskva/kvartiry/3-k._kvartira_749m_216et._7961085920",
     "7961085920"),
    ("https://m.avito.ru/sankt-peterburg/avtomobili/lada_2107_2003_2222333344",
     "2222333344"),
    # с query/fragment
    ("https://www.avito.ru/moskva/kvartiry/1k_1234567890?utm_source=x",
     "1234567890"),
    ("https://www.avito.ru/moskva/kvartiry/1k_1234567890#tab",
     "1234567890"),
    # http
    ("http://avito.ru/moskva/kvartiry/abc_9999999999", "9999999999"),
    # отсутствие id
    ("https://avito.ru/moskva/kvartiry", None),
    ("https://avito.ru/", None),
    ("https://avito.ru/profile/12345", None),  # короткий — мы хотим >=8 цифр
    ("not a url", None),
    ("", None),
    (None, None),
])
def test_extract_ad_id(url, expected):
    assert extract_ad_id(url) == expected
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/avito_url.py`:

```python
"""Извлечение Avito ad_id из URL объявления.

ad_id — последняя группа цифр (>=8) в пути URL. Этот формат единый для
desktop/mobile (avito.ru, m.avito.ru) и не меняется query/fragment'ом.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_AD_ID_RE = re.compile(r"_(\d{8,})(?:/|$)")


def extract_ad_id(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    if not path:
        return None
    m = _AD_ID_RE.search(path)
    return m.group(1) if m else None
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add services/avito_url.py tests/unit/test_avito_url.py
git commit -m "feat(pf-auto): extract_ad_id helper for avito urls"
```

---

## Task 3: `services/avito_phrase_cache.py` (CRUD)

**Files:**
- Create: `services/avito_phrase_cache.py`
- Create: `tests/unit/test_avito_phrase_cache.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_avito_phrase_cache.py
from services import avito_phrase_cache as cache


def test_lookup_missing_returns_none(tmp_db):
    assert cache.lookup("12345") is None


def test_upsert_then_lookup(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "купить",
         "created_at": "2026-06-01 12:00"},
    ])
    assert cache.lookup("111") == "купить"


def test_upsert_latest_created_at_wins(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "old",
         "created_at": "2026-06-01 12:00"},
    ])
    cache.upsert_many([
        {"ad_id": "111", "search_link": "new",
         "created_at": "2026-06-05 12:00"},
    ])
    assert cache.lookup("111") == "new"


def test_upsert_older_does_not_overwrite(tmp_db):
    cache.upsert_many([
        {"ad_id": "111", "search_link": "new",
         "created_at": "2026-06-05 12:00"},
    ])
    cache.upsert_many([
        {"ad_id": "111", "search_link": "old",
         "created_at": "2026-06-01 12:00"},
    ])
    assert cache.lookup("111") == "new"


def test_last_refreshed_at(tmp_db):
    assert cache.last_refreshed_at() is None
    cache.upsert_many([
        {"ad_id": "111", "search_link": "x",
         "created_at": "2026-06-05 12:00"},
    ])
    assert cache.last_refreshed_at() is not None
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/avito_phrase_cache.py`:

```python
"""CRUD кэша известных объявлений (ad_id → search_link).

Используется classifier'ом в hot-path'е: один SELECT, никаких внешних HTTP.
Заполняется bulk-скрейпом dashboard'а исполнителя (см.
services.avito_phrase_cache_refresh).
"""
from __future__ import annotations

import logging
from typing import Iterable

from services.db import connect
from utils.dates import now_iso

logger = logging.getLogger(__name__)


def lookup(ad_id: str) -> str | None:
    """Вернуть last-used search_link для ad_id, или None."""
    if not ad_id:
        return None
    with connect() as con:
        row = con.execute(
            "SELECT search_link FROM avito_ad_phrase_cache WHERE ad_id=?",
            (ad_id,),
        ).fetchone()
    if row is None:
        return None
    return row["search_link"] if hasattr(row, "keys") else row[0]


def upsert_many(rows: Iterable[dict]) -> int:
    """Апсёрт пачки записей. Latest-created_at-wins по конфликту.

    Возвращает количество successful upsert'ов.
    """
    now = now_iso()
    affected = 0
    with connect() as con:
        for r in rows:
            ad_id = r.get("ad_id")
            phrase = r.get("search_link")
            created = r.get("created_at")
            if not ad_id or not phrase or not created:
                continue
            cur = con.execute(
                "INSERT INTO avito_ad_phrase_cache"
                "(ad_id, search_link, created_at, cached_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ad_id) DO UPDATE SET "
                "  search_link=excluded.search_link, "
                "  created_at=excluded.created_at, "
                "  cached_at=excluded.cached_at "
                "WHERE excluded.created_at > avito_ad_phrase_cache.created_at",
                (ad_id, phrase, created, now),
            )
            affected += cur.rowcount
        con.commit()
    return affected


def last_refreshed_at() -> str | None:
    """ISO-метка последнего апсёрта. Используется в health-check."""
    with connect() as con:
        row = con.execute(
            "SELECT MAX(cached_at) AS m FROM avito_ad_phrase_cache"
        ).fetchone()
    if row is None:
        return None
    return row["m"] if hasattr(row, "keys") else row[0]
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add services/avito_phrase_cache.py tests/unit/test_avito_phrase_cache.py
git commit -m "feat(pf-auto): avito_phrase_cache CRUD (lookup, upsert, latest-wins)"
```

---

## Task 4: `services/biznesklondaik_client.py::login`

**Files:**
- Create: `services/biznesklondaik_client.py`
- Create: `tests/unit/test_biznesklondaik_client.py`

> **NOTE для исполнителя:** имена полей формы (`username` vs `login` vs `email`,
> наличие CSRF-токена) подтверждаются по факту при первом подключении к
> живому endpoint'у. Стартуем с типовых имён, корректируем по факту.

- [ ] **Step 1: Failing test (на mock'е HTTP)**

```python
# tests/unit/test_biznesklondaik_client.py
from unittest.mock import patch, MagicMock
from services.biznesklondaik_client import login, LoginFailed
import pytest


def _mock_session(post_status=200, post_cookies=None, post_text="dashboard"):
    sess = MagicMock()
    resp = MagicMock(status_code=post_status, text=post_text)
    resp.cookies = post_cookies or {}
    sess.post.return_value = resp
    sess.cookies = post_cookies or {}
    return sess


def test_login_success_returns_session_with_cookies():
    sess = _mock_session(post_cookies={"PHPSESSID": "x",
                                       "remember_token": "t"})
    with patch("services.biznesklondaik_client._new_session",
               return_value=sess):
        out = login("user", "pwd")
    assert out is sess
    sess.post.assert_called_once()


def test_login_no_session_cookie_raises():
    sess = _mock_session(post_cookies={})  # no PHPSESSID
    with patch("services.biznesklondaik_client._new_session",
               return_value=sess):
        with pytest.raises(LoginFailed):
            login("user", "pwd")


def test_login_http_error_raises():
    sess = _mock_session(post_status=500)
    with patch("services.biznesklondaik_client._new_session",
               return_value=sess):
        with pytest.raises(LoginFailed):
            login("user", "pwd")
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Skeleton implementation**

`services/biznesklondaik_client.py`:

```python
"""Клиент к биза (skipper для cookie-auth dashboard scraping).

Stateless: каждый вызов login() создаёт свежий requests.Session, выполняет
POST формы логина, возвращает сессию с накопленными cookies. Сессия живёт
ровно столько, сколько вызывающий код её использует.

Чтение только с dashboard.php — никаких мутаций через эти cookies.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from data import config

logger = logging.getLogger(__name__)


# URL и имена полей формы — фиксируем после первого подключения.
# По умолчанию закладываемся на типовые имена.
_LOGIN_PATH = "/login.php"        # CONFIRM by intercept
_USERNAME_FIELD = "username"      # CONFIRM
_PASSWORD_FIELD = "password"      # CONFIRM
_DASHBOARD_PATH = "/dashboard.php"

# Cookies, которые ожидаем после успешного логина.
_AUTH_COOKIE_NAMES = ("PHPSESSID",)


class BiznesklondaikError(RuntimeError):
    pass


class LoginFailed(BiznesklondaikError):
    pass


class ScrapeFailed(BiznesklondaikError):
    pass


def _new_session() -> requests.Session:
    """Hookable для тестов."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "original_avito_pf_bot/1.0 (+server)",
    })
    return s


def login(login_value: str, password: str,
          *, timeout: float = 15.0) -> requests.Session:
    """Залогиниться в биза. Возвращает сессию с auth cookies.

    Raises LoginFailed если HTTP не 200 или нет auth-cookie в ответе.
    """
    if not login_value or not password:
        raise LoginFailed("login/password not configured")

    session = _new_session()
    url = config.BIZA_DASHBOARD_BASE_URL + _LOGIN_PATH
    payload = {_USERNAME_FIELD: login_value, _PASSWORD_FIELD: password}

    try:
        resp = session.post(url, data=payload, timeout=timeout,
                            allow_redirects=True)
    except requests.RequestException as exc:
        raise LoginFailed(f"network error: {exc}") from exc

    if resp.status_code != 200:
        raise LoginFailed(f"HTTP {resp.status_code} on login")

    cookies = dict(session.cookies)
    if not any(name in cookies for name in _AUTH_COOKIE_NAMES):
        raise LoginFailed(
            f"login did not produce auth cookies (have: {list(cookies)})"
        )

    logger.info("biza.login.ok cookies=%s", list(cookies.keys()))
    return session
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add services/biznesklondaik_client.py tests/unit/test_biznesklondaik_client.py
git commit -m "feat(pf-auto): biznesklondaik client — login flow"
```

---

## Task 5: `fetch_dashboard` + parser

**Files:**
- Modify: `services/biznesklondaik_client.py` — добавить
  `fetch_dashboard`, `parse_dashboard_html`.
- Create: `tests/fixtures/biznesklondaik_dashboard_sample.html` — реальный
  фрагмент HTML 5-10 строк (берётся из реального ответа, чистится от PII).
- Modify: `tests/unit/test_biznesklondaik_client.py` — добавить тесты
  парсера.

- [ ] **Step 1: Получить sample fixture (manual prep)**

> Этот шаг выполняется **руками** один раз — нужны живые креды.
>
> 1. Залогиниться в биза через curl/Postman, получить cookies.
> 2. Скачать `dashboard.php?daterange=…` за маленькое окно (1 день).
> 3. Из ответа взять 5-10 первых `<tr>` строк + обрамляющую структуру
>    (открытие `<table>`, `<thead>`, `<tbody>`, закрытия).
> 4. Сохранить в `tests/fixtures/biznesklondaik_dashboard_sample.html`.
> 5. (опц.) обфусцировать пользовательские ad-link'и — заменить домены
>    в search_link на тестовые. ad_id оставить, search_link тоже (для
>    unit-теста парсера).

- [ ] **Step 2: Failing test**

```python
# в tests/unit/test_biznesklondaik_client.py
from pathlib import Path
from services.biznesklondaik_client import parse_dashboard_html

_FIXTURE = Path(__file__).parent.parent / "fixtures" \
    / "biznesklondaik_dashboard_sample.html"


def test_parse_dashboard_html_basic_shape():
    html = _FIXTURE.read_text()
    rows = parse_dashboard_html(html)
    assert len(rows) >= 5
    sample = rows[0]
    assert set(sample.keys()) >= {"ad_id", "search_link", "created_at"}
    assert sample["ad_id"].isdigit()
    assert len(sample["ad_id"]) >= 8
    assert sample["search_link"]
    # ISO-like дата 'YYYY-MM-DD HH:MM' либо 'YYYY-MM-DD'
    assert sample["created_at"].startswith("202")


def test_parse_dashboard_html_skips_broken_rows():
    # одна строка без ad-link → должна быть пропущена с warning, остальные ОК
    bad = "<table><tbody><tr><td>broken</td></tr></tbody></table>"
    rows = parse_dashboard_html(bad)
    assert rows == []


def test_parse_dashboard_html_empty_returns_empty():
    assert parse_dashboard_html("") == []
    assert parse_dashboard_html("<html></html>") == []
```

- [ ] **Step 3: Run — FAIL**

- [ ] **Step 4: Implementation парсера**

В `services/biznesklondaik_client.py` добавить:

```python
from bs4 import BeautifulSoup
from datetime import date, timedelta

from services.avito_url import extract_ad_id


def fetch_dashboard(
    session: requests.Session,
    date_from: date,
    date_to: date,
    *,
    timeout: float = 60.0,
) -> str:
    """GET dashboard.php?daterange=… → raw HTML.

    Raises ScrapeFailed на HTTP != 200.
    """
    daterange = f"{_fmt_date(date_from)} - {_fmt_date(date_to)}"
    url = config.BIZA_DASHBOARD_BASE_URL + _DASHBOARD_PATH
    try:
        resp = session.get(
            url,
            params={"filter": "", "daterange": daterange},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ScrapeFailed(f"network: {exc}") from exc
    if resp.status_code != 200:
        raise ScrapeFailed(f"HTTP {resp.status_code} on dashboard")
    return resp.text


def parse_dashboard_html(html: str) -> list[dict]:
    """Распарсить HTML дашборда → список dict'ов с ad_id, search_link,
    created_at.

    Падающие строки пропускаем (с warning), не валим всю выборку.
    """
    if not html or "<tbody" not in html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for tr in soup.select("tbody tr"):
        try:
            row = _parse_row(tr)
        except Exception:  # noqa: BLE001
            logger.warning("biza.parse_row.failed", exc_info=True)
            continue
        if row:
            out.append(row)
    return out


def _parse_row(tr) -> dict | None:
    """Распарсить одну строку <tr>. Возвращает None если в строке нет
    avito-ссылки или ad_id не извлекается."""
    # Ищем любую ссылку на avito.ru — берём первую попавшуюся (в строке
    # таких 1-3, все на один и тот же ad).
    href = None
    for a in tr.find_all("a"):
        h = a.get("href") or ""
        if "avito.ru" in h:
            href = _unwrap_redirect(h)
            break
        # вложенный параметр ad_link=… в их internal links
        if "ad_link=" in h:
            href = _unwrap_redirect(h)
            break
    if not href:
        return None

    ad_id = extract_ad_id(href)
    if not ad_id:
        return None

    # Колонки: чекбокс, дата, search_link, ad_link, ...
    tds = tr.find_all("td")
    if len(tds) < 3:
        return None

    # Дата — первая строка во второй td (без "Через поиск" второй строкой).
    created_text = tds[1].get_text(" ", strip=True).split()
    # ожидаем "YYYY-MM-DD HH:MM Через поиск" → берём первые 2 токена.
    created_at = " ".join(created_text[:2]) if len(created_text) >= 2 \
        else (created_text[0] if created_text else "")

    # search_link — первая ссылка/текст в третьей td.
    sl_td = tds[2]
    a = sl_td.find("a")
    search_link = (a.get_text(strip=True) if a
                   else sl_td.get_text(strip=True))

    if not search_link or not created_at:
        return None

    return {
        "ad_id": ad_id,
        "search_link": search_link,
        "created_at": created_at,
    }


def _unwrap_redirect(href: str) -> str:
    """Если href вида '...?ad_link=<url-encoded>' — вернуть распакованный
    ad_link. Иначе вернуть href как есть."""
    from urllib.parse import urlparse, parse_qs, unquote
    p = urlparse(href)
    qs = parse_qs(p.query)
    if "ad_link" in qs:
        return unquote(qs["ad_link"][0])
    return href


def _fmt_date(d: date) -> str:
    """YYYY_M_D — формат биза, без ведущих нулей."""
    return f"{d.year}_{d.month}_{d.day}"
```

- [ ] **Step 5: Run — PASS на fixture**

- [ ] **Step 6: Commit**

```bash
git add services/biznesklondaik_client.py \
        tests/fixtures/biznesklondaik_dashboard_sample.html \
        tests/unit/test_biznesklondaik_client.py
git commit -m "feat(pf-auto): biza dashboard fetch + html parser"
```

---

## Task 6: Rewrite `services/pf_executor_api.py::submit_link`

**Files:**
- Modify: `services/pf_executor_api.py`
- Modify: `services/exceptions.py` — (опц.) добавить `ExecutorAPIInsufficientBalance`
- Create: `tests/unit/test_pf_executor_api_real.py`
- Delete: `tests/unit/test_pf_executor_api_stub.py` (или оставить с
  @pytest.mark.skip + комментарием — на твой выбор)

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_pf_executor_api_real.py
from unittest.mock import patch, MagicMock
import pytest

from services.pf_executor_api import submit_link
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected


def _order():
    return {"position_name": "3/10", "start_date": "2026-06-10",
            "contacts": 1, "phone": "+7..."}


def _resp(status, json_body):
    r = MagicMock(status_code=status)
    r.json.return_value = json_body
    return r


def test_submit_link_success_returns_external_id():
    with patch("services.pf_executor_api._session.post",
               return_value=_resp(200, {
                   "success": True,
                   "data": {"task_ids": [42, 43], "tasks_added": 1},
               })) as post:
        ext = submit_link("https://avito.ru/x_1234567890",
                          _order(), search_phrase="купить квартиру")
    assert ext == "42"
    # payload: правильный module/ad_link/search_link/views_per_day/dates
    args, kwargs = post.call_args
    body = kwargs["json"]
    assert body["module"] == "avito_pf"
    task = body["tasks"][0]
    assert task["ad_link"] == "https://avito.ru/x_1234567890"
    assert task["search_link"] == "купить квартиру"
    assert task["views_per_day"] == 10
    assert len(task["dates"]) == 3
    assert all(d.count("_") == 2 for d in task["dates"])


def test_submit_link_400_rejected():
    with patch("services.pf_executor_api._session.post",
               return_value=_resp(400, {
                   "success": False, "error": "invalid url"
               })):
        with pytest.raises(ExecutorAPIRejected):
            submit_link("https://avito.ru/x_1234567890",
                        _order(), search_phrase="x")


def test_submit_link_429_temporary_error():
    with patch("services.pf_executor_api._session.post",
               return_value=_resp(429, {
                   "success": False, "error": "rate limit"
               })):
        with pytest.raises(ExecutorAPIError):
            submit_link("https://avito.ru/x_1234567890",
                        _order(), search_phrase="x")


def test_submit_link_500_temporary_error():
    with patch("services.pf_executor_api._session.post",
               return_value=_resp(500, {"success": False})):
        with pytest.raises(ExecutorAPIError):
            submit_link("https://avito.ru/x_1234567890",
                        _order(), search_phrase="x")
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/pf_executor_api.py` (полная замена stub'а):

```python
"""Клиент API исполнителя ПФ (https://biznesklondaik.ru/.../api/).

Используется dispatcher'ом для auto-режима. Авторизация — X-API-KEY.
Чтение из dashboard'а (cookie-auth) — отдельно, в biznesklondaik_client.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from data import config
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_session = requests.Session()


def submit_link(
    url: str,
    order: dict,
    *,
    search_phrase: str,
) -> str:
    """POST add-tasks.php → возвращает external_id (str) при успехе.

    Маппинг ошибок:
      400 → ExecutorAPIRejected (won't retry, fallback в manual)
      401/403 → ExecutorAPIError (config issue, retry бессмыслен,
                                  но логируем CRITICAL)
      422 → ExecutorAPIError (наш bug, лог critical)
      429 → ExecutorAPIError (retry)
      5xx / network → ExecutorAPIError (retry)
    """
    if not config.BIZA_API_KEY:
        raise ExecutorAPIError("BIZA_API_KEY not configured")

    payload = _build_avito_payload(url, order, search_phrase)
    api_url = config.BIZA_API_BASE_URL + "/add-tasks.php"
    headers = {
        "X-API-KEY": config.BIZA_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = _session.post(api_url, json=payload, headers=headers,
                             timeout=20.0)
    except requests.RequestException as exc:
        raise ExecutorAPIError(f"network: {exc}") from exc

    status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = {}

    if status == 200 and body.get("success"):
        task_ids = body.get("data", {}).get("task_ids") or []
        if not task_ids:
            raise ExecutorAPIError(
                f"200 OK но нет task_ids: {body}")
        external_id = str(task_ids[0])
        logger.info("biza.submit.ok ad=%s external_id=%s",
                    payload["tasks"][0]["ad_link"], external_id)
        return external_id

    err_text = body.get("error") or resp.text[:200]
    if status == 400:
        logger.warning("biza.submit.rejected ad=%s err=%s",
                       payload["tasks"][0]["ad_link"], err_text)
        raise ExecutorAPIRejected(f"400: {err_text}")
    if status in (401, 403):
        logger.critical("biza.submit.auth_error status=%s err=%s",
                        status, err_text)
        raise ExecutorAPIError(f"{status}: {err_text}")
    if status == 422:
        logger.critical("biza.submit.invalid_json payload=%s body=%s",
                        payload, body)
        raise ExecutorAPIError(f"422: {err_text}")
    if status == 429:
        logger.warning("biza.submit.rate_limited")
        raise ExecutorAPIError("429: rate limited")
    raise ExecutorAPIError(f"{status}: {err_text}")


# === Payload builder ===


def _build_avito_payload(
    url: str, order: dict, search_phrase: str
) -> dict:
    """Сформировать JSON для POST add-tasks.php (module=avito_pf)."""
    parts = str(order["position_name"]).split("/")
    days = int(parts[0])
    fix_count = int(parts[1]) if len(parts) > 1 else 0
    if fix_count <= 0:
        raise ExecutorAPIError(
            f"invalid fix_count from position_name={order['position_name']!r}"
        )

    today = datetime.now(timezone.utc).astimezone(_MSK).date()
    start_str = order.get("start_date")
    start = today
    if start_str:
        try:
            start = date.fromisoformat(str(start_str))
        except ValueError:
            logger.warning("biza.payload.bad_start_date %r → today",
                           start_str)
            start = today
    start = max(start, today)

    dates = [_fmt_date(start + timedelta(days=i)) for i in range(days)]

    return {
        "module": "avito_pf",
        "tasks": [{
            "search_link": search_phrase,
            "ad_link": url,
            "views_per_day": fix_count,
            "dates": dates,
            "device": "desktop",
            "mode": "polnyj",
            "request_contact": bool(order.get("contacts")),
            "add_favorite": True,
            "direct_if_not_found": True,
            "start_hour": 0,
            "enable_pauses": False,
        }],
    }


def _fmt_date(d: date) -> str:
    return f"{d.year}_{d.month}_{d.day}"
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Удалить старый stub-тест**

```bash
git rm tests/unit/test_pf_executor_api_stub.py
```

(Либо оставить с `pytest.mark.skip("заменён реальной реализацией")` — на
твой выбор. Чище — удалить.)

- [ ] **Step 6: Commit**

```bash
git add services/pf_executor_api.py tests/unit/test_pf_executor_api_real.py
git commit -m "feat(pf-auto): real submit_link via add-tasks.php (avito_pf)"
```

---

## Task 7: Rewrite `services/order_links_classifier.py`

**Files:**
- Modify: `services/order_links_classifier.py`
- Modify: `services/order_links_dispatcher.py` — `_dispatch_one` теперь
  достаёт phrase и пробрасывает.
- Create: `tests/unit/test_order_links_classifier_cache.py`
- Delete: `tests/unit/test_order_links_classifier_stub.py`

**Сигнатура:** `classify(url, order) -> tuple[str, str | None]` —
возвращает `(mode, phrase | None)`. Phrase нужен dispatcher'у для submit'а.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_order_links_classifier_cache.py
from unittest.mock import patch
from services.order_links_classifier import classify


def _order():
    return {"position_name": "3/10"}


def test_feature_off_returns_manual(tmp_db, caplog):
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               False):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any(
        "feature_off" in r.message or
        getattr(r, "reason", None) == "feature_off"
        for r in caplog.records
    )


def test_no_ad_id_returns_manual(tmp_db, caplog):
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://example.com/no_ad", _order(),
                                link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any("no_ad_id" in r.message for r in caplog.records)


def test_cache_miss_returns_manual(tmp_db, caplog):
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "manual"
    assert phrase is None
    assert any("cache_miss" in r.message for r in caplog.records)


def test_cache_hit_returns_auto(tmp_db, caplog):
    from services.avito_phrase_cache import upsert_many
    upsert_many([{"ad_id": "1234567890", "search_link": "купить квартиру",
                  "created_at": "2026-06-01 12:00"}])
    with patch("services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
               True):
        mode, phrase = classify("https://avito.ru/x_1234567890",
                                _order(), link_id=99)
    assert mode == "auto"
    assert phrase == "купить квартиру"
    assert any("cache_hit" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/order_links_classifier.py`:

```python
"""Classifier для dispatcher'а: auto или manual для одной ссылки.

Hot-path: один SELECT в локальный кэш — никаких внешних HTTP.

Decision-логи (structured) на каждое решение — для аудита почему ссылка
пошла куда пошла. Reason codes:
  feature_off — PF_AUTO_DISPATCH_ENABLED=false
  no_ad_id    — extract_ad_id не вернул id
  cache_miss  — ad_id есть, но в кэше пусто
  cache_hit   — auto, phrase подтянулась
"""
from __future__ import annotations

import logging

from data import config
from services.avito_phrase_cache import lookup as cache_lookup
from services.avito_url import extract_ad_id

logger = logging.getLogger(__name__)


def classify(url: str, order: dict, *, link_id: int | None = None) \
        -> tuple[str, str | None]:
    """Решает auto/manual для ссылки.

    Возвращает (mode, phrase | None).
    Phrase != None только когда mode='auto'.

    `link_id` — для логов; ничего не меняет в логике.
    """
    if not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None

    ad_id = extract_ad_id(url)
    if not ad_id:
        _log(link_id, None, "manual", "no_ad_id")
        return "manual", None

    phrase = cache_lookup(ad_id)
    if not phrase:
        _log(link_id, ad_id, "manual", "cache_miss")
        return "manual", None

    _log(link_id, ad_id, "auto", "cache_hit")
    return "auto", phrase


def _log(link_id, ad_id, decision, reason):
    logger.info(
        "classifier.decision link=%s ad=%s decision=%s reason=%s",
        link_id, ad_id or "none", decision, reason,
    )
```

- [ ] **Step 4: Update dispatcher `_dispatch_one`**

В `services/order_links_dispatcher.py` строки `mode = current_mode or
classify(url, order)` и далее заменить на:

```python
# Если delivery_mode ещё не назначен — классифицируем.
if current_mode:
    mode = current_mode
    phrase = None  # ranks: повторный dispatch на уже-auto ссылку —
                   # phrase тут не нужен (link уже в pending+auto после
                   # ExecutorAPIError, в этом случае submit_link сам
                   # достанет из контекста — НО, для consistency, лучше
                   # дёрнуть classifier'а заново)
    # ↓ корректнее так:
    mode, phrase = classify(url, order, link_id=link_id)
else:
    mode, phrase = classify(url, order, link_id=link_id)

if mode == "manual":
    ...

# mode == 'auto' — пробуем API
try:
    external_id = submit_link(url, order, search_phrase=phrase)
except ...
```

(Перепиши блок целиком, не лоскутками. Главное — `submit_link` теперь
принимает `search_phrase=phrase` именованным аргументом, и phrase всегда
не-None когда mode='auto'.)

- [ ] **Step 5: Run — PASS classifier-тесты И dispatcher-тесты**

```bash
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api \
    pytest tests/unit/test_order_links_classifier_cache.py \
           tests/unit/test_order_links_dispatcher.py \
           tests/unit/test_order_links_dispatcher_retry.py -v
```

Падающие тесты (на старую сигнатуру `classify(url, order) -> str`) надо
обновить в том же коммите.

- [ ] **Step 6: Commit**

```bash
git rm tests/unit/test_order_links_classifier_stub.py
git add services/order_links_classifier.py services/order_links_dispatcher.py \
        tests/unit/test_order_links_classifier_cache.py \
        tests/unit/test_order_links_dispatcher.py \
        tests/unit/test_order_links_dispatcher_retry.py
git commit -m "feat(pf-auto): classifier reads phrase cache, dispatcher passes phrase to API"
```

---

## Task 8: `services/avito_phrase_cache_refresh.py` + cron-loop

**Files:**
- Create: `services/avito_phrase_cache_refresh.py`
- Create: `tests/unit/test_avito_phrase_cache_refresh.py`
- Modify: `web/main.py` — добавить task в lifespan.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_avito_phrase_cache_refresh.py
from datetime import date
from unittest.mock import patch, MagicMock

from services.avito_phrase_cache_refresh import refresh_recent


def test_refresh_skipped_when_flag_off(tmp_db):
    with patch("services.avito_phrase_cache_refresh."
               "config.PF_PHRASE_CACHE_REFRESH_ENABLED", False), \
         patch("services.avito_phrase_cache_refresh.login") as login:
        n = refresh_recent(days=2)
    assert n == 0
    login.assert_not_called()


def test_refresh_window_is_last_n_days(tmp_db):
    sess = MagicMock()
    with patch("services.avito_phrase_cache_refresh."
               "config.PF_PHRASE_CACHE_REFRESH_ENABLED", True), \
         patch("services.avito_phrase_cache_refresh.login",
               return_value=sess), \
         patch("services.avito_phrase_cache_refresh.fetch_dashboard",
               return_value="<html></html>") as fetch, \
         patch("services.avito_phrase_cache_refresh.parse_dashboard_html",
               return_value=[
                   {"ad_id": "111", "search_link": "x",
                    "created_at": "2026-06-08 09:00"},
               ]) as parse, \
         patch("services.avito_phrase_cache_refresh."
               "_today", return_value=date(2026, 6, 8)):
        n = refresh_recent(days=2)
    fetch.assert_called_once()
    args, kwargs = fetch.call_args
    assert kwargs["date_from"] == date(2026, 6, 6)
    assert kwargs["date_to"] == date(2026, 6, 8)
    assert n == 1
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/avito_phrase_cache_refresh.py`:

```python
"""Bulk-refresh кэша известных объявлений.

Один раз в сутки тянем dashboard'у биза за последние `days` дней, парсим,
апсёртим в локальный кэш. Гейтится `PF_PHRASE_CACHE_REFRESH_ENABLED`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from data import config
from services.avito_phrase_cache import upsert_many
from services.biznesklondaik_client import (
    BiznesklondaikError, fetch_dashboard, login, parse_dashboard_html,
)

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))


def _today() -> date:
    return datetime.now(timezone.utc).astimezone(_MSK).date()


def refresh_recent(days: int = 2) -> int:
    """Один заход refresh-цикла. Возвращает число upsert'ов.

    Skip когда feature flag выключен — вернёт 0, ничего не делает.
    """
    if not config.PF_PHRASE_CACHE_REFRESH_ENABLED:
        logger.info("biza.refresh.skip feature_off")
        return 0

    today = _today()
    date_from = today - timedelta(days=days)
    date_to = today

    logger.info("biza.refresh.start window=%s..%s", date_from, date_to)
    try:
        session = login(config.BIZA_LOGIN, config.BIZA_PASSWORD)
        html = fetch_dashboard(session, date_from=date_from, date_to=date_to)
        rows = parse_dashboard_html(html)
    except BiznesklondaikError as exc:
        logger.exception("biza.refresh.failed err=%s", exc)
        return 0

    # Группируем by ad_id, оставляем latest по created_at
    by_ad: dict[str, dict] = {}
    for r in rows:
        prev = by_ad.get(r["ad_id"])
        if prev is None or r["created_at"] > prev["created_at"]:
            by_ad[r["ad_id"]] = r

    affected = upsert_many(by_ad.values())
    logger.info(
        "biza.refresh.done window=%s..%s rows=%d unique_ads=%d upserted=%d",
        date_from, date_to, len(rows), len(by_ad), affected,
    )
    return affected


async def run_refresh_loop() -> None:
    interval_sec = config.PF_PHRASE_CACHE_REFRESH_INTERVAL_H * 3600
    logger.info("biza.refresh.loop start interval=%ss", interval_sec)
    while True:
        await asyncio.sleep(interval_sec)
        try:
            refresh_recent(days=2)
        except Exception:  # noqa: BLE001
            logger.exception("biza.refresh.loop_iter_failed")
```

- [ ] **Step 4: Wire в lifespan**

В `web/main.py` после `dispatcher_task = asyncio.create_task(...)`:

```python
from services.avito_phrase_cache_refresh import run_refresh_loop

refresh_task = asyncio.create_task(run_refresh_loop())
```

В finally блоке — cancel + await.

- [ ] **Step 5: Run — PASS**

- [ ] **Step 6: Commit**

```bash
git add services/avito_phrase_cache_refresh.py \
        tests/unit/test_avito_phrase_cache_refresh.py web/main.py
git commit -m "feat(pf-auto): daily refresh loop for avito phrase cache"
```

---

## Task 9: `scripts/backfill_avito_phrase_cache.py`

**Files:**
- Create: `scripts/backfill_avito_phrase_cache.py`
- Create: `tests/unit/test_backfill_avito_phrase_cache.py`

- [ ] **Step 1: Failing test (chunking + idempotency)**

```python
# tests/unit/test_backfill_avito_phrase_cache.py
from datetime import date
from unittest.mock import patch, MagicMock

from scripts.backfill_avito_phrase_cache import iter_chunks, backfill


def test_iter_chunks_splits_correctly():
    chunks = list(iter_chunks(date(2026, 6, 8), days_back=10, chunk_size=4))
    # ожидаем 3 чанка: [-10..-6], [-6..-2], [-2..0]
    assert len(chunks) == 3
    assert chunks[0] == (date(2026, 5, 29), date(2026, 6, 2))
    assert chunks[-1][1] == date(2026, 6, 8)


def test_backfill_idempotent(tmp_db):
    sess = MagicMock()
    with patch("scripts.backfill_avito_phrase_cache.login",
               return_value=sess), \
         patch("scripts.backfill_avito_phrase_cache.fetch_dashboard",
               return_value="<html></html>"), \
         patch("scripts.backfill_avito_phrase_cache.parse_dashboard_html",
               return_value=[
                   {"ad_id": "111", "search_link": "x",
                    "created_at": "2026-06-05 12:00"},
               ]):
        n1 = backfill(days=8, chunk_size=4,
                      today=date(2026, 6, 8), delay_sec=0)
        n2 = backfill(days=8, chunk_size=4,
                      today=date(2026, 6, 8), delay_sec=0)
    # повторный запуск не валится; кэш консистентен
    from services.avito_phrase_cache import lookup
    assert lookup("111") == "x"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`scripts/backfill_avito_phrase_cache.py`:

```python
"""One-shot backfill кэша известных объявлений за N последних дней.

Использование:
    docker compose exec bot python -m scripts.backfill_avito_phrase_cache --days 90

Идемпотентен: можно прогонять повторно. Кэш апсёртится с latest-created_at-wins.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from data import config
from services.avito_phrase_cache import upsert_many
from services.biznesklondaik_client import (
    BiznesklondaikError, fetch_dashboard, login, parse_dashboard_html,
)

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))


def iter_chunks(today: date, *, days_back: int,
                chunk_size: int) -> Iterator[tuple[date, date]]:
    """Разбить интервал [today-days_back, today] на чанки по chunk_size дней."""
    start = today - timedelta(days=days_back)
    cur = start
    while cur < today:
        nxt = min(cur + timedelta(days=chunk_size), today)
        yield (cur, nxt)
        cur = nxt


def backfill(*, days: int, chunk_size: int = None,
             today: date = None, delay_sec: int = None) -> int:
    """Прогнать backfill. Возвращает суммарное число upsert'ов."""
    chunk_size = chunk_size or config.PF_PHRASE_CACHE_CHUNK_DAYS
    delay_sec = (delay_sec if delay_sec is not None
                 else config.PF_DASHBOARD_REQUEST_DELAY_SEC)
    today = today or datetime.now(timezone.utc).astimezone(_MSK).date()

    session = login(config.BIZA_LOGIN, config.BIZA_PASSWORD)
    chunks = list(iter_chunks(today, days_back=days, chunk_size=chunk_size))
    total_upserted = 0
    for i, (df, dt) in enumerate(chunks, 1):
        logger.info("backfill.chunk %d/%d %s..%s", i, len(chunks), df, dt)
        try:
            html = fetch_dashboard(session, date_from=df, date_to=dt)
            rows = parse_dashboard_html(html)
        except BiznesklondaikError as exc:
            logger.exception("backfill.chunk_failed %d/%d err=%s",
                             i, len(chunks), exc)
            continue

        by_ad: dict[str, dict] = {}
        for r in rows:
            prev = by_ad.get(r["ad_id"])
            if prev is None or r["created_at"] > prev["created_at"]:
                by_ad[r["ad_id"]] = r

        affected = upsert_many(by_ad.values())
        total_upserted += affected
        logger.info("backfill.chunk_done rows=%d ads=%d upserted=%d",
                    len(rows), len(by_ad), affected)

        if i < len(chunks) and delay_sec > 0:
            time.sleep(delay_sec)

    logger.info("backfill.complete chunks=%d total_upserted=%d",
                len(chunks), total_upserted)
    return total_upserted


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--delay", type=int, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    backfill(days=args.days, chunk_size=args.chunk_size,
             delay_sec=args.delay)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_avito_phrase_cache.py \
        tests/unit/test_backfill_avito_phrase_cache.py
git commit -m "feat(pf-auto): 90-day backfill script for phrase cache"
```

---

## Task 10: Hourly `auto_rate` метрика

**Files:**
- Create: `services/auto_rate_metric.py`
- Create: `tests/unit/test_auto_rate_metric.py`
- Modify: `web/main.py` — добавить task в lifespan.

- [ ] **Step 1: Failing tests**

```python
# tests/unit/test_auto_rate_metric.py
import sqlite3

from services.auto_rate_metric import compute_recent_auto_rate
from utils.dates import now_iso


def _seed(tmp_db, modes):
    """modes: список ('auto'|'manual'|None,) — каждая попадёт как pending link."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/10', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        for mode in modes:
            con.execute(
                "INSERT INTO order_links(order_id, url, status, "
                "delivery_mode, created_at) "
                "VALUES (?, 'u', 'pending', ?, ?)",
                (order_id, mode, now_iso())
            )
        con.commit()


def test_auto_rate_empty(tmp_db):
    out = compute_recent_auto_rate(hours=1)
    assert out == {"auto": 0, "total": 0, "rate": 0.0}


def test_auto_rate_mixed(tmp_db):
    _seed(tmp_db, modes=["auto", "auto", "manual", None])
    out = compute_recent_auto_rate(hours=1)
    # None не считаем — это ещё-не-классифицированные.
    assert out["auto"] == 2
    assert out["total"] == 3
    assert out["rate"] == 2 / 3
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implementation**

`services/auto_rate_metric.py`:

```python
"""Hourly метрика auto_rate — для слежения за качеством работы classifier'а.

Лог формата:
    metric.auto_rate auto=N total=M rate=0.XX
"""
from __future__ import annotations

import asyncio
import logging

from data import config
from services.db import connect

logger = logging.getLogger(__name__)


def compute_recent_auto_rate(hours: int = 1) -> dict:
    sql = """
        SELECT
            SUM(CASE WHEN delivery_mode='auto'   THEN 1 ELSE 0 END) AS n_auto,
            SUM(CASE WHEN delivery_mode IS NOT NULL THEN 1 ELSE 0 END) AS n_total
        FROM order_links
        WHERE created_at >= datetime('now', ?)
    """
    with connect() as con:
        row = con.execute(sql, (f"-{hours} hours",)).fetchone()
    n_auto = int(row["n_auto"] or 0)
    n_total = int(row["n_total"] or 0)
    rate = n_auto / n_total if n_total else 0.0
    return {"auto": n_auto, "total": n_total, "rate": rate}


async def run_metric_loop() -> None:
    interval_sec = config.PF_AUTO_RATE_METRIC_INTERVAL_H * 3600
    logger.info("metric.auto_rate.loop start interval=%ss", interval_sec)
    while True:
        await asyncio.sleep(interval_sec)
        try:
            m = compute_recent_auto_rate(
                hours=config.PF_AUTO_RATE_METRIC_INTERVAL_H,
            )
            logger.info("metric.auto_rate auto=%d total=%d rate=%.3f",
                        m["auto"], m["total"], m["rate"])
        except Exception:  # noqa: BLE001
            logger.exception("metric.auto_rate.failed")
```

- [ ] **Step 4: Wire в lifespan**

В `web/main.py`:

```python
from services.auto_rate_metric import run_metric_loop

metric_task = asyncio.create_task(run_metric_loop())
# и в finally cancel + await
```

- [ ] **Step 5: Run — PASS**

- [ ] **Step 6: Commit**

```bash
git add services/auto_rate_metric.py tests/unit/test_auto_rate_metric.py \
        web/main.py
git commit -m "feat(pf-auto): hourly auto_rate metric loop"
```

---

## Task 11: e2e интеграционный тест

**Files:**
- Create: `tests/unit/test_order_links_dispatcher_auto.py`

- [ ] **Step 1: Тесты**

```python
# tests/unit/test_order_links_dispatcher_auto.py
"""e2e: оплата → classify → submit_link → mark_in_work с external_id."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.avito_phrase_cache import upsert_many
from utils.dates import now_iso


def _seed(tmp_db, url):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, "
            "start_date, date) VALUES (1, 100, '3/10', 'paid', NULL, ?)",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=[url])
        con.commit()
    return order_id


def test_e2e_auto_dispatch_when_phrase_cached(tmp_db):
    """Cache hit + feature on → submit_link вызван, link in_work auto."""
    url = "https://avito.ru/moskva/kvartiry/x_1234567890"
    order_id = _seed(tmp_db, url)
    upsert_many([{"ad_id": "1234567890",
                  "search_link": "купить квартиру",
                  "created_at": "2026-06-01 12:00"}])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        True), patch(
        "services.order_links_dispatcher.submit_link",
        return_value="ext-42",
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    # submit_link был вызван с search_phrase из кэша
    args, kwargs = submit.call_args
    assert kwargs["search_phrase"] == "купить квартиру"
    assert args[0] == url

    links = list_links(order_id)
    assert links[0]["status"] == "in_work"
    assert links[0]["delivery_mode"] == "auto"
    assert links[0]["external_id"] == "ext-42"


def test_e2e_manual_when_feature_off(tmp_db):
    url = "https://avito.ru/moskva/kvartiry/x_1234567890"
    order_id = _seed(tmp_db, url)
    upsert_many([{"ad_id": "1234567890", "search_link": "x",
                  "created_at": "2026-06-01 12:00"}])

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        False), patch(
        "services.order_links_dispatcher.submit_link"
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    submit.assert_not_called()
    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "manual"


def test_e2e_manual_when_cache_miss(tmp_db):
    url = "https://avito.ru/moskva/kvartiry/x_9999999999"
    order_id = _seed(tmp_db, url)
    # кэш пустой

    with patch(
        "services.order_links_classifier.config.PF_AUTO_DISPATCH_ENABLED",
        True), patch(
        "services.order_links_dispatcher.submit_link"
    ) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(order_id)

    submit.assert_not_called()
    links = list_links(order_id)
    assert links[0]["delivery_mode"] == "manual"
```

- [ ] **Step 2: Run — PASS все три**

- [ ] **Step 3: Final full-suite smoke**

```bash
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api pytest -v
```

Все должно быть зелёным.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_order_links_dispatcher_auto.py
git commit -m "test(pf-auto): e2e dispatcher with cached phrase / feature off"
```

---

## Out of scope для этого плана

Эти задачи **НЕ** реализуем здесь:

1. **Cleanup кэша** (`DELETE WHERE cached_at < …`). По решению юзера —
   откладываем, таблица растёт органически.
2. **Stop-task через API.** Остановка остаётся через админ-кнопку
   `fail_remaining_links`.
3. **Балансный алерт** — нужен ли cron на `get-balance.php` и алерт в
   support-thread при пороге. Отдельной задачей.
4. **Webhook от исполнителя** о статусе задач. Closure по-прежнему по
   `deadline_at` через `close_expired_links`.
5. **Runtime toggle флагов** через админку (без рестарта).
6. **Self-invalidation кэша** по факту неуспешной отправки. Без этого —
   stale phrase будет тихо проваливаться в `failed`, разруливается
   рестартом backfill'а руками.

---

## Rollout-протокол (после merge)

1. Деплой кода — оба флага в `false`, ничего не меняется в проде.
2. Залить креды в `.env` на проде:
   - `BIZA_API_KEY` (тот же или новый ключ, что и в их docs.php)
   - `BIZA_LOGIN`, `BIZA_PASSWORD`
3. Включить `PF_PHRASE_CACHE_REFRESH_ENABLED=true` + рестарт.
4. Запустить backfill руками:
   ```bash
   docker compose exec bot python -m scripts.backfill_avito_phrase_cache --days 90
   ```
5. Проверить, что в БД ~5-10к строк в `avito_ad_phrase_cache`.
6. Дождаться суток — посмотреть лог `biza.refresh.done` (значит nightly
   refresh работает).
7. Включить `PF_AUTO_DISPATCH_ENABLED=true` + рестарт.
8. Следить за логами `classifier.decision` и метрикой `metric.auto_rate`
   на первых заказах. Если `rate` стабильно > 0 — auto работает.
9. Если что-то не так — флипнуть `PF_AUTO_DISPATCH_ENABLED=false` +
   рестарт, моментально откатываемся к manual flow.
