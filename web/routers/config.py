"""Public client-facing config (bot links, etc.).

Frontend fetches this once on mount to build accurate deep-links
(`?start=connect`) and not hard-code the bot username.
"""
from __future__ import annotations

import re

from fastapi import APIRouter

from data import config as bot_config

router = APIRouter(prefix="/api/config", tags=["config"])


def _extract_bot_username(bot_url: str) -> str:
    """https://t.me/AVITOPF_bot → 'AVITOPF_bot'. Falls back to 'AVITOPF_bot'."""
    m = re.search(r"t\.me/([A-Za-z0-9_]+)", bot_url or "")
    return m.group(1) if m else "AVITOPF_bot"


@router.get("")
async def get_config() -> dict:
    bot_url = bot_config.botlink or "https://t.me/AVITOPF_bot"
    bot_username = _extract_bot_username(bot_url)
    return {
        "bot_url": bot_url,
        "bot_username": bot_username,
        "bot_connect_url": f"{bot_url}?start=connect",
    }
