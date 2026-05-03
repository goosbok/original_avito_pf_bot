"""Тестовые фикстуры. Каждый тест получает изолированную SQLite-БД во временной папке.

Мы не используем in-memory БД, потому что код продакшена открывает соединение через
sqlite3.connect(path_db) на каждый запрос (см. utils/sqlite3.py), и in-memory БД у разных
соединений — разные. Файловая БД во временной папке — самый прямой путь.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from utils.sqlite3 import get_schema_statements


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Создаёт пустую БД с продакшен-схемой и подменяет path_database во всех модулях."""
    db_path = tmp_path / "test.db"

    with sqlite3.connect(db_path) as con:
        for _table, ddl, _cols in get_schema_statements():
            con.execute(ddl)
        con.commit()

    monkeypatch.setattr("data.config.path_database", str(db_path), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db_path), raising=False)

    yield db_path
