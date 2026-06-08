from unittest.mock import patch, MagicMock
import pytest

from services.pf_executor_api import submit_link
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected


@pytest.fixture(autouse=True)
def _biza_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conftest stub leaves BIZA_API_KEY empty; tests need a non-empty value
    so submit_link reaches the HTTP path."""
    monkeypatch.setattr("data.config.BIZA_API_KEY", "test-key", raising=False)


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
