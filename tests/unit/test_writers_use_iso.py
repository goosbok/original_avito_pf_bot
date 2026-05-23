from datetime import datetime

from services.guest_orders import _now
from utils.other import get_date


def test_get_date_returns_iso_with_utc():
    result = get_date()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_guest_orders_now_returns_iso_with_utc():
    result = _now()
    parsed = datetime.fromisoformat(result)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0
