"""Планировщик ежедневной выгрузки авто-запусков."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

_MSK = timezone(timedelta(hours=3))


def test_next_run_before_hour_is_today():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 3, 15, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 9, 6, 0, tzinfo=_MSK)


def test_next_run_exactly_at_hour_is_tomorrow():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 6, 0, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 10, 6, 0, tzinfo=_MSK)


def test_next_run_after_hour_is_tomorrow():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 9, 23, 59, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 8, 10, 6, 0, tzinfo=_MSK)


def test_next_run_crosses_month_boundary():
    from services.auto_launch_export import next_run_at

    now = datetime(2026, 8, 31, 12, 0, tzinfo=_MSK)
    assert next_run_at(now, hour=6) == datetime(2026, 9, 1, 6, 0, tzinfo=_MSK)


def test_is_due_false_before_hour(tmp_db):
    from services import auto_launch_export as ale

    now = datetime(2026, 8, 9, 5, 0, tzinfo=_MSK)
    assert ale._is_due(now) is False


def test_is_due_true_when_never_ran(tmp_db):
    from services import auto_launch_export as ale

    now = datetime(2026, 8, 9, 7, 0, tzinfo=_MSK)
    assert ale._is_due(now) is True


def test_is_due_false_after_successful_run(tmp_db):
    from services import auto_launch_export as ale

    ale._mark_run_done("2026-08-09")
    now = datetime(2026, 8, 9, 7, 0, tzinfo=_MSK)
    assert ale._is_due(now) is False


@pytest.mark.asyncio
async def test_run_once_marks_day_and_notifies(tmp_db):
    from services import auto_launch_export as ale

    sent = []

    async def _fake_send(msg, category):
        sent.append((msg, category))

    with patch.object(ale, "export_auto_launches",
                      return_value="https://example.test/auto"), \
         patch.object(ale, "send_admins", _fake_send), \
         patch.object(ale, "now_msk",
                      return_value=datetime(2026, 8, 9, 6, 1, tzinfo=_MSK)):
        await ale.run_once()

    assert ale._last_run_date() == "2026-08-09"
    assert len(sent) == 1
    assert "https://example.test/auto" in sent[0][0]
    assert sent[0][1] == "orders"


@pytest.mark.asyncio
async def test_run_once_on_failure_keeps_day_unmarked(tmp_db):
    from services import auto_launch_export as ale

    sent = []

    async def _fake_send(msg, category):
        sent.append((msg, category))

    with patch.object(ale, "export_auto_launches",
                      side_effect=RuntimeError("google down")), \
         patch.object(ale, "send_admins", _fake_send), \
         patch.object(ale, "now_msk",
                      return_value=datetime(2026, 8, 9, 6, 1, tzinfo=_MSK)):
        await ale.run_once()

    assert ale._last_run_date() is None
    assert sent[0][1] == "errors"
