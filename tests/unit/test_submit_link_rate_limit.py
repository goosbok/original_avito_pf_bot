"""submit_link зовёт rate_limiter.acquire() перед POST."""
from unittest.mock import patch

from services.pf_executor_api import submit_link


def test_submit_link_acquires_rate_limit_before_post():
    order = {"increment": 1, "position_name": "3/10", "start_date": None}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"success": True, "data": {"task_ids": ["ext-1"]}}

    with patch("services.pf_executor_api.config.BIZA_API_KEY", "k"), \
         patch("services.pf_executor_api.rate_limiter.acquire") as acq, \
         patch("services.pf_executor_api._session.post", return_value=FakeResp()) as post:
        ext = submit_link("https://avito.ru/x_1", order, search_phrase="q")

    assert ext == "ext-1"
    acq.assert_called_once()
    # acquire должен сработать ДО POST
    assert acq.call_count == 1 and post.call_count == 1
