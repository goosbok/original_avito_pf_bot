"""Tests for services.funnel."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
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


def _insert_event(db_path: Path, user_id: int, service: str, step: str, ts: datetime) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO funnel_events (user_id, service, step, ts) VALUES (?, ?, ?, ?)",
            (user_id, service, step, ts.isoformat()),
        )
        con.commit()


def test_get_funnel_stats_empty(tmp_db: Path):
    from services.funnel import FUNNEL_STEPS, get_funnel_stats

    result = get_funnel_stats("pf_avito")
    assert [r["step"] for r in result] == FUNNEL_STEPS["pf_avito"]
    assert all(r["users"] == 0 for r in result)
    assert result[0]["drop_off_pct"] is None
    assert all(r["drop_off_pct"] is None for r in result)  # prev=0 → None


def test_get_funnel_stats_distinct_users(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    # user 1 reaches view_tariff twice and select_period once
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "select_period", now)
    # user 2 only reaches view_tariff
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)

    result = {r["step"]: r for r in get_funnel_stats("pf_avito")}
    assert result["view_tariff"]["users"] == 2
    assert result["select_period"]["users"] == 1
    assert result["select_count"]["users"] == 0


def test_get_funnel_stats_drop_off_percentages(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    # 10 users at view_tariff, 8 at select_period, 4 at select_count
    for uid in range(1, 11):
        _insert_event(tmp_db, uid, "pf_avito", "view_tariff", now)
    for uid in range(1, 9):
        _insert_event(tmp_db, uid, "pf_avito", "select_period", now)
    for uid in range(1, 5):
        _insert_event(tmp_db, uid, "pf_avito", "select_count", now)

    result = {r["step"]: r for r in get_funnel_stats("pf_avito")}
    assert result["view_tariff"]["drop_off_pct"] is None
    assert result["select_period"]["drop_off_pct"] == 20.0  # (10-8)/10
    assert result["select_count"]["drop_off_pct"] == 50.0   # (8-4)/8


def test_get_funnel_stats_date_filter(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", old)
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)

    # Filter: only events in the last 7 days
    result = {
        r["step"]: r
        for r in get_funnel_stats("pf_avito", from_dt=now - timedelta(days=7), to_dt=now + timedelta(seconds=1))
    }
    assert result["view_tariff"]["users"] == 1


def test_get_funnel_stats_invalid_service(tmp_db: Path):
    from services.funnel import get_funnel_stats

    with pytest.raises(ValueError):
        get_funnel_stats("nonexistent")


def test_get_funnel_stats_naive_datetime_rejected(tmp_db: Path):
    from services.funnel import get_funnel_stats

    naive = datetime(2026, 5, 18, 12, 0, 0)  # no tzinfo
    with pytest.raises(ValueError):
        get_funnel_stats("pf_avito", from_dt=naive)
    with pytest.raises(ValueError):
        get_funnel_stats("pf_avito", to_dt=naive)


def test_render_chart_returns_png_bytesio(tmp_db: Path):
    from services.funnel import render_chart

    now = datetime.now(timezone.utc)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "select_period", now)

    buf = render_chart("pf_avito", title="Test funnel")
    head = buf.read(8)
    # PNG magic bytes
    assert head[:4] == b"\x89PNG"
    buf.seek(0)
    # File-like object positioned at the start for downstream callers
    assert buf.tell() == 0
