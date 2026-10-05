"""Classifier для dispatcher'а: auto или manual для одной ссылки.

Hot-path: один SELECT в локальный кэш — никаких внешних HTTP.

Decision-логи (structured) на каждое решение — для аудита почему ссылка
пошла куда пошла. Reason codes:
  feature_off  — PF_AUTO_DISPATCH_ENABLED=false
  no_ad_id     — extract_ad_id не вернул id
  cache_miss   — ad_id есть, но валидного ключа нет ни в кэше, ни в истории
  cache_hit    — auto, phrase подтянулась из кэша
  history_hit  — auto, кэш пуст/невалиден, phrase взята из истории
                 order_links.search_link этого же объявления

Фраза из любого источника прогоняется через sanitize_search_key: правила
заказчика (2026-10-04) запрещают автозапуск по ключу не-https, а ключи
с фильтром цены и «ключ;ссылка» нормализуются (см. services/search_key.py).
Невалидный ключ из кэша логируется как classifier.invalid_cache_key и
трактуется как промах — ссылка уходит на fallback в историю, а при его
неудаче в ручной запуск.
"""
from __future__ import annotations

import logging

from data import config
from services.avito_phrase_cache import lookup as cache_lookup
from services.avito_url import extract_ad_id
from services.db import connect
from services.search_key import sanitize_search_key

logger = logging.getLogger(__name__)


def resolve_phrase(ad_id: str) -> tuple[str | None, str]:
    """Найти валидный поисковый ключ для ad_id.

    Порядок: кэш (last-used с дашборда) → история order_links.search_link
    этого же объявления (последние отправленные, новые первыми).

    Возвращает (phrase, source):
      ("...", "cache_hit")   — валидный ключ из кэша (возможно, подчищенный)
      ("...", "history_hit") — кэш пуст/невалиден, ключ из истории запусков
      (None, "cache_miss")   — нигде нет валидного ключа
    """
    raw = cache_lookup(ad_id)
    if raw:
        phrase, action = sanitize_search_key(raw)
        if phrase is not None:
            if action != "ok":
                logger.info(
                    "classifier.key_fixed ad=%s action=%s source=cache",
                    ad_id, action,
                )
            return phrase, "cache_hit"
        logger.warning(
            "classifier.invalid_cache_key ad=%s reason=%s raw=%r",
            ad_id, action, raw[:120],
        )

    # Fallback: «ищем другой ключ в бд» — последний валидный search_link
    # этого же объявления из истории отправленных задач.
    with connect() as con:
        rows = con.execute(
            "SELECT search_link FROM order_links "
            "WHERE url LIKE ? AND search_link IS NOT NULL "
            "ORDER BY id DESC LIMIT 20",
            (f"%{ad_id}%",),
        ).fetchall()
    for r in rows:
        hist = r["search_link"] if hasattr(r, "keys") else r[0]
        phrase, _ = sanitize_search_key(hist)
        if phrase is not None:
            return phrase, "history_hit"

    return None, "cache_miss"


def classify(url: str, order: dict, *,
             link_id: int | None = None,
             force: bool = False) \
        -> tuple[str, str | None]:
    """Решает auto/manual для ссылки.

    Возвращает (mode, phrase | None).
    Phrase != None только когда mode='auto'.

    `link_id` — для логов; ничего не меняет в логике.
    `force` — игнорировать PF_AUTO_DISPATCH_ENABLED. Используется только
    админ-handler'ом «Test auto-dispatch». Штатный dispatcher всегда зовёт
    с force=False (дефолт).
    """
    if not force and not config.PF_AUTO_DISPATCH_ENABLED:
        _log(link_id, None, "manual", "feature_off")
        return "manual", None

    ad_id = extract_ad_id(url)
    if not ad_id:
        _log(link_id, None, "manual", "no_ad_id")
        return "manual", None

    phrase, source = resolve_phrase(ad_id)
    if not phrase:
        _log(link_id, ad_id, "manual", source)
        return "manual", None

    _log(link_id, ad_id, "auto", source)
    return "auto", phrase


def _log(link_id, ad_id, decision, reason):
    logger.info(
        "classifier.decision link=%s ad=%s decision=%s reason=%s",
        link_id, ad_id or "none", decision, reason,
    )
