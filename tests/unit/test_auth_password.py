import pytest

from services.auth_password import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)


def test_verify_rejects_wrong_password():
    h = hash_password("password123")
    assert not verify_password("wrong-pass", h)


def test_hash_rejects_short_password():
    with pytest.raises(ValueError):
        hash_password("short")


def test_verify_rejects_empty_inputs():
    assert not verify_password("", "")
    assert not verify_password("abc", "")
    assert not verify_password("", "abc")


def test_hash_is_unique_per_call():
    """bcrypt использует salt — два хеша одного пароля разные."""
    a = hash_password("samepass1")
    b = hash_password("samepass1")
    assert a != b
    assert verify_password("samepass1", a)
    assert verify_password("samepass1", b)
