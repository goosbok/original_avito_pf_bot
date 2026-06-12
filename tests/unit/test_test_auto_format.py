"""Чистые форматтеры preview/result сообщений для admin Test auto."""
from services.order_links_dispatcher import LinkPreview, DispatchResult


def test_format_preview_two_links_mixed():
    """2 ссылки: одна auto, одна manual."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/bmw_8048793719",
            ad_id="8048793719", decision="auto", reason="cache_hit",
            phrase="купить квартиру москва",
            deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/lada_2222333344",
            ad_id="2222333344", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99431, previews=previews)

    assert "99431" in text
    assert "Будет обработано: 2 ссылки" in text
    assert "AUTO" in text
    assert "MANUAL" in text
    assert "8048793719" in text
    assert "2222333344" in text
    assert "купить квартиру москва" in text
    assert "2026-06-12" in text
    assert "Будет реально отправлено 1 ссылка" in text


def test_format_preview_zero_auto():
    """Все ссылки manual → footer указывает что отправлять нечего."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99432, previews=previews)
    assert "Все ссылки → MANUAL" in text
    assert "отправлять нечего" in text


def test_format_preview_no_ad_id_reason():
    """no_ad_id reason человекочитаемо."""
    from utils.test_auto_format import format_preview

    previews = [
        LinkPreview(
            link_id=11, url="https://example.com/foo",
            ad_id=None, decision="manual", reason="no_ad_id",
            phrase=None, deadline_at=None,
        ),
    ]
    text = format_preview(order_id=99433, previews=previews)
    assert "ad_id не выделился" in text or "no_ad_id" in text


def test_format_result_all_success():
    """Все отправки успешны."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1234567890",
            ad_id="1234567890", decision="auto", reason="cache_hit",
            phrase="купить", deadline_at="2026-06-12T00:00:00+00:00",
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="357901", error=None),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)

    assert "99431" in text
    assert "Отправлено: 1 / 1" in text
    assert "357901" in text
    assert "2026-06-12" in text
    assert "✅" in text


def test_format_result_with_failure():
    """Один success, один failure."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="auto", reason="cache_hit",
            phrase="a", deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/x_2222222222",
            ad_id="2222222222", decision="auto", reason="cache_hit",
            phrase="b", deadline_at="2026-06-12T00:00:00+00:00",
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="100", error=None),
        DispatchResult(link_id=12, success=False, external_id=None,
                       error="API отказал: 400 invalid"),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)

    assert "Отправлено: 1 / 2" in text
    assert "100" in text
    assert "API отказал" in text
    assert "❌" in text


def test_format_result_includes_manual_links():
    """MANUAL ссылки из preview показываются в результате как 'не отправлялось'."""
    from utils.test_auto_format import format_result

    previews = [
        LinkPreview(
            link_id=11, url="https://avito.ru/x_1111111111",
            ad_id="1111111111", decision="auto", reason="cache_hit",
            phrase="a", deadline_at="2026-06-12T00:00:00+00:00",
        ),
        LinkPreview(
            link_id=12, url="https://avito.ru/x_2222222222",
            ad_id="2222222222", decision="manual", reason="cache_miss",
            phrase=None, deadline_at=None,
        ),
    ]
    results = [
        DispatchResult(link_id=11, success=True,
                       external_id="100", error=None),
    ]
    text = format_result(order_id=99431, previews=previews, results=results)
    assert "MANUAL" in text or "не отправлялось" in text


def test_format_empty_cache_message():
    """Friendly fallback message при пустом кэше."""
    from utils.test_auto_format import format_empty_cache_message

    text = format_empty_cache_message(order_id=99431, link_count=2)
    assert "99431" in text
    assert "2 ссыл" in text
    assert "backfill" in text
    assert "scripts.backfill_avito_phrase_cache" in text
