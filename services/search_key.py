"""Нормализация поискового ключа (search_link) для автозапуска ПФ.

Правила заказчика (Игорь, 2026-10-04): в базу для автозапуска НЕ берём ключи:
  1) начинающиеся не с https — это форс-мажорный прямой запуск («1», «#N/A»),
     не поисковый запрос;
  2) с фильтром цены (priceMin/priceMax в query) — ценовая вилка ломает
     накрутку. Решение владельца: не отбрасывать ключ, а вырезать
     price-параметры (их ~40% кэша прода, отбраковка потеряла бы их все);
  3) с «;» — при запуске вставили «ключ;ссылка_на_объяву» одной строкой.
     Решение: разбираем и берём поисковую https-часть.

Единая функция используется на всех входах: refresh кэша с дашборда,
classifier в hot-path'е dispatch'а и cleanup-скрипт по историческим данным.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Query-параметры ценового фильтра Авито.
_PRICE_PARAMS = frozenset({"price", "priceMin", "priceMax"})


def sanitize_search_key(raw: str | None) -> tuple[str | None, str]:
    """Привести сырой ключ к валидному поисковому URL или отклонить.

    Возвращает (ключ, action):
      ключ != None — можно использовать для автозапуска;
      ключ == None — отклонён, action объясняет почему.

    action:
      ok                      — ключ валиден без изменений
      price_stripped          — вырезали price-параметры
      semicolon_split         — взяли https-часть из «ключ;ссылка»
      semicolon_price_fixed   — обе правки сразу
      empty                   — пусто/None
      not_https               — не начинается с https (форс-мажор «1», «#N/A»)
      semicolon_no_https_part — «;» есть, но ни одна часть не https
    """
    if not raw or not raw.strip():
        return None, "empty"

    s = raw.strip()
    fixed_semicolon = False

    if ";" in s:
        parts = [p.strip() for p in s.split(";") if p.strip()]
        https_parts = [p for p in parts if p.startswith("https")]
        if not https_parts:
            return None, "semicolon_no_https_part"
        # Если https-частей несколько — предпочитаем avito.ru (вторая часть
        # обычно ссылка на само объявление, она тоже https, но нам нужен
        # поисковый ключ; avito-части в этом кейсе обе, берём первую).
        avito_parts = [p for p in https_parts if "avito.ru" in p]
        s = (avito_parts or https_parts)[0]
        fixed_semicolon = True

    if not s.startswith("https"):
        return None, "not_https"

    # Вырезаем price-параметры. Строковый разбор query, а не
    # parse_qsl/urlencode: пересборка через urlencode перекодирует кириллицу
    # в %XX, а в БД и у исполнителя ключи лежат в исходном виде — после
    # чистки ключ должен отличаться от исходного только удалёнными
    # price-параметрами.
    fixed_price = False
    if "?" in s:
        base, _, query = s.partition("?")
        parts = query.split("&")
        kept = [p for p in parts
                if p.split("=", 1)[0] not in _PRICE_PARAMS]
        if len(kept) != len(parts):
            fixed_price = True
            s = base + ("?" + "&".join(kept) if kept else "")

    if fixed_semicolon and fixed_price:
        return s, "semicolon_price_fixed"
    if fixed_semicolon:
        return s, "semicolon_split"
    if fixed_price:
        return s, "price_stripped"
    return s, "ok"
