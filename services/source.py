"""Source-tracking — кто создал заявку/refill.

Используется на refills (Phase 2) и на orders (Phase 3).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class Source(str, Enum):
    TELEGRAM = "telegram"
    WEB = "web"
    API = "api"


def normalize(source_type: str | Source, source_app_id: Optional[int] = None) -> tuple[str, Optional[int]]:
    """Нормализует и валидирует пару (type, app_id)."""
    s = Source(source_type) if not isinstance(source_type, Source) else source_type
    if s is Source.API and source_app_id is None:
        raise ValueError("source_type=api requires source_app_id")
    if s is not Source.API and source_app_id is not None:
        raise ValueError(f"source_app_id must be None for source_type={s.value}")
    return s.value, source_app_id
