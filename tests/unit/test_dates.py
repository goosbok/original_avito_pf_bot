from datetime import datetime, timezone

import pytest

from utils.dates import format_display, now_iso, parse_any


def test_now_iso_returns_iso_with_utc_timezone():
    result = now_iso()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_now_iso_no_microseconds():
    result = now_iso()
    assert "." not in result.split("+")[0]


def test_parse_any_iso_with_tz():
    dt = parse_any("2026-05-23T11:30:00+00:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 23
    assert dt.tzinfo is not None


def test_parse_any_legacy_dd_mm_yyyy():
    dt = parse_any("23.05.2026 14:30:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 23 and dt.hour == 14


def test_parse_any_sqlite_current_timestamp():
    dt = parse_any("2026-05-23 11:30:00")
    assert dt is not None
    assert dt.year == 2026 and dt.hour == 11


@pytest.mark.parametrize("value", [None, "", "   ", "not a date", "13.13.2026 25:00:00"])
def test_parse_any_invalid_returns_none(value):
    assert parse_any(value) is None


def test_format_display_iso_utc_converts_to_moscow():
    assert format_display("2026-05-23T11:30:00+00:00") == "23.05.2026 14:30"


def test_format_display_iso_with_microseconds():
    assert format_display("2026-05-23T11:30:00.123456+00:00") == "23.05.2026 14:30"


def test_format_display_legacy_passes_through_as_naive_moscow():
    assert format_display("23.05.2026 14:30:00") == "23.05.2026 14:30"


def test_format_display_sqlite_current_timestamp_treated_as_utc():
    assert format_display("2026-05-23 11:30:00") == "23.05.2026 14:30"


@pytest.mark.parametrize("value", [None, "", "   ", "garbage"])
def test_format_display_invalid_returns_empty(value):
    assert format_display(value) == ""
