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


def test_submit_link_missing_position_name_rejected():
    """Missing position_name → ExecutorAPIRejected (manual fallback)."""
    bad_order = {"start_date": "2026-06-10", "contacts": 0}
    # _session.post should not even be called because we raise before that
    with patch("services.pf_executor_api._session.post") as post:
        with pytest.raises(ExecutorAPIRejected):
            submit_link("https://avito.ru/x_1234567890",
                        bad_order, search_phrase="x")
    post.assert_not_called()


def test_submit_link_malformed_position_name_rejected():
    """Malformed position_name → ExecutorAPIRejected."""
    bad_order = {"position_name": "not-a-number", "contacts": 0}
    with patch("services.pf_executor_api._session.post") as post:
        with pytest.raises(ExecutorAPIRejected):
            submit_link("https://avito.ru/x_1234567890",
                        bad_order, search_phrase="x")
    post.assert_not_called()


def test_submit_link_uses_PF_DEFAULT_START_HOUR_from_config():
    """start_hour в payload берётся из config.PF_DEFAULT_START_HOUR, не хардкод 0."""
    with patch("services.pf_executor_api.config.PF_DEFAULT_START_HOUR", 10), \
         patch("services.pf_executor_api._session.post",
               return_value=_resp(200, {
                   "success": True,
                   "data": {"task_ids": [1], "tasks_added": 1},
               })) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(), search_phrase="x")
    body = post.call_args.kwargs["json"]
    assert body["tasks"][0]["start_hour"] == 10


def test_submit_link_start_hour_default_zero_when_config_zero():
    """Когда PF_DEFAULT_START_HOUR=0 — start_hour=0 (дефолт-совместимость)."""
    with patch("services.pf_executor_api.config.PF_DEFAULT_START_HOUR", 0), \
         patch("services.pf_executor_api._session.post",
               return_value=_resp(200, {
                   "success": True,
                   "data": {"task_ids": [1], "tasks_added": 1},
               })) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(), search_phrase="x")
    assert post.call_args.kwargs["json"]["tasks"][0]["start_hour"] == 0
