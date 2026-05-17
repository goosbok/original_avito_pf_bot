"""Admin panel: funnel analytics — service picker + period picker + chart."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery

from data.loader import dp
from keyboards.inline_keyboards import funnel_period_kb, funnel_service_kb
from services.funnel import (
    FUNNEL_STEPS,
    SERVICE_LABELS,
    get_funnel_stats,
    render_chart,
)
from utils.sqlite3 import get_admins

logger = logging.getLogger(__name__)

_PERIOD_LABELS = {
    "today": "сегодня",
    "7d": "7 дней",
    "30d": "30 дней",
    "all": "всё время",
}


def _resolve_period(suffix: str) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    if suffix == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if suffix == "7d":
        return now - timedelta(days=7), now
    if suffix == "30d":
        return now - timedelta(days=30), now
    if suffix == "all":
        return None, None
    raise ValueError(f"Unknown period suffix: {suffix!r}")


def _format_caption(
    service: str,
    period_suffix: str,
    from_dt: datetime | None,
    to_dt: datetime | None,
    stats: list[dict],
) -> str:
    period_label = _PERIOD_LABELS.get(period_suffix, period_suffix)
    if from_dt is not None and to_dt is not None:
        range_str = f"{from_dt.date()} — {to_dt.date()}"
    else:
        range_str = "всё время"
    header = f"{SERVICE_LABELS.get(service, service)} · {period_label} ({range_str})"

    body_lines = []
    width = max(len(r["step"]) for r in stats) + 2
    for r in stats:
        users_str = str(r["users"]).rjust(6)
        line = f"{r['step']:<{width}}{users_str}"
        if r["drop_off_pct"] is not None:
            line += f"  (-{r['drop_off_pct']}%)"
        body_lines.append(line)

    first = stats[0]["users"] if stats else 0
    last = stats[-1]["users"] if stats else 0
    conv_line = ""
    if first > 0:
        conv = round(last / first * 100, 1)
        conv_line = f"\n\nКонверсия в заказ: {conv}%"

    return f"{header}\n\n<pre>{chr(10).join(body_lines)}</pre>{conv_line}"


@dp.callback_query_handler(text="funnel_menu", state='*')
async def funnel_menu(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    await call.message.answer(
        "📊 Воронка — выбери сервис:",
        reply_markup=funnel_service_kb(),
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(
    lambda c: c.data is not None and c.data.startswith("funnel:") and c.data.count(":") == 1,
    state='*',
)
async def funnel_service(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    service = call.data.split(":", 1)[1]
    if service not in FUNNEL_STEPS:
        return
    label = SERVICE_LABELS.get(service, service)
    await call.message.answer(
        f"📊 {label} — выбери период:",
        reply_markup=funnel_period_kb(service),
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(
    lambda c: c.data is not None and c.data.startswith("funnel:") and c.data.count(":") == 2,
    state='*',
)
async def funnel_period(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    _, service, period_suffix = call.data.split(":")
    if service not in FUNNEL_STEPS:
        return
    try:
        from_dt, to_dt = _resolve_period(period_suffix)
    except ValueError:
        return

    stats = get_funnel_stats(service, from_dt=from_dt, to_dt=to_dt)
    period_label = _PERIOD_LABELS.get(period_suffix, period_suffix)
    chart_title = f"Воронка «{SERVICE_LABELS.get(service, service)}» за {period_label}"
    buf = render_chart(service, from_dt=from_dt, to_dt=to_dt, title=chart_title)
    caption = _format_caption(service, period_suffix, from_dt, to_dt, stats)

    await call.message.answer_photo(
        buf,
        caption=caption,
        parse_mode="HTML",
        reply_markup=funnel_period_kb(service),
    )
    buf.close()
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
