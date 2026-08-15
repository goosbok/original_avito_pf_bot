"""Тесты обобщённого OTP-сервиса (channel='telegram' и channel='sms').

Регрессии, которые сохраняются после рефакторинга:
- Cooldown по-прежнему опционален и raise'ит OTPCooldown.
- Код хешируется с pepper (JWT_SECRET) — дамп БД не выдаёт plaintext.
"""
import sqlite3
from pathlib import Path

import pytest


# --- Новый channel/destination API ---


def test_issue_sms_otp_stores_with_channel_and_destination(tmp_db: Path):
    from services import otp
    code = otp.issue(channel='sms', destination='+79991234567',
                     purpose='phone_login', ttl_seconds=300, cooldown_seconds=0)
    assert len(code) >= 4
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT channel, destination, purpose FROM otp_codes"
        ).fetchone()
    assert row == ('sms', '+79991234567', 'phone_login')


def test_verify_sms_otp_consumes_record(tmp_db: Path):
    from services import otp
    code = otp.issue(channel='sms', destination='+79991234567',
                     purpose='phone_login', ttl_seconds=300, cooldown_seconds=0)
    assert otp.verify(channel='sms', destination='+79991234567',
                      code=code, purpose='phone_login') is True
    # повторный verify не проходит — consumed
    assert otp.verify(channel='sms', destination='+79991234567',
                      code=code, purpose='phone_login') is False


def test_verify_wrong_code_increments_attempts_and_caps_at_max(tmp_db: Path):
    from services import otp
    otp.issue(channel='sms', destination='+79991234567',
              purpose='phone_login', ttl_seconds=300, cooldown_seconds=0)
    for _ in range(otp.MAX_ATTEMPTS):
        assert otp.verify(channel='sms', destination='+79991234567',
                          code='0000', purpose='phone_login') is False
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT attempts, consumed_at FROM otp_codes").fetchone()
    assert row[0] >= otp.MAX_ATTEMPTS
    assert row[1] is not None  # сжат


def test_telegram_otp_still_works_after_generalization(tmp_db: Path):
    """Регрессия: старый код, дёргающий issue с channel='telegram', должен работать."""
    from services import otp
    code = otp.issue(channel='telegram', destination='12345',
                     purpose='link', ttl_seconds=300, cooldown_seconds=0)
    assert otp.verify(channel='telegram', destination='12345',
                      code=code, purpose='link') is True


# --- Сохранённое поведение: cooldown + pepper-хеширование ---


def test_cooldown_still_raised_when_requesting_too_fast(tmp_db: Path):
    """Cooldown сохранён — это защита от abuse при платных SMS."""
    from services import otp
    from services.exceptions import OTPCooldown
    otp.issue(channel='sms', destination='+79991234567',
              purpose='phone_login', ttl_seconds=300, cooldown_seconds=60)
    with pytest.raises(OTPCooldown):
        otp.issue(channel='sms', destination='+79991234567',
                  purpose='phone_login', ttl_seconds=300, cooldown_seconds=60)


def test_code_stored_as_pepper_hash_not_plaintext(tmp_db: Path):
    """В БД хранится sha256(code+pepper), а не сам код."""
    from services import otp
    code = otp.issue(channel='sms', destination='+79991234567',
                     purpose='phone_login', ttl_seconds=300, cooldown_seconds=0)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT code_hash FROM otp_codes").fetchone()
    assert row[0] != code
    assert len(row[0]) == 64  # sha256 hex


def test_get_user_id_to_link_peeks_without_consuming(tmp_db: Path):
    """get_user_id_to_link читает user_id_to_link без consume — чтобы caller мог
    проверить владельца до фактического consume."""
    from services import otp
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance) VALUES (?, 0)", (77,))
        con.commit()
    code = otp.issue(channel='telegram', destination='999',
                     purpose='link', ttl_seconds=300, cooldown_seconds=0,
                     user_id_to_link=77)
    assert otp.get_user_id_to_link(channel='telegram', destination='999',
                                   code=code, purpose='link') == 77
    # повторный peek работает — не consume
    assert otp.get_user_id_to_link(channel='telegram', destination='999',
                                   code=code, purpose='link') == 77
    # после verify — consumed
    assert otp.verify(channel='telegram', destination='999',
                      code=code, purpose='link') is True
    assert otp.get_user_id_to_link(channel='telegram', destination='999',
                                   code=code, purpose='link') is None


def test_get_user_id_to_link_returns_none_for_wrong_code(tmp_db: Path):
    from services import otp
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance) VALUES (?, 0)", (77,))
        con.commit()
    otp.issue(channel='telegram', destination='999',
              purpose='link', ttl_seconds=300, cooldown_seconds=0,
              user_id_to_link=77)
    assert otp.get_user_id_to_link(channel='telegram', destination='999',
                                   code='000000', purpose='link') is None
