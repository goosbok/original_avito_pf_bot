"""Cutoff 04:00 МСК для biza-старта.

Бизнес-сутка биза начинается в 04:00 МСК. Заказы, оформленные:
  - ≤ 04:00 МСК       → старт в эту же дату в 10:00 МСК (день в день);
  - > 04:00 МСК       → старт на следующий день в 10:00 МСК.

Поэтому все заказы с момента (T-1).04:01 МСК до T.04:00 МСК включительно
попадают в одну партию запуска — T.10:00 МСК.
"""
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.pf_executor_api import (
    _MSK,
    _effective_start_msk,
    submit_link,
)


# ── _effective_start_msk: чистая функция от текущего МСК-времени ────────────

@pytest.mark.parametrize("hour,minute,expected_delta_days", [
    (0,  0, 0),   # 00:00 МСК → сегодня
    (3, 59, 0),   # 03:59 МСК → сегодня
    (4,  0, 0),   # 04:00 МСК — граница включена → сегодня
    (4,  1, 1),   # 04:01 МСК → завтра
    (12, 0, 1),   # полдень → завтра
    (23, 59, 1),  # 23:59 МСК → завтра
])
def test_effective_start_msk_boundary(hour, minute, expected_delta_days):
    fake = datetime(2026, 12, 11, hour, minute, tzinfo=_MSK)
    expected = fake.date() + timedelta(days=expected_delta_days)
    assert _effective_start_msk(fake) == expected


def test_effective_start_msk_requires_tz_aware():
    naive = datetime(2026, 12, 11, 12, 0)
    with pytest.raises(ValueError):
        _effective_start_msk(naive)


# ── submit_link payload uses cutoff for `dates` ────────────────────────────

@pytest.fixture(autouse=True)
def _biza_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("data.config.BIZA_API_KEY", "test-key", raising=False)


def _resp(status, json_body):
    r = MagicMock(status_code=status)
    r.json.return_value = json_body
    return r


_OK_RESP = _resp(200, {"success": True, "data": {"task_ids": [1], "tasks_added": 1}})


def _order(position="1/30", start_date=None):
    return {"position_name": position, "start_date": start_date,
            "contacts": 0, "phone": None}


@pytest.mark.parametrize("now_hour,now_min,expected_first_date", [
    # ── Заказ оформлен 11.12 до 04:00 МСК → старт 11.12 ─────────────────
    (0,  0,  "2026_12_11"),
    (4,  0,  "2026_12_11"),
    # ── Заказ оформлен 11.12 после 04:00 МСК → старт 12.12 ──────────────
    (4,  1,  "2026_12_12"),
    (23, 53, "2026_12_12"),  # ← наш реальный кейс Алексея @specsnosspb
])
def test_submit_link_dates_respect_msk_cutoff(now_hour, now_min, expected_first_date):
    fake_now_msk = datetime(2026, 12, 11, now_hour, now_min, tzinfo=_MSK)
    with patch("services.pf_executor_api._now_msk", return_value=fake_now_msk), \
         patch("services.pf_executor_api._session.post", return_value=_OK_RESP) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(position="1/30"), search_phrase="x")
    dates = post.call_args.kwargs["json"]["tasks"][0]["dates"]
    assert dates[0] == expected_first_date


def test_submit_link_multiday_dates_extend_from_effective_start():
    """3-дневная задача в 23:00 МСК — старт завтра, dates на 3 дня подряд."""
    fake = datetime(2026, 12, 11, 23, 0, tzinfo=_MSK)
    with patch("services.pf_executor_api._now_msk", return_value=fake), \
         patch("services.pf_executor_api._session.post", return_value=_OK_RESP) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(position="3/10"), search_phrase="x")
    dates = post.call_args.kwargs["json"]["tasks"][0]["dates"]
    assert dates == ["2026_12_12", "2026_12_13", "2026_12_14"]


def test_submit_link_explicit_future_start_date_respected():
    """Если юзер явно выбрал start_date в будущем — используем его."""
    fake = datetime(2026, 12, 11, 12, 0, tzinfo=_MSK)
    with patch("services.pf_executor_api._now_msk", return_value=fake), \
         patch("services.pf_executor_api._session.post", return_value=_OK_RESP) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(position="1/30", start_date="2026-12-20"),
                    search_phrase="x")
    dates = post.call_args.kwargs["json"]["tasks"][0]["dates"]
    assert dates[0] == "2026_12_20"


def test_submit_link_explicit_past_start_date_bumped_to_effective():
    """Юзер указал прошлое start_date — поднимаем до effective_start (cutoff)."""
    fake = datetime(2026, 12, 11, 12, 0, tzinfo=_MSK)  # > 04:00 → effective=12.12
    with patch("services.pf_executor_api._now_msk", return_value=fake), \
         patch("services.pf_executor_api._session.post", return_value=_OK_RESP) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(position="1/30", start_date="2026-12-01"),
                    search_phrase="x")
    dates = post.call_args.kwargs["json"]["tasks"][0]["dates"]
    assert dates[0] == "2026_12_12"


def test_submit_link_today_explicit_start_date_late_evening_bumped():
    """Юзер выбрал start_date=today, но оформил в 23:53 МСК → старт завтра."""
    fake = datetime(2026, 12, 11, 23, 53, tzinfo=_MSK)
    with patch("services.pf_executor_api._now_msk", return_value=fake), \
         patch("services.pf_executor_api._session.post", return_value=_OK_RESP) as post:
        submit_link("https://avito.ru/x_1234567890",
                    _order(position="1/30", start_date="2026-12-11"),
                    search_phrase="x")
    dates = post.call_args.kwargs["json"]["tasks"][0]["dates"]
    assert dates[0] == "2026_12_12"
