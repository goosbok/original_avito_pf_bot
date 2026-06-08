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


def test_login_body_still_login_page_raises():
    """Cookie set но в body всё ещё login form → fail."""
    sess = _mock_session(post_cookies={"PHPSESSID": "x"},
                         post_text="<html><title>Страница авторизации</title>")
    with patch("services.biznesklondaik_client._new_session",
               return_value=sess):
        with pytest.raises(LoginFailed):
            login("user", "wrong_pwd")


def test_login_empty_credentials_raises():
    """Пустой login или password → не идём в сеть."""
    with pytest.raises(LoginFailed):
        login("", "pwd")
    with pytest.raises(LoginFailed):
        login("user", "")
