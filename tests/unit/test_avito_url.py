import pytest
from services.avito_url import extract_ad_id


@pytest.mark.parametrize("url, expected", [
    # стандартные
    ("https://www.avito.ru/moskva/kvartiry/1-k._kvartira_44_m_812_et_1234567890",
     "1234567890"),
    ("https://avito.ru/moskva/kvartiry/3-k._kvartira_749m_216et._7961085920",
     "7961085920"),
    ("https://m.avito.ru/sankt-peterburg/avtomobili/lada_2107_2003_2222333344",
     "2222333344"),
    # с query/fragment
    ("https://www.avito.ru/moskva/kvartiry/1k_1234567890?utm_source=x",
     "1234567890"),
    ("https://www.avito.ru/moskva/kvartiry/1k_1234567890#tab",
     "1234567890"),
    # http
    ("http://avito.ru/moskva/kvartiry/abc_9999999999", "9999999999"),
    # отсутствие id
    ("https://avito.ru/moskva/kvartiry", None),
    ("https://avito.ru/", None),
    ("https://avito.ru/profile/12345", None),  # короткий — мы хотим >=8 цифр
    ("not a url", None),
    ("", None),
    (None, None),
])
def test_extract_ad_id(url, expected):
    assert extract_ad_id(url) == expected
