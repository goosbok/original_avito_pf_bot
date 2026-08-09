"""Ежедневная выгрузка авто-запусков в Google Sheets.

Раз в сутки в PF_AUTO_EXPORT_HOUR_MSK перезаписывает вкладку «Авто запуски»
и кидает админам ссылку. Дата последней успешной выгрузки живёт в таблице
settings — по ней луп догоняет пропущенный день после рестарта контейнера.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from data import config
from utils.googlesheets import create_auto_tasks_sheet
from utils.sender import send_admins
from utils.sqlite3 import edit_setting, get_setting

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))

LAST_RUN_SETTING = "auto_export_last_run_date"


def now_msk() -> datetime:
    """Текущее время в МСК. Отдельная функция — чтобы патчить в тестах."""
    return datetime.now(timezone.utc).astimezone(_MSK)


def next_run_at(now: datetime, *, hour: int) -> datetime:
    """Ближайшие `hour`:00 МСК строго в будущем относительно `now`."""
    candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def export_auto_launches() -> str:
    """Перезаписать вкладку. Возвращает URL. Исключения не глотает."""
    return create_auto_tasks_sheet()


def _last_run_date() -> str | None:
    value = get_setting(LAST_RUN_SETTING)
    return str(value) if value else None


def _mark_run_done(day: str) -> None:
    edit_setting(LAST_RUN_SETTING, day)


def _is_due(now: datetime) -> bool:
    """Пропустили ли мы сегодняшнюю выгрузку."""
    if now.hour < config.PF_AUTO_EXPORT_HOUR_MSK:
        return False
    return _last_run_date() != now.date().isoformat()


async def run_once() -> None:
    """Одна выгрузка + уведомление. Ошибки логирует, наружу не пускает."""
    today = now_msk().date().isoformat()
    logger.info("auto_export.start date=%s", today)
    try:
        url = await asyncio.to_thread(export_auto_launches)
    except Exception:  # noqa: BLE001
        logger.exception("auto_export.failed date=%s", today)
        try:
            await send_admins(
                "⚠️ Не смог обновить выгрузку «Авто запуски». Подробности в логах.",
                category="errors",
            )
        except Exception:  # noqa: BLE001
            logger.exception("auto_export.error_notify_failed")
        return

    # Выгрузка сделана — фиксируем день до отправки сообщения. Упавшее
    # уведомление не повод гонять Sheets API повторно.
    _mark_run_done(today)
    logger.info("auto_export.done date=%s url=%s", today, url)
    try:
        await send_admins(
            f"📤 Выгрузка «Авто запуски» обновлена\n{url}",
            category="orders",
        )
    except Exception:  # noqa: BLE001
        logger.exception("auto_export.notify_failed date=%s", today)


async def run_auto_export_loop() -> None:
    """Cron-луп: догон пропуска при старте, дальше раз в сутки в час X."""
    if not config.PF_AUTO_EXPORT_ENABLED:
        logger.info("auto_export.loop disabled (PF_AUTO_EXPORT_ENABLED=false)")
        return

    hour = config.PF_AUTO_EXPORT_HOUR_MSK
    logger.info("auto_export.loop start hour=%s МСК", hour)

    now = now_msk()
    if _is_due(now):
        logger.info("auto_export.catchup date=%s", now.date().isoformat())
        await run_once()

    while True:
        now = now_msk()
        delay = (next_run_at(now, hour=hour) - now).total_seconds()
        await asyncio.sleep(max(delay, 1.0))
        await run_once()
