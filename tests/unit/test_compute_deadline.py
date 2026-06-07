"""compute_deadline(order, now=...) → ISO deadline = max(start, today) + days."""
from datetime import datetime, timezone

import pytest


def _fixed_now(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_no_start_date_uses_today(monkeypatch):
    from services import order_links
    order = {"position_name": "3/100", "start_date": None}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # Now is 2026-06-07; start = today; deadline = today + 3 days = 2026-06-10
    assert deadline.startswith("2026-06-10")


def test_start_date_in_future_adds_days_from_start(monkeypatch):
    from services import order_links
    order = {"position_name": "5/200", "start_date": "2026-06-15"}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # start = 2026-06-15; deadline = 2026-06-20
    assert deadline.startswith("2026-06-20")


def test_start_date_in_past_uses_today(monkeypatch):
    """Если юзер выбрал прошедшую дату (или backfill), стартуем сегодня."""
    from services import order_links
    order = {"position_name": "2/50", "start_date": "2026-06-01"}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # start_effective = max(2026-06-01, 2026-06-07) = 2026-06-07
    # deadline = 2026-06-09
    assert deadline.startswith("2026-06-09")


def test_invalid_position_name_raises(monkeypatch):
    from services import order_links
    order = {"position_name": "broken", "start_date": None}
    with pytest.raises(ValueError):
        order_links.compute_deadline(
            order, now=_fixed_now("2026-06-07T10:00:00+00:00")
        )


def test_returns_iso_with_tz(monkeypatch):
    from services import order_links
    order = {"position_name": "1/10", "start_date": None}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # Должно парситься обратно
    parsed = order_links.datetime.fromisoformat(deadline)
    assert parsed.tzinfo is not None


def test_invalid_start_date_falls_back_to_today_with_warning(caplog):
    import logging
    from services import order_links
    order = {"position_name": "3/100", "start_date": "15.06.2026"}
    with caplog.at_level(logging.WARNING, logger="services.order_links"):
        deadline = order_links.compute_deadline(
            order, now=_fixed_now("2026-06-07T10:00:00+00:00")
        )
    # Used today MSK (2026-06-07) + 3 days = 2026-06-10
    assert deadline.startswith("2026-06-10")
    assert any("invalid start_date" in rec.message for rec in caplog.records)
