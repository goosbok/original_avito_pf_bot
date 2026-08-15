"""get_tasks клиент + find_existing_task (дедуп после ошибки add-tasks)."""
from unittest.mock import patch

from services.pf_executor_api import get_tasks, find_existing_task
from services.exceptions import ExecutorAPIError


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = ""
    def json(self):
        return self._payload


def test_get_tasks_parses_task_list():
    payload = {"success": True, "data": {"total": 2, "tasks": [{"task_id": 1}, {"task_id": 2}]}}
    with patch("services.pf_executor_api.config.BIZA_API_KEY", "k"), \
         patch("services.pf_executor_api.rate_limiter.acquire"), \
         patch("services.pf_executor_api._session.get", return_value=_Resp(200, payload)):
        tasks = get_tasks()
    assert [t["task_id"] for t in tasks] == [1, 2]


def test_get_tasks_raises_on_non_200():
    with patch("services.pf_executor_api.config.BIZA_API_KEY", "k"), \
         patch("services.pf_executor_api.rate_limiter.acquire"), \
         patch("services.pf_executor_api._session.get", return_value=_Resp(500, {})):
        try:
            get_tasks()
            assert False, "expected ExecutorAPIError"
        except ExecutorAPIError:
            pass


def test_find_existing_task_matches_recent():
    order = {"position_name": "3/10"}
    now = 1_000_000_000_000
    tasks = [{"task_id": 777, "ad_link": "U", "views_per_day": 10, "days_count": 3, "created_at": now - 1000}]
    with patch("services.pf_executor_api.get_tasks", return_value=tasks):
        assert find_existing_task("U", order, now_ms=now) == "777"


def test_find_existing_task_no_match_returns_none():
    order = {"position_name": "3/10"}
    now = 1_000_000_000_000
    tasks = [{"task_id": 777, "ad_link": "OTHER", "views_per_day": 10, "days_count": 3, "created_at": now}]
    with patch("services.pf_executor_api.get_tasks", return_value=tasks):
        assert find_existing_task("U", order, now_ms=now) is None


def test_find_existing_task_stale_returns_none():
    order = {"position_name": "3/10"}
    now = 1_000_000_000_000
    old = now - (600 * 1000) - 1  # старше окна within_seconds=600
    tasks = [{"task_id": 777, "ad_link": "U", "views_per_day": 10, "days_count": 3, "created_at": old}]
    with patch("services.pf_executor_api.get_tasks", return_value=tasks):
        assert find_existing_task("U", order, now_ms=now, within_seconds=600) is None


def test_find_existing_task_none_when_get_tasks_errors():
    order = {"position_name": "3/10"}
    with patch("services.pf_executor_api.get_tasks", side_effect=ExecutorAPIError("boom")):
        assert find_existing_task("U", order) is None
