"""Клиент к биза (skipper для cookie-auth dashboard scraping).

Stateless: каждый вызов login() создаёт свежий requests.Session, выполняет
POST формы логина, возвращает сессию с накопленными cookies. Сессия живёт
ровно столько, сколько вызывающий код её использует.

Чтение только с dashboard.php — никаких мутаций через эти cookies.
"""
from __future__ import annotations

import logging

import requests

from data import config

logger = logging.getLogger(__name__)


# URL и имена полей формы — ПОДТВЕРЖДЕНЫ через DevTools.
_LOGIN_PATH = "/login.php"
_USERNAME_FIELD = "username"
_PASSWORD_FIELD = "password"
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

    # PHP создаёт PHPSESSID до проверки кредов, поэтому наличие cookie
    # само по себе не значит успешный логин. Проверяем тело финальной
    # страницы — на login.php заголовок 'Страница авторизации', после
    # успешного входа сервер редиректит на меню/дашборд.
    if "Страница авторизации" in resp.text:
        raise LoginFailed("credentials rejected (still on login page)")

    logger.info("biza.login.ok cookies=%s", list(cookies.keys()))
    return session
