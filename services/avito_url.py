"""Извлечение Avito ad_id из URL объявления.

ad_id — последняя группа цифр (>=8) в пути URL. Этот формат единый для
desktop/mobile (avito.ru, m.avito.ru) и не меняется query/fragment'ом.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_AD_ID_RE = re.compile(r"_(\d{8,})(?:/|$)")


def extract_ad_id(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    if not path:
        return None
    m = _AD_ID_RE.search(path)
    return m.group(1) if m else None
