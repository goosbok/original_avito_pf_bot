"""sanitize_search_key — правила отбора поисковых ключей для автозапуска.

Заказчик (2026-10-04): не берём в базу автозапуска ключи
  1) не начинающиеся с https — форс-мажорный прямой запуск;
  2) с фильтром цены (&priceMin/&priceMax) — вырезаем параметры;
  3) с «;» — «ключ;ссылка на объяву», разбираем и берём поисковую часть.
"""
from services.search_key import sanitize_search_key


# === ok ===

def test_plain_search_url_passes_unchanged():
    url = "https://www.avito.ru/sankt-peterburg?q=Аренда+экскаватора"
    clean, action = sanitize_search_key(url)
    assert clean == url
    assert action == "ok"


def test_category_url_without_query_passes():
    """https-ссылка на категорию без q= — валидна (правило только про https)."""
    url = "https://www.avito.ru/chelyabinsk/predlozheniya_uslug"
    clean, action = sanitize_search_key(url)
    assert clean == url
    assert action == "ok"


def test_surrounding_whitespace_trimmed():
    clean, action = sanitize_search_key("  https://avito.ru/x?q=тест  ")
    assert clean == "https://avito.ru/x?q=тест"
    assert action == "ok"


# === price filter ===

def test_price_params_stripped_from_end():
    clean, action = sanitize_search_key(
        "https://www.avito.ru/sankt-peterburg/arenda_spetstehniki"
        "?q=Аренда+экскаватора-погрузчика&priceMax=3300&priceMin=2700"
    )
    assert clean == (
        "https://www.avito.ru/sankt-peterburg/arenda_spetstehniki"
        "?q=Аренда+экскаватора-погрузчика"
    )
    assert action == "price_stripped"


def test_price_params_stripped_from_middle():
    """Price-параметры не обязаны стоять в конце — вырезаем из любого места."""
    clean, action = sanitize_search_key(
        "https://www.avito.ru/moskva?priceMin=100&q=шкаф&priceMax=200&s=104"
    )
    assert clean is not None
    assert "priceMin" not in clean
    assert "priceMax" not in clean
    assert "q=" in clean and "s=104" in clean
    assert action == "price_stripped"


def test_price_zero_values_stripped_too():
    """priceMin=0&priceMax=0 (полная вилка) — тоже фильтр, вырезаем."""
    clean, action = sanitize_search_key(
        "https://www.avito.ru/kazan?q=Удаление+царапин&priceMax=0&priceMin=0"
    )
    assert clean == "https://www.avito.ru/kazan?q=Удаление+царапин"
    assert action == "price_stripped"


def test_price_stripped_leaves_empty_query():
    clean, action = sanitize_search_key(
        "https://www.avito.ru/chelyabinsk/vakansii?priceMax=1003"
    )
    assert clean == "https://www.avito.ru/chelyabinsk/vakansii"
    assert action == "price_stripped"


# === semicolon ===

def test_semicolon_takes_search_part():
    """«ключ;ссылка_на_объяву» → берём поисковую https-часть."""
    clean, action = sanitize_search_key(
        "https://www.avito.ru/chelyabinsk/predlozheniya_uslug"
        "?q=Аренда+экскаватора"
        ";https://www.avito.ru/chelyabinsk/arenda_tyazhelogo_ekskavatora"
        "_s_kovshom_2.5_m_4422302355"
    )
    assert clean == (
        "https://www.avito.ru/chelyabinsk/predlozheniya_uslug"
        "?q=Аренда+экскаватора"
    )
    assert action == "semicolon_split"


def test_semicolon_and_price_both_fixed():
    clean, action = sanitize_search_key(
        "https://www.avito.ru/sankt-peterburg/igry?q=God+of+War"
        "&priceMax=2189&priceMin=1791"
        ";https://www.avito.ru/sankt-peterburg/igra_123"
    )
    assert clean == "https://www.avito.ru/sankt-peterburg/igry?q=God+of+War"
    assert action == "semicolon_price_fixed"


def test_semicolon_without_https_part_rejected():
    clean, action = sanitize_search_key("1;купить квартиру")
    assert clean is None
    assert action == "semicolon_no_https_part"


# === reject ===

def test_force_majeure_one_rejected():
    clean, action = sanitize_search_key("1")
    assert clean is None
    assert action == "not_https"


def test_na_rejected():
    clean, action = sanitize_search_key("#N/A")
    assert clean is None
    assert action == "not_https"


def test_http_without_s_rejected():
    clean, action = sanitize_search_key("http://avito.ru/perm/foo?q=бар")
    assert clean is None
    assert action == "not_https"


def test_none_and_empty_rejected():
    assert sanitize_search_key(None) == (None, "empty")
    assert sanitize_search_key("") == (None, "empty")
    assert sanitize_search_key("   ") == (None, "empty")


def test_non_avito_https_passes():
    """https не-avito — правила заказчика не запрещают, пропускаем."""
    clean, action = sanitize_search_key("https://example.com/search?q=x")
    assert clean == "https://example.com/search?q=x"
    assert action == "ok"
