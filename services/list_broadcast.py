"""Рассылки из админки бота: по списку Telegram ID из CSV и по всем пользователям.

Разбор файла и сама отправка вынесены сюда из handlers/admin_broadcast.py,
чтобы их можно было тестировать без aiogram-диспетчера.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field

from aiogram.utils.exceptions import (
    BotBlocked,
    ChatNotFound,
    RetryAfter,
    TelegramAPIError,
    UserDeactivated,
)

from services.db import connect
from utils.sqlite3 import get_spam_exclude

logger = logging.getLogger(__name__)

# Telegram позволяет ~30 сообщений/сек в разные чаты; держимся с запасом.
SEND_DELAY_SEC = 0.05
MAX_RECIPIENTS = 5000
ID_COLUMNS = ("telegram_id", "tg_id", "id")


class RecipientsFileError(ValueError):
    """Файл не удалось разобрать как список Telegram ID."""


@dataclass
class ParsedRecipients:
    tg_ids: list[int]
    invalid: int  # строки, где в колонке ID не число


def parse_recipients_csv(data: bytes) -> ParsedRecipients:
    """Достаёт Telegram ID из CSV.

    Берёт колонку telegram_id / tg_id / id, если есть заголовок, иначе первую
    колонку. Дубли убираются с сохранением порядка.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise RecipientsFileError("файл пустой")

    try:
        delimiter = csv.Sniffer().sniff(lines[0], delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(lines, delimiter=delimiter))

    header = [c.strip().lower() for c in rows[0]]
    col = next((header.index(name) for name in ID_COLUMNS if name in header), None)
    if col is not None:
        rows = rows[1:]
    else:
        col = 0

    seen: set[int] = set()
    tg_ids: list[int] = []
    invalid = 0
    for row in rows:
        raw = row[col].strip() if col < len(row) else ""
        if not raw.isdigit():
            invalid += 1
            continue
        tg_id = int(raw)
        if tg_id not in seen:
            seen.add(tg_id)
            tg_ids.append(tg_id)

    if not tg_ids:
        raise RecipientsFileError("в файле не нашлось ни одного Telegram ID")
    if len(tg_ids) > MAX_RECIPIENTS:
        raise RecipientsFileError(f"слишком много получателей: {len(tg_ids)} (максимум {MAX_RECIPIENTS})")
    return ParsedRecipients(tg_ids=tg_ids, invalid=invalid)


@dataclass
class ResolvedRecipients:
    send: list[int]
    unknown: list[int]   # нет в базе бота — бот не может им написать
    excluded: list[int]  # в списке «Исключены из рассылки»


def resolve_recipients(tg_ids: list[int]) -> ResolvedRecipients:
    with connect() as con:
        known = {
            int(r["identifier"]) for r in con.execute(
                "SELECT identifier FROM auth_providers WHERE provider = 'telegram'"
            )
            if str(r["identifier"]).isdigit()
        }
    excluded_ids = set(get_spam_exclude())
    result = ResolvedRecipients(send=[], unknown=[], excluded=[])
    for tg_id in tg_ids:
        if tg_id not in known:
            result.unknown.append(tg_id)
        elif str(tg_id) in excluded_ids:
            result.excluded.append(tg_id)
        else:
            result.send.append(tg_id)
    return result


@dataclass
class SendReport:
    delivered: int = 0
    blocked: list[int] = field(default_factory=list)  # бот заблокирован / аккаунт удалён
    failed: list[int] = field(default_factory=list)   # прочие ошибки


async def send_to_list(bot, tg_ids: list[int], payload: dict,
                       delay: float = SEND_DELAY_SEC) -> SendReport:
    """Копирует сообщение админа (payload: from_chat_id + message_id) каждому tg_id.

    copy_message сохраняет форматирование, ссылки и любые вложения (видео,
    голосовые, файлы) и не добавляет плашку «Переслано из…».
    """
    report = SendReport()
    for tg_id in tg_ids:
        for attempt in range(2):
            try:
                await bot.copy_message(chat_id=tg_id, from_chat_id=payload["from_chat_id"],
                                       message_id=payload["message_id"])
                report.delivered += 1
            except RetryAfter as e:
                if attempt == 0:
                    await asyncio.sleep(e.timeout + 1)
                    continue
                report.failed.append(tg_id)
            except (BotBlocked, UserDeactivated, ChatNotFound):
                report.blocked.append(tg_id)
            except TelegramAPIError:
                logger.warning("broadcast: failed to send to tg_id=%s", tg_id, exc_info=True)
                report.failed.append(tg_id)
            break
        await asyncio.sleep(delay)
    return report


def undelivered_csv(report: SendReport) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["telegram_id", "reason"])
    w.writerows((tg_id, "blocked") for tg_id in report.blocked)
    w.writerows((tg_id, "error") for tg_id in report.failed)
    return buf.getvalue().encode("utf-8-sig")
