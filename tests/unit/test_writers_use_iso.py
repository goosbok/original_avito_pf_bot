from datetime import datetime

from utils.dates import now_iso
from utils.other import get_date


def test_get_date_returns_iso_with_utc():
    result = get_date()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_now_iso_returns_iso_with_utc():
    result = now_iso()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0
