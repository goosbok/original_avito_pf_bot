"""Tests for services.list_broadcast — рассылка по списку из CSV."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram.utils.exceptions import BotBlocked, RetryAfter, TelegramAPIError

from services.list_broadcast import (
    RecipientsFileError,
    parse_recipients_csv,
    resolve_recipients,
    send_to_list,
    undelivered_csv,
)


def test_parse_export_format_with_bom_and_header():
    data = (
        "﻿telegram_id,username,first_name,spent_rub\n"
        "8953117272,@a,Артем,1110\n"
        "678075535,@b,Ilnur,3000\n"
    ).encode("utf-8")
    parsed = parse_recipients_csv(data)
    assert parsed.tg_ids == [8953117272, 678075535]
    assert parsed.invalid == 0


def test_parse_picks_telegram_id_column_not_first():
    data = "username;telegram_id\n@a;111\n@b;222\n".encode("utf-8")
    assert parse_recipients_csv(data).tg_ids == [111, 222]


def test_parse_headerless_first_column_dedup_and_invalid():
    data = b"111\n222\n111\nabc\n\n333\n"
    parsed = parse_recipients_csv(data)
    assert parsed.tg_ids == [111, 222, 333]
    assert parsed.invalid == 1


def test_parse_cp1251_excel_export():
    data = "telegram_id;имя\n111;Вася\n".encode("cp1251")
    assert parse_recipients_csv(data).tg_ids == [111]


@pytest.mark.parametrize("data", [b"", b"telegram_id\n", b"name\nfoo\nbar\n"])
def test_parse_rejects_files_without_ids(data):
    with pytest.raises(RecipientsFileError):
        parse_recipients_csv(data)


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        for uid, tg in [(1, "111"), (2, "222"), (3, "333")]:
            con.execute(
                "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
                "VALUES (?, NULL, 'U', 0, '2026-01-01')", (uid,))
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                "VALUES (?, 'telegram', ?, '2026-01-01')", (uid, tg))
        con.execute("INSERT INTO settings(parametr, description, value) "
                    "VALUES ('spam_exclude', 'x', '333')")
        con.commit()


def test_resolve_splits_unknown_and_excluded(tmp_db: Path):
    _seed(tmp_db)
    r = resolve_recipients([111, 999, 222, 333])
    assert r.send == [111, 222]
    assert r.unknown == [999]
    assert r.excluded == [333]


PAYLOAD = {"from_chat_id": 500, "message_id": 42}


@pytest.mark.asyncio
async def test_send_counts_delivered_blocked_failed_and_retries():
    bot = AsyncMock()
    calls = {"n": 0}

    async def copy_message(chat_id, from_chat_id, message_id):
        assert (from_chat_id, message_id) == (500, 42)
        if chat_id == 2:
            raise BotBlocked("Forbidden: bot was blocked by the user")
        if chat_id == 3:
            raise TelegramAPIError("boom")
        if chat_id == 4:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RetryAfter(0)

    bot.copy_message.side_effect = copy_message
    report = await send_to_list(bot, [1, 2, 3, 4], PAYLOAD, delay=0)
    assert report.delivered == 2
    assert report.blocked == [2]
    assert report.failed == [3]
    assert calls["n"] == 2

    csv_text = undelivered_csv(report).decode("utf-8-sig")
    assert "2,blocked" in csv_text and "3,error" in csv_text


@pytest.mark.asyncio
async def test_send_copies_message_without_rebuilding_it():
    bot = AsyncMock()
    report = await send_to_list(bot, [7], PAYLOAD, delay=0)
    bot.copy_message.assert_awaited_once_with(chat_id=7, from_chat_id=500, message_id=42)
    bot.send_message.assert_not_called()
    assert report.delivered == 1


@pytest.mark.asyncio
async def test_all_users_broadcast_skips_admins_vip_and_no_tg(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        rows = [(1, "111", None), (2, "222", 1), (3, "333", None), (4, None, None)]
        for uid, tg, vip in rows:
            con.execute("INSERT INTO users(id, user_name, first_name, balance, reg_date, is_vip) "
                        "VALUES (?, NULL, 'U', 0, '2026-01-01', ?)", (uid, vip))
            if tg:
                con.execute("INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                            "VALUES (?, 'telegram', ?, '2026-01-01')", (uid, tg))
        con.execute("INSERT INTO settings(parametr, description, value) VALUES ('admins', 'a', '333')")
        con.commit()
    import handlers.admin_broadcast as ab
    assert ab._all_users_recipients() == [111]


def test_handlers_import_and_menu_button(tmp_db: Path):
    import handlers.admin_broadcast as ab
    from keyboards.inline_keyboards import messages_kb

    assert ab.ListSpam.WaitFile and ab.ListSpam.WaitMessage
    callbacks = [b.callback_data for row in messages_kb().inline_keyboard for b in row]
    assert "send_list_spam" in callbacks
