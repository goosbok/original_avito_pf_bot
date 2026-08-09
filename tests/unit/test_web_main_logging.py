"""Regression test: web/main.py must configure the root logger so INFO-level
logs from any application module reach the api container's stdout/stderr.

The api container runs `uvicorn web.main:app` directly (docker-compose.yml,
service `api`) — it never executes __main__.py, which is the only place that
called logging.basicConfig(...). uvicorn only configures its own uvicorn.*
loggers via dictConfig, not the root logger, so every logger.info() call in
application code (services/*, web/routers/*) silently disappears from
`docker logs`. Found 2026-07-28 while QA'ing SMS login: services/sms.py's
logger.info(...) with the OTP code never showed up in `docker logs` for the
api service.
"""
import io
import logging
from contextlib import redirect_stderr


def test_configure_logging_makes_info_logs_reach_stderr():
    from web.main import configure_logging

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            configure_logging()
            logging.getLogger("services.sms").info("STUB SMS to +7: code=1234")
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)

    assert "STUB SMS to +7: code=1234" in buf.getvalue()
