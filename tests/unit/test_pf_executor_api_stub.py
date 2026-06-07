"""Stub: API-клиент всегда raises ExecutorAPIRejected (Спек §5.1)."""
import pytest


def test_submit_link_always_raises_rejected():
    from services.pf_executor_api import submit_link
    from services.exceptions import ExecutorAPIRejected
    with pytest.raises(ExecutorAPIRejected):
        submit_link("https://avito.ru/x", {"position_name": "3/100"})
