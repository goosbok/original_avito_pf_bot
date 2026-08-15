"""Нормализация телефонов в E.164-ish формат.

Правила:
- Strip whitespace, parentheses, dashes.
- If starts with '+' and the rest is all digits → keep as-is.
- If 11 digits starting with '8' → replace leading '8' with '+7' (RU).
- If 11 digits starting with '7' → prepend '+'.
- If 10–15 digits → prepend '+' (международный без плюса).
- Otherwise: None (не похоже на телефон).
"""
from __future__ import annotations

import re

_PHONE_STRIP_RE = re.compile(r"[\s()\-]+")


def normalize_phone(raw: str) -> str | None:
    """+79..., 79..., 89..., (или любой 10-15 значный) → +<digits>; иначе None."""
    if not raw:
        return None
    s = _PHONE_STRIP_RE.sub("", raw)
    if not s:
        return None
    if s.startswith("+"):
        rest = s[1:]
        if rest.isdigit() and 10 <= len(rest) <= 15:
            return "+" + rest
        return None
    if not s.isdigit():
        return None
    if len(s) == 11 and s.startswith("8"):
        return "+7" + s[1:]
    if len(s) == 11 and s.startswith("7"):
        return "+" + s
    if 10 <= len(s) <= 15:
        return "+" + s
    return None
