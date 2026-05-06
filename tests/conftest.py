"""Тестовые фикстуры. Каждый тест получает изолированную SQLite-БД во временной папке.

Мы не используем in-memory БД, потому что код продакшена открывает соединение через
sqlite3.connect(path_db) на каждый запрос (см. utils/sqlite3.py), и in-memory БД у разных
соединений — разные. Файловая БД во временной папке — самый прямой путь.
"""
from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path
from typing import Iterator

import pytest


def _make_config_stub() -> types.ModuleType:
    """Минимальный data.config для тестов — без реальных секретов."""
    stub = types.ModuleType("data.config")
    stub.path_database = "data/database.db"  # overridden by tmp_db monkeypatch
    stub.TOKEN = "test:token"
    stub.bot_version = "0.0.0"
    stub.YOOKASSA_TEST = ""
    stub.SHOP_ID = 0
    stub.SECRET_KEY = "test_secret"
    stub.support_tag = "test"
    stub.ADMINS = []
    stub.CODER = 0
    stub.botlink = "https://t.me/test"
    stub.channel_link = "https://t.me/test"
    stub.host = ""
    stub.user = ""
    stub.bd_name = ""
    stub.password = ""
    stub.fix_price = 6
    stub.prices = {}
    stub.services = {}
    stub.price_google = {}
    stub.price_yandex = {}
    stub.price_vk = {}
    stub.price_flamp = {}
    stub.price_2gis = {}
    stub.price_avito = {}
    stub.JWT_SECRET = "test_jwt_secret_placeholder_at_least_32_chars"
    stub.WEB_HOST = "127.0.0.1"
    stub.WEB_PORT = 8000
    return stub


# Inject before any module-level import of data.config (utils/sqlite3.py imports it at load time)
if "data.config" not in sys.modules:
    _stub = _make_config_stub()
    sys.modules["data.config"] = _stub
    # Also set as attribute on the data package so `from data import config` works
    import data as _data_pkg
    _data_pkg.config = _stub  # type: ignore[attr-defined]

from utils.sqlite3 import get_schema_statements  # noqa: E402


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
