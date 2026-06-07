"""Stub: классификатор всегда возвращает 'manual' (Спек §5.1)."""


def test_classify_returns_manual():
    from services.order_links_classifier import classify
    assert classify("https://avito.ru/anything", {"position_name": "3/100"}) == "manual"


def test_classify_does_not_raise_on_missing_fields():
    """Stub не должен зависеть от состава order — это будущая бизнес-логика."""
    from services.order_links_classifier import classify
    assert classify("url", {}) == "manual"
