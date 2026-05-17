"""Tests for services.funnel."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_funnel_steps_contains_pf_avito():
    from services.funnel import FUNNEL_STEPS

    assert "pf_avito" in FUNNEL_STEPS
    assert FUNNEL_STEPS["pf_avito"] == [
        "view_tariff",
        "select_period",
        "select_count",
        "links_valid",
        "contact_chosen",
        "order_confirmed",
    ]


def test_every_funnel_service_has_label():
    from services.funnel import FUNNEL_STEPS, SERVICE_LABELS

    assert set(FUNNEL_STEPS) <= set(SERVICE_LABELS)


def test_track_step_inserts_row(tmp_db: Path):
    from services.funnel import track_step

    track_step(user_id=42, service="pf_avito", step="view_tariff")

    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, service, step, ts FROM funnel_events"
        ).fetchall()
    assert len(rows) == 1
    user_id, service, step, ts = rows[0]
    assert user_id == 42
    assert service == "pf_avito"
    assert step == "view_tariff"
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed).total_seconds() == 0


def test_track_step_invalid_service_raises(tmp_db: Path):
    from services.funnel import track_step

    with pytest.raises(ValueError):
        track_step(user_id=1, service="nonexistent", step="view_tariff")


def test_track_step_invalid_step_raises(tmp_db: Path):
    from services.funnel import track_step

    with pytest.raises(ValueError):
        track_step(user_id=1, service="pf_avito", step="not_a_step")


def test_track_step_multiple_events_same_user(tmp_db: Path):
    from services.funnel import track_step

    track_step(user_id=7, service="pf_avito", step="view_tariff")
    track_step(user_id=7, service="pf_avito", step="view_tariff")
    track_step(user_id=7, service="pf_avito", step="select_period")

    with sqlite3.connect(tmp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM funnel_events").fetchone()[0]
    assert count == 3
