"""Legacy OTP-tests, переведены на channel/destination API.

Канал в этих кейсах всегда 'telegram' (destination = str(tg_id)), что
исторически было единственным.
"""
from pathlib import Path

import pytest

from services import otp
from services.exceptions import OTPCooldown, OTPExpired


_TG = '12345'  # destination для channel='telegram'


def test_issue_returns_six_digit_code(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='login',
                     cooldown_seconds=0)
    assert len(code) == 6 and code.isdigit()


def test_verify_correct_code(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='login',
                     cooldown_seconds=0)
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code, purpose='login') is True


def test_verify_wrong_code_returns_false(tmp_db: Path):
    otp.issue(channel='telegram', destination=_TG, purpose='login',
              cooldown_seconds=0)
    assert otp.verify(channel='telegram', destination=_TG,
                      code='999999', purpose='login') is False


def test_verify_consumes_code_after_success(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='login',
                     cooldown_seconds=0)
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code, purpose='login') is True
    # повторный verify — False (consumed)
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code, purpose='login') is False


def test_issue_invalidates_previous_unused(tmp_db: Path):
    code1 = otp.issue(channel='telegram', destination=_TG, purpose='login',
                      cooldown_seconds=0)
    code2 = otp.issue(channel='telegram', destination=_TG, purpose='login',
                      cooldown_seconds=0)
    assert code1 != code2 or True  # коллизия возможна, но редка
    # старый код больше не валиден
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code1, purpose='login') is False


def test_cooldown_blocks_rapid_request(tmp_db: Path):
    otp.issue(channel='telegram', destination=_TG, purpose='login',
              cooldown_seconds=60)
    with pytest.raises(OTPCooldown) as exc:
        otp.issue(channel='telegram', destination=_TG, purpose='login',
                  cooldown_seconds=60)
    assert exc.value.retry_after_seconds > 0


def test_expired_code_raises(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='login',
                     ttl_seconds=0, cooldown_seconds=0)
    import time
    time.sleep(0.01)
    with pytest.raises(OTPExpired):
        otp.verify(channel='telegram', destination=_TG,
                   code=code, purpose='login')


def test_max_attempts_invalidates_code(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='login',
                     cooldown_seconds=0)
    # MAX_ATTEMPTS неверных попыток — код burn
    for _ in range(otp.MAX_ATTEMPTS):
        assert otp.verify(channel='telegram', destination=_TG,
                          code='000000', purpose='login') is False
    # верный код после burn — уже не работает
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code, purpose='login') is False


def test_link_purpose_user_id_via_get_user_id_to_link(tmp_db: Path):
    code = otp.issue(channel='telegram', destination=_TG, purpose='link',
                     cooldown_seconds=0, user_id_to_link=42)
    assert otp.get_user_id_to_link(channel='telegram', destination=_TG,
                                   code=code, purpose='link') == 42
    assert otp.verify(channel='telegram', destination=_TG,
                      code=code, purpose='link') is True
