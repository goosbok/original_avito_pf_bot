"""Tests for handlers/support_web.py — admin reply handler."""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# handlers/__init__.py auto-imports all handlers which pull in aiogram 2.x-only
# symbols (FSMContext) not present in the aiogram 3.x installed in this env.
# Pre-stub the package so that 'from handlers.support_web import ...' loads
# just the one file without executing __init__.py.
if "handlers" not in sys.modules:
    _pkg = types.ModuleType("handlers")
    _pkg.__path__ = [str(Path(__file__).parent.parent.parent / "handlers")]
    _pkg.__package__ = "handlers"
    sys.modules["handlers"] = _pkg

# dp.message_handler is a MagicMock by default; it wraps and replaces the
# decorated function so the handler becomes uncallable. Replace with a real
# pass-through decorator so admin_reply_to_support stays a coroutine.
import data.loader as _loader  # noqa: E402

def _passthrough(*args, **kwargs):
    def _decorator(fn):
        return fn
    return _decorator

_loader.dp.message_handler = _passthrough


def _make_reply_message(
    from_user_id: int,
    chat_id: int,
    replied_text: str,
    msg_text: str,
) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = from_user_id
    msg.chat.id = chat_id
    msg.text = msg_text
    msg.message_id = 42
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.text = replied_text
    msg.bot.send_message = AsyncMock()
    return msg


def _stub_httpx(monkeypatch) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")


def _seed(tmp_db: Path, admin_value: str = "111") -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text, created_at) "
            "VALUES (7, 10, 'user', 'Help!', '2026-01-01 00:00:00')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', ?)",
            (admin_value,),
        )
        con.commit()


def test_admin_reply_saved(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    _stub_httpx(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=111,
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="Here is your answer",
    )

    from handlers.support_web import admin_reply_to_support
    asyncio.run(admin_reply_to_support(msg))

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT direction, text FROM support_messages WHERE direction = 'admin'"
        ).fetchone()
    assert row == ("admin", "Here is your answer")


def test_reply_from_wrong_chat_ignored(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=111,
        chat_id=99999,  # not the support group
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="answer",
    )

    from handlers.support_web import admin_reply_to_support
    asyncio.run(admin_reply_to_support(msg))

    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT count(*) FROM support_messages WHERE direction = 'admin'"
        ).fetchone()[0]
    assert count == 0


def test_non_admin_reply_ignored(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=9999,  # not in admin list
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="answer",
    )

    from handlers.support_web import admin_reply_to_support
    asyncio.run(admin_reply_to_support(msg))

    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT count(*) FROM support_messages WHERE direction = 'admin'"
        ).fetchone()[0]
    assert count == 0


def test_admin_stored_as_internal_id_can_reply(monkeypatch, tmp_db: Path):
    """Regression: admin stored as internal user_id (not TG ID) must still be able to reply."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text, created_at) "
            "VALUES (7, 10, 'user', 'Help!', '2026-01-01 00:00:00')"
        )
        # Admin stored as internal user_id=42; their Telegram ID is 999888777
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (42, 'telegram', '999888777', '2026-01-01 00:00:00')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '42')"
        )
        con.commit()

    _stub_httpx(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=999888777,  # Telegram ID, while admin list stores internal ID 42
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="Fixed!",
    )

    from handlers.support_web import admin_reply_to_support
    asyncio.run(admin_reply_to_support(msg))

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT direction, text FROM support_messages WHERE direction = 'admin'"
        ).fetchone()
    assert row == ("admin", "Fixed!")
