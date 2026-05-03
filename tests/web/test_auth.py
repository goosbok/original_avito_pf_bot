import hashlib
import hmac
import time
from typing import Any

import jwt as pyjwt
import pytest

from web import auth as auth_module


def _make_widget_data(bot_token: str, user_id: int = 42, **extra: Any) -> dict:
    """Сгенерировать корректно подписанные данные виджета."""
    data: dict[str, Any] = {
        "id": user_id,
        "first_name": "Test",
        "auth_date": int(time.time()),
        **extra,
    }
    data_check_string = "\n".join(
        f"{k}={data[k]}" for k in sorted(data.keys())
    )
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return {**data, "hash": h}


def test_verify_telegram_auth_accepts_valid_signature() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    user_id = auth_module.verify_telegram_auth(data, bot_token=token)
    assert user_id == 42


def test_verify_telegram_auth_rejects_bad_hash() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    data["hash"] = "0" * 64
    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_verify_telegram_auth_rejects_old_auth_date() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    data["auth_date"] = int(time.time()) - 99_999_999
    fresh = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={fresh[k]}" for k in sorted(fresh.keys()))
    secret_key = hashlib.sha256(token.encode()).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_verify_telegram_auth_rejects_missing_hash() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    del data["hash"]
    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_create_and_decode_jwt_roundtrip() -> None:
    secret = "x" * 32
    token = auth_module.create_jwt(user_id=42, secret=secret)
    user_id = auth_module.decode_jwt(token, secret=secret)
    assert user_id == 42


def test_decode_jwt_rejects_bad_signature() -> None:
    secret = "x" * 32
    token = auth_module.create_jwt(user_id=42, secret=secret)
    with pytest.raises(auth_module.AuthError):
        auth_module.decode_jwt(token, secret="y" * 32)


def test_decode_jwt_rejects_expired_token() -> None:
    secret = "x" * 32
    expired = pyjwt.encode(
        {"sub": "42", "exp": int(time.time()) - 10},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(auth_module.AuthError):
        auth_module.decode_jwt(expired, secret=secret)
