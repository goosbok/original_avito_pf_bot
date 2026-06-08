"""Classifier для dispatcher'а: auto или manual для одной ссылки.

Hot-path: один SELECT в локальный кэш — никаких внешних HTTP.

Decision-логи (structured) на каждое решение — для аудита почему ссылка
пошла куда пошла. Reason codes:
  feature_off — PF_AUTO_DISPATCH_ENABLED=false
  no_ad_id    — extract_ad_id не вернул id
  cache_miss  — ad_id есть, но в кэше пусто
  cache_hit   — auto, phrase подтянулась
"""
from __future__ import annotations

import logging

from data import config
from services.avito_phrase_cache import lookup as cache_lookup
from services.avito_url import extract_ad_id

logger = logging.getLogger(__name__)


def classify(url: str, order: dict, *, link_id: int | None = None) \
        -> tuple[str, str | None]:
    """Решает auto/manual для ссылки.

    Возвращает (mode, phrase | None).
    Phrase != None только когда mode='auto'.

    `link_id` — для логов; ничего не меняет в логике.
    """
    if not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None

    ad_id = extract_ad_id(url)
    if not ad_id:
        _log(link_id, None, "manual", "no_ad_id")
        return "manual", None

    phrase = cache_lookup(ad_id)
    if not phrase:
        _log(link_id, ad_id, "manual", "cache_miss")
        return "manual", None

    _log(link_id, ad_id, "auto", "cache_hit")
    return "auto", phrase


def _log(link_id, ad_id, decision, reason):
    logger.info(
        "classifier.decision link=%s ad=%s decision=%s reason=%s",
        link_id, ad_id or "none", decision, reason,
    )
