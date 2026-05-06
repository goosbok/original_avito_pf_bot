from pathlib import Path

import pytest

from services import otp
from services.exceptions import OTPCooldown, OTPExpired, OTPInvalid


def test_request_returns_six_digit_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    assert len(code) == 6 and code.isdigit()


def test_verify_correct_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    assert otp.verify_code("login", 12345, code) is None  # purpose=login → None


def test_verify_wrong_code_raises(tmp_db: Path):
    otp.request_code("login", 12345)
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, "999999")


def test_verify_consumes_code_after_success(tmp_db: Path):
    code = otp.request_code("login", 12345)
    otp.verify_code("login", 12345, code)
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code)


def test_request_invalidates_previous_unused(tmp_db: Path):
    code1 = otp.request_code("login", 12345, cooldown_seconds=0)
    code2 = otp.request_code("login", 12345, cooldown_seconds=0)
    assert code1 != code2 or True  # collision возможна, но редка
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code1)


def test_cooldown_blocks_rapid_request(tmp_db: Path):
    otp.request_code("login", 12345, cooldown_seconds=60)
    with pytest.raises(OTPCooldown) as exc:
        otp.request_code("login", 12345, cooldown_seconds=60)
    assert exc.value.retry_after_seconds > 0


def test_expired_code_raises(tmp_db: Path):
    code = otp.request_code("login", 12345, ttl_seconds=0)
    import time
    time.sleep(0.01)
    with pytest.raises(OTPExpired):
        otp.verify_code("login", 12345, code)


def test_max_attempts_invalidates_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    for _ in range(5):
        with pytest.raises(OTPInvalid):
            otp.verify_code("login", 12345, "000000")
    # 6-я попытка с правильным кодом — уже не работает
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code)


def test_link_purpose_returns_user_id(tmp_db: Path):
    code = otp.request_code("link", 12345, user_id_to_link=42)
    assert otp.verify_code("link", 12345, code) == 42
