"""Telethon e2e test client.

Credentials and session are read from the project .env file (never committed).
Session file: .test_session.session (also gitignored).

Usage:
    python3 -m pytest tests/e2e/ -v
    # or run a scenario directly:
    python3 tests/e2e/test_basic_flow.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.custom import Message

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_ID   = int(os.environ["TEST_TG_API_ID"])
API_HASH = os.environ["TEST_TG_API_HASH"]
BOT      = os.environ.get("BOT_LINK", "").replace("https://t.me/", "@") or "@opt_test_bot"
SESSION  = str(Path(__file__).resolve().parents[2] / ".test_session")


def get_client() -> TelegramClient:
    return TelegramClient(SESSION, API_ID, API_HASH)


async def send_and_wait(client: TelegramClient, text: str, timeout: float = 3.0) -> Message:
    """Send a message to the bot and return its reply."""
    await client.send_message(BOT, text)
    await asyncio.sleep(timeout)
    msgs = await client.get_messages(BOT, limit=1)
    return msgs[0] if msgs else None


async def click_button(client: TelegramClient, message: Message, button_text: str, timeout: float = 3.0) -> Message:
    """Click an inline button by its text label and return the bot reply."""
    await message.click(text=button_text)
    await asyncio.sleep(timeout)
    msgs = await client.get_messages(BOT, limit=1)
    return msgs[0] if msgs else None


def button_texts(message: Message) -> list[str]:
    """Extract all inline button labels from a message."""
    if not message or not message.reply_markup:
        return []
    return [btn.text for row in message.reply_markup.rows for btn in row.buttons]


async def click_first_matching_button(
    client: TelegramClient, message: Message, pattern: str, timeout: float = 3.0
) -> Message:
    """Click the first inline button whose text contains *pattern* and return the bot reply."""
    if message and message.reply_markup:
        for i, row in enumerate(message.reply_markup.rows):
            for j, btn in enumerate(row.buttons):
                if pattern in btn.text:
                    await message.click(i, j)
                    await asyncio.sleep(timeout)
                    msgs = await client.get_messages(BOT, limit=1)
                    return msgs[0] if msgs else None
    return None
