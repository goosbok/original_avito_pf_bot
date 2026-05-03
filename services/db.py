"""Общий слой работы с SQLite для сервисов.

Сюда добавляются только утилиты, которые не подходят к конкретному домену
(connect/dict_factory). Доменные репозитории — рядом с сервисами.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Открыть SQLite-соединение с dict_factory.

    Путь к БД читается из data.config.path_database на каждый вызов, чтобы
    pytest monkeypatch мог подменять его в фикстурах.
    """
    from data import config  # noqa: PLC0415 — ленивый импорт ради monkeypatch

    con = sqlite3.connect(config.path_database)
    con.row_factory = _dict_factory
    try:
        yield con
    finally:
        con.close()
