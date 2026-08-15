"""Единая точка работы с датами: writers, дисплей-форматтер, толерантный парсер.

Хранение: ISO 8601 + UTC (без микросекунд).
Дисплей:  dd.mm.yyyy HH:MM в Moscow time (Europe/Moscow, UTC+3).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_MSK = timezone(timedelta(hours=3))


def now_iso() -> str:
    """Текущий момент в ISO+UTC без микросекунд."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_any(value: str | None) -> datetime | None:
    """Толерантный парсер: ISO+TZ, ISO без TZ (SQLite CURRENT_TIMESTAMP),
    legacy dd.mm.yyyy HH:MM:SS. Возвращает None на пустой / битый ввод."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def format_display(value: str | None) -> str:
    """Превращает любой известный формат даты в 'dd.mm.yyyy HH:MM' в Moscow time.
    Пустой/битый ввод → пустая строка."""
    dt = parse_any(value)
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # Naive: legacy писалось через datetime.today() — серверное (Moscow) время.
        # Для SQLite CURRENT_TIMESTAMP (тоже naive, но UTC по спеке) сделаем
        # эвристику: строки с разделителем '-' в дате-части трактуем как UTC,
        # остальные ('dd.mm.YYYY ...') как MSK.
        sample = str(value).strip()
        date_part = sample.split(" ", 1)[0] if " " in sample else sample
        if "-" in date_part:
            dt = dt.replace(tzinfo=timezone.utc).astimezone(_MSK)
    else:
        dt = dt.astimezone(_MSK)
    return dt.strftime("%d.%m.%Y %H:%M")
