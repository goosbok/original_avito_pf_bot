import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services import auth_telegram, identity
from services.exceptions import OTPInvalid


def _seed_user(tmp_db: Path, tg_id: int, user_name: str | None = None) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (tg_id, user_name, "U", 0, "2026-01-01"),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2026-01-01')",
            (tg_id, str(tg_id)),
        )
        con.commit()


def test_resolve_numeric_id(tmp_db: Path):
    assert auth_telegram.resolve_telegram_id("123456") == 123456
    assert auth_telegram.resolve_telegram_id("  789  ") == 789


def test_resolve_username(tmp_db: Path):
    _seed_user(tmp_db, 555, user_name="alice")
    assert auth_telegram.resolve_telegram_id("@alice") == 555
    assert auth_telegram.resolve_telegram_id("alice") == 555
    assert auth_telegram.resolve_telegram_id("ALICE") == 555


def test_resolve_username_modern_user(tmp_db: Path):
    """Modern users: users.id is auto-increment, real Telegram ID is in auth_providers.
    Bug: resolve_telegram_id was returning users.id (1) instead of the actual tg_id.
    """
    real_tg_id = 987654321
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date) VALUES (?, ?, 0, ?)",
            ("modernuser", "Modern", "2026-01-01"),
        )
        internal_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2026-01-01')",
            (internal_id, str(real_tg_id)),
        )
        con.commit()
    assert auth_telegram.resolve_telegram_id("@modernuser") == real_tg_id


def test_resolve_username_not_found(tmp_db: Path):
    with pytest.raises(OTPInvalid):
        auth_telegram.resolve_telegram_id("@nobody")


def test_request_code_sends_message(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    _seed_user(tmp_db, 777, user_name="bob")

    captured = {}
    def fake_send(token, tg_id, text):
        captured.update(token=token, tg_id=tg_id, text=text)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    result_tg_id = auth_telegram.request_code("@bob")
    assert result_tg_id == 777
    assert captured["tg_id"] == 777
    assert captured["token"] == "test:token"
    assert "код" in captured["text"].lower()


def test_verify_code_login_creates_user(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")

    captured_code = {}
    def fake_send(token, tg_id, text):
        # Парсим код из текста для теста
        import re
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    auth_telegram.request_code("999111")  # numeric id, не существующий юзер
    user_id = auth_telegram.verify_code_login("999111", captured_code["code"])
    assert user_id > 0
    assert identity.find_user_id_by_provider("telegram", "999111") == user_id


def test_verify_code_link_attaches_to_current_user(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    captured_code = {}
    def fake_send(token, tg_id, text):
        import re
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    # Создаём email-юзера
    from services import auth_email
    uid = auth_email.register("a@b.com", "password123")

    auth_telegram.request_code("888222", purpose="link", user_id_to_link=uid)
    auth_telegram.verify_code_link("888222", captured_code["code"], uid)
    assert identity.find_user_id_by_provider("telegram", "888222") == uid


def test_verify_code_wrong_code(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    auth_telegram.request_code("111222")
    with pytest.raises(OTPInvalid):
        auth_telegram.verify_code_login("111222", "000000")
