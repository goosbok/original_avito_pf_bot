"""Планировщик ежедневной выгрузки авто-запусков."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
         patch("utils.sender.send_admins", _fake_send), \
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
         patch("utils.sender.send_admins", _fake_send), \
         patch.object(ale, "now_msk",
                      return_value=datetime(2026, 8, 9, 6, 1, tzinfo=_MSK)):
        await ale.run_once()

    assert ale._last_run_date() is None
    assert sent[0][1] == "errors"


@pytest.mark.asyncio
async def test_loop_returns_immediately_when_disabled(tmp_db):
    """При выключенном флаге луп не должен даже смотреть на _is_due/run_once."""
    from services import auto_launch_export as ale

    with patch.object(ale.config, "PF_AUTO_EXPORT_ENABLED", False), \
         patch.object(ale, "run_once", AsyncMock()) as run_once_mock, \
         patch.object(ale, "_is_due") as is_due_mock:
        await ale.run_auto_export_loop()

    run_once_mock.assert_not_called()
    is_due_mock.assert_not_called()


@pytest.mark.asyncio
async def test_boot_check_failure_does_not_crash_loop(tmp_db):
    """sqlite-ошибка в _is_due на старте не должна ронять корутину лупа."""
    from services import auto_launch_export as ale

    class _StopLoop(Exception):
        pass

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _StopLoop()

    with patch.object(ale.config, "PF_AUTO_EXPORT_ENABLED", True), \
         patch.object(ale, "_is_due", side_effect=RuntimeError("database is locked")), \
         patch.object(ale, "run_once", AsyncMock()) as run_once_mock, \
         patch.object(ale.asyncio, "sleep", _fake_sleep):
        with pytest.raises(_StopLoop):
            await ale.run_auto_export_loop()

    # Boot-check упал целиком, поэтому catch-up run_once не вызывался, но
    # выполнение продолжилось в while-цикл (о чём говорит сам факт,
    # что мы дошли до _fake_sleep и получили _StopLoop, а не RuntimeError).
    run_once_mock.assert_not_called()
    assert sleep_calls


@pytest.mark.asyncio
async def test_loop_iter_failure_falls_back_to_fixed_delay(tmp_db):
    """Падение до собственного sleep (например, при расчёте delay) не должно
    превращать while True в busy-loop — луп обязан заснуть на фиксированную
    паузу перед следующей попыткой."""
    from services import auto_launch_export as ale

    class _StopLoop(Exception):
        pass

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise _StopLoop()

    with patch.object(ale.config, "PF_AUTO_EXPORT_ENABLED", True), \
         patch.object(ale, "_is_due", return_value=False), \
         patch.object(ale, "next_run_at", side_effect=RuntimeError("database is locked")), \
         patch.object(ale.asyncio, "sleep", _fake_sleep):
        with pytest.raises(_StopLoop):
            await ale.run_auto_export_loop()

    assert sleep_calls == [
        ale._LOOP_ERROR_RETRY_DELAY_SEC,
        ale._LOOP_ERROR_RETRY_DELAY_SEC,
    ]
