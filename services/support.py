"""Support-message CRUD for web chat relay."""
from __future__ import annotations

from utils.sqlite3 import (
    support_add_message,
    support_find_by_tg_message_id,
    support_get_messages,
)


def create_user_message(user_id: int, text: str) -> int:
    """Save a user question. Returns new row id."""
    return support_add_message(user_id, "user", text)


def create_admin_reply(user_id: int, text: str, tg_message_id: int | None = None) -> int:
    """Save admin reply for a user. Returns new row id."""
    return support_add_message(user_id, "admin", text, tg_message_id)


def get_conversation(user_id: int) -> list[dict]:
    return support_get_messages(user_id)


def find_message_by_tg_id(tg_message_id: int) -> dict | None:
    return support_find_by_tg_message_id(tg_message_id)
