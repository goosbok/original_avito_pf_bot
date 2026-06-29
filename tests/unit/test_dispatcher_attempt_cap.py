"""Потолок попыток авто-отправки: 2 неудачи → manual; + миграция колонки."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso


def test_order_links_has_dispatch_attempts_column(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(order_links)").fetchall()}
    assert "dispatch_attempts" in cols
