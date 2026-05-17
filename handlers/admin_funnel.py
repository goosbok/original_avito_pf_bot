"""Admin panel: funnel analytics — service picker + period picker + chart."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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


# Step strings come from FUNNEL_STEPS (developer-controlled, ASCII identifiers).
# If that contract ever changes, escape them via html.escape() before embedding.
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


async def _try_delete(call: CallbackQuery) -> None:
    try:
        await call.message.delete()
    except Exception as exc:
        logger.debug("could not delete message: %r", exc)


@dp.callback_query_handler(text="funnel_menu", state='*')
async def funnel_menu(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    await call.answer()
    await call.message.answer(
        "📊 Воронка — выбери сервис:",
        reply_markup=funnel_service_kb(),
    )
    await _try_delete(call)


@dp.callback_query_handler(text_startswith="funnel:", state='*')
async def funnel_router(call: CallbackQuery, state: FSMContext):
    """Branch on number of colon-separated parts.

    funnel:<service>             → period picker
    funnel:<service>:<period>    → chart
    """
    if str(call.from_user.id) not in get_admins():
        return
    parts = call.data.split(":")
    if len(parts) == 2:
        await _funnel_service(call, parts[1])
    elif len(parts) == 3:
        await _funnel_period(call, parts[1], parts[2])
    else:
        logger.warning("funnel_router: unexpected callback shape %r", call.data)
        await call.answer()


async def _funnel_service(call: CallbackQuery, service: str) -> None:
    if service not in FUNNEL_STEPS:
        logger.warning("funnel_router: unknown service %r", service)
        await call.answer()
        return
    await call.answer()
    label = SERVICE_LABELS.get(service, service)
    await call.message.answer(
        f"📊 {label} — выбери период:",
        reply_markup=funnel_period_kb(service),
    )
    await _try_delete(call)


async def _funnel_period(call: CallbackQuery, service: str, period_suffix: str) -> None:
    if service not in FUNNEL_STEPS:
        logger.warning("funnel_router: unknown service %r", service)
        await call.answer()
        return
    try:
        from_dt, to_dt = _resolve_period(period_suffix)
    except ValueError:
        logger.warning("funnel_router: unknown period %r", period_suffix)
        await call.answer()
        return
    await call.answer()

    stats = get_funnel_stats(service, from_dt=from_dt, to_dt=to_dt)
    period_label = _PERIOD_LABELS.get(period_suffix, period_suffix)
    chart_title = f"Воронка «{SERVICE_LABELS.get(service, service)}» за {period_label}"
    buf = render_chart(service, from_dt=from_dt, to_dt=to_dt, title=chart_title)
    caption = _format_caption(service, period_suffix, from_dt, to_dt, stats)

    try:
        await call.message.answer_photo(
            buf,
            caption=caption,
            parse_mode="HTML",
            reply_markup=funnel_period_kb(service),
        )
    finally:
        buf.close()
    await _try_delete(call)
