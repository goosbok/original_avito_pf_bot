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


def test_parse_dashboard_html_handles_date_only_row():
    """Если в дате нет времени, всё равно вытаскивает YYYY-MM-DD."""
    html = """
    <table><tbody>
    <tr>
      <td></td>
      <td>2026-06-07 Через поиск</td>
      <td><a href='x'>купить</a></td>
      <td><a href='https://www.avito.ru/x_1234567890'>ad</a></td>
    </tr>
    </tbody></table>
    """
    rows = parse_dashboard_html(html)
    assert len(rows) == 1
    assert rows[0]["created_at"] == "2026-06-07"


def test_parse_dashboard_html_skips_row_without_parseable_date():
    """Если в td[1] нет даты — строка пропускается (column-drift защита)."""
    html = """
    <table><tbody>
    <tr>
      <td></td>
      <td>not a date at all</td>
      <td><a href='x'>купить</a></td>
      <td><a href='https://www.avito.ru/x_1234567890'>ad</a></td>
    </tr>
    </tbody></table>
    """
    assert parse_dashboard_html(html) == []


def test_fmt_date_no_leading_zeros():
    """_fmt_date должна давать формат биза 'YYYY_M_D'."""
    from services.biznesklondaik_client import _fmt_date
    from datetime import date
    assert _fmt_date(date(2026, 1, 5)) == "2026_1_5"
    assert _fmt_date(date(2026, 12, 31)) == "2026_12_31"
