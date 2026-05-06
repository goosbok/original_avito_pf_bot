from pathlib import Path

import pytest

from services import auth_email
from services.exceptions import InvalidCredentials, EmailAlreadyRegistered


def test_register_creates_user(tmp_db: Path):
    uid = auth_email.register("Alice@Example.com", "password123", first_name="Alice")
    assert uid > 0


def test_register_normalizes_email(tmp_db: Path):
    uid1 = auth_email.register("Alice@Example.com", "password123")
    with pytest.raises(EmailAlreadyRegistered):
        auth_email.register("alice@example.com", "password123")


def test_register_invalid_email(tmp_db: Path):
    with pytest.raises(InvalidCredentials):
        auth_email.register("not-an-email", "password123")


def test_register_short_password(tmp_db: Path):
    with pytest.raises(ValueError):
        auth_email.register("a@b.com", "short")


def test_login_success(tmp_db: Path):
    uid = auth_email.register("user@example.com", "password123")
    assert auth_email.login("user@example.com", "password123") == uid


def test_login_case_insensitive_email(tmp_db: Path):
    uid = auth_email.register("user@example.com", "password123")
    assert auth_email.login("USER@example.com", "password123") == uid


def test_login_wrong_password(tmp_db: Path):
    auth_email.register("user@example.com", "password123")
    with pytest.raises(InvalidCredentials):
        auth_email.login("user@example.com", "wrong-password")


def test_login_unregistered(tmp_db: Path):
    with pytest.raises(InvalidCredentials):
        auth_email.login("nope@example.com", "password123")
