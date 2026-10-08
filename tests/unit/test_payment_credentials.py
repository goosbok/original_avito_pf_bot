"""Креды Юкассы из настроек бота: fallback на env + приоритет БД."""
from services import payment_credentials as pc


def test_env_fallback_when_no_db_rows(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.SHOP_ID", 111111, raising=False)
    monkeypatch.setattr("data.config.SECRET_KEY", "test_envkey123", raising=False)
    assert pc.shop_id() == "111111"
    assert pc.secret_key() == "test_envkey123"
    assert pc.source() == "env"
    assert pc.is_configured() is True


def test_db_rows_override_env(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.SHOP_ID", 111111, raising=False)
    monkeypatch.setattr("data.config.SECRET_KEY", "test_envkey123", raising=False)
    pc.set_shop_id("1328070")
    pc.set_secret_key("live_abcdef1234567890")
    assert pc.shop_id() == "1328070"
    assert pc.secret_key() == "live_abcdef1234567890"
    assert pc.source() == "db"


def test_empty_db_value_falls_back_to_env(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.SHOP_ID", 111111, raising=False)
    pc.set_shop_id("1328070")
    pc.set_shop_id("")  # сброс через "-" в админке
    assert pc.shop_id() == "111111"


def test_not_configured_when_empty(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.SHOP_ID", 0, raising=False)
    monkeypatch.setattr("data.config.SECRET_KEY", "", raising=False)
    assert pc.is_configured() is False
    assert pc.source() == "none"
    assert pc.masked_secret() == "—"


def test_masked_secret(tmp_db):
    pc.set_secret_key("live_KGlmTRPu20BZFuUll9svR5V4m6dNNawJ4TwDER_DK8w")
    masked = pc.masked_secret()
    assert masked == "live_KGlm…DK8w"
    assert "TRPu20" not in masked  # середина не светится


def test_masked_short_secret(tmp_db):
    pc.set_secret_key("test_short")
    assert pc.masked_secret() == "***"
