"""Клиент к биза (skipper для cookie-auth dashboard scraping).

Stateless: каждый вызов login() создаёт свежий requests.Session, выполняет
POST формы логина, возвращает сессию с накопленными cookies. Сессия живёт
ровно столько, сколько вызывающий код её использует.

Чтение только с dashboard.php — никаких мутаций через эти cookies.
"""
from __future__ import annotations

import logging
from datetime import date
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from data import config
from services.avito_url import extract_ad_id

logger = logging.getLogger(__name__)


# URL и имена полей формы — ПОДТВЕРЖДЕНЫ через DevTools.
_LOGIN_PATH = "/login.php"  # лежит на project root, NOT под /pf-avito
_USERNAME_FIELD = "username"
_PASSWORD_FIELD = "password"
_DASHBOARD_PATH = "/dashboard.php"

# Cookies, которые ожидаем после успешного логина.
_AUTH_COOKIE_NAMES = ("PHPSESSID",)

# Anchor для извлечения created_at — гарантирует, что мы НЕ запишем
# garbage если столбцы биза сменили порядок или формат даты упростился.
import re as _re
_CREATED_AT_RE = _re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")


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
    # BIZA_DASHBOARD_BASE_URL = .../fwdrjjkigor_new/pf-avito ; login.php
    # лежит на parent уровне (/fwdrjjkigor_new/login.php), не под /pf-avito.
    url = config.BIZA_DASHBOARD_BASE_URL.rsplit("/", 1)[0] + _LOGIN_PATH
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

    # PHP создаёт PHPSESSID до проверки кредов, поэтому наличие cookie
    # само по себе не значит успешный логин. Проверяем тело финальной
    # страницы — на login.php заголовок 'Страница авторизации', после
    # успешного входа сервер редиректит на меню/дашборд.
    if "Страница авторизации" in resp.text:
        raise LoginFailed("credentials rejected (still on login page)")

    logger.info("biza.login.ok cookies=%s", list(cookies.keys()))
    return session


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
    """Распарсить одну строку <tr>. Возвращает None если структура не
    соответствует ожидаемой (column-drift защита).

    Колонки: [0]checkbox, [1]date+mode, [2]search_link, [3]ad_link, ...
    """
    tds = tr.find_all("td")
    if len(tds) < 4:
        return None

    # td[1]: дата 'YYYY-MM-DD HH:MM' (потом "Через поиск" вторым токеном).
    m_date = _CREATED_AT_RE.search(tds[1].get_text(" ", strip=True))
    if not m_date:
        return None
    created_at = m_date.group(0)

    # td[2]: search_link — реальный URL в href, display text может быть
    # обрезан (типа '...ii/tag/kurer?cd=1'). Берём href или title.
    a_search = tds[2].find("a")
    if a_search is not None:
        search_link = (a_search.get("href") or a_search.get("title")
                       or a_search.get_text(strip=True))
    else:
        search_link = tds[2].get_text(strip=True)
    if not search_link:
        return None

    # td[3]: ad_link — отсюда берём ad_id.
    a_ad = tds[3].find("a")
    if a_ad is None:
        return None
    ad_href = _unwrap_redirect(a_ad.get("href") or "")
    ad_id = extract_ad_id(ad_href)
    if not ad_id:
        return None

    return {
        "ad_id": ad_id,
        "search_link": search_link,
        "created_at": created_at,
    }


def _unwrap_redirect(href: str) -> str:
    """Если href вида '...?ad_link=<url-encoded>' — вернуть распакованный
    ad_link. Иначе вернуть href как есть."""
    p = urlparse(href)
    qs = parse_qs(p.query)
    if "ad_link" in qs:
        return unquote(qs["ad_link"][0])
    return href


def _fmt_date(d: date) -> str:
    """YYYY_M_D — формат биза, без ведущих нулей."""
    return f"{d.year}_{d.month}_{d.day}"
