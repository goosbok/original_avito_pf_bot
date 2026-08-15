"""Schema test for funnel_events table."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def test_funnel_events_table_exists_with_expected_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(funnel_events)").fetchall()}
    assert cols == {"id", "user_id", "service", "step", "ts"}


def test_funnel_events_indexes_exist(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        idx_names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='funnel_events'"
            ).fetchall()
        }
    assert "idx_funnel_service_ts" in idx_names
    assert "idx_funnel_service_step_user" in idx_names
