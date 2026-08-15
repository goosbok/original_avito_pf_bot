"""extract_avito_links должен корректно разбирать 4 кейса ввода URL.

Регрессия: ранее URL-ы, разделённые переносом строки, склеивались в один
из-за нормализации `re.sub(r'(?<=\\S)[\\r\\n]+(?=\\S)', '', text)` —
в order_links писалась 1 строка вместо N.

tmp_db нужен, потому что цепочка импорта handlers.pf_order дёргает
keyboards/users_menu.py, который на load-time ходит в БД через get_price.
"""
import pytest


def _fn():
    from handlers.pf_order import extract_avito_links
    return extract_avito_links


def test_urls_one_per_line_are_separated(tmp_db):
    text = (
        "https://avito.ru/moskva/vakansii/aaa_111\n"
        "https://avito.ru/spb/vakansii/bbb_222\n"
        "https://avito.ru/kazan/vakansii/ccc_333"
    )
    assert _fn()(text) == [
        "https://avito.ru/moskva/vakansii/aaa_111",
        "https://avito.ru/spb/vakansii/bbb_222",
        "https://avito.ru/kazan/vakansii/ccc_333",
    ]


def test_urls_separated_by_spaces(tmp_db):
    text = (
        "https://avito.ru/moskva/vakansii/aaa_111 "
        "https://avito.ru/spb/vakansii/bbb_222"
    )
    assert _fn()(text) == [
        "https://avito.ru/moskva/vakansii/aaa_111",
        "https://avito.ru/spb/vakansii/bbb_222",
    ]


def test_urls_glued_without_separator_are_split(tmp_db):
    text = (
        "https://avito.ru/moskva/vakansii/aaa_111"
        "https://avito.ru/spb/vakansii/bbb_222"
    )
    assert _fn()(text) == [
        "https://avito.ru/moskva/vakansii/aaa_111",
        "https://avito.ru/spb/vakansii/bbb_222",
    ]


def test_single_url_broken_by_newline_is_rejoined(tmp_db):
    text = (
        "https://avito.ru/moskva/kvartiry/\n"
        "2_komnatnaya_8090325313"
    )
    assert _fn()(text) == [
        "https://avito.ru/moskva/kvartiry/2_komnatnaya_8090325313",
    ]


def test_duplicates_are_deduplicated(tmp_db):
    text = (
        "https://avito.ru/moskva/aaa_111\n"
        "https://avito.ru/moskva/aaa_111\n"
        "https://avito.ru/spb/bbb_222"
    )
    assert _fn()(text) == [
        "https://avito.ru/moskva/aaa_111",
        "https://avito.ru/spb/bbb_222",
    ]


def test_empty_input_returns_empty_list(tmp_db):
    assert _fn()("") == []


def test_non_avito_urls_are_ignored(tmp_db):
    text = "https://example.com/foo https://avito.ru/moskva/aaa_111"
    assert _fn()(text) == ["https://avito.ru/moskva/aaa_111"]


def test_mobile_avito_links_are_accepted(tmp_db):
    text = (
        "https://m.avito.ru/moskva/vakansii/aaa_111\n"
        "https://avito.ru/spb/vakansii/bbb_222"
    )
    assert _fn()(text) == [
        "https://m.avito.ru/moskva/vakansii/aaa_111",
        "https://avito.ru/spb/vakansii/bbb_222",
    ]
