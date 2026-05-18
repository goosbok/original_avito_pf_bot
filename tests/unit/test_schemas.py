"""Unit tests for Pydantic schema validation (no DB required)."""
import pytest
from pydantic import ValidationError

from web.schemas import (
    EmailRegisterRequest,
    LinkEmailRequestStep1,
    ResetPasswordRequest,
)


def test_email_register_passwords_match():
    obj = EmailRegisterRequest(
        email="a@b.com",
        password="password123",
        password_confirm="password123",
    )
    assert obj.password == "password123"


def test_email_register_passwords_mismatch_raises():
    with pytest.raises(ValidationError, match="passwords do not match"):
        EmailRegisterRequest(
            email="a@b.com",
            password="password123",
            password_confirm="different",
        )


def test_email_register_missing_confirm_raises():
    with pytest.raises(ValidationError):
        EmailRegisterRequest(email="a@b.com", password="password123")


def test_link_email_step1_passwords_match():
    obj = LinkEmailRequestStep1(
        email="a@b.com",
        password="password123",
        password_confirm="password123",
    )
    assert obj.password == "password123"


def test_link_email_step1_mismatch_raises():
    with pytest.raises(ValidationError, match="passwords do not match"):
        LinkEmailRequestStep1(
            email="a@b.com",
            password="password123",
            password_confirm="different",
        )


def test_reset_password_passwords_match():
    obj = ResetPasswordRequest(
        token="tok",
        new_password="password123",
        new_password_confirm="password123",
    )
    assert obj.new_password == "password123"


def test_reset_password_mismatch_raises():
    with pytest.raises(ValidationError, match="passwords do not match"):
        ResetPasswordRequest(
            token="tok",
            new_password="password123",
            new_password_confirm="different",
        )
