"""Unit tests for services/auth_reset.py — OTP-based reset."""
import pytest

from services import auth_email, auth_reset
from services.exceptions import InvalidCredentials, OTPCooldown, OTPExpired, OTPInvalid


@pytest.fixture
def fake_send_email(monkeypatch):
    calls: list[dict] = []

    def _capture(to: str, subject: str, body: str, *, html: bool = False) -> None:
        calls.append({"to": to, "subject": subject, "body": body})

    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", _capture)
    return calls


def _register(email: str, password: str = "password123") -> int:
    return auth_email.register(email, password)


# ── forgot_password ────────────────────────────────────────────────────────

def test_forgot_password_sends_code(tmp_db, fake_send_email):
    _register("reset@example.com")
    auth_reset.forgot_password("reset@example.com")
    assert len(fake_send_email) == 1
    msg = fake_send_email[0]
    assert msg["to"] == "reset@example.com"
    import re
    assert re.search(r"\b\d{6}\b", msg["body"]), "expected 6-digit code in body"
    assert "http" not in msg["body"], "body must not contain a link"


def test_forgot_password_unknown_email_silent(tmp_db, fake_send_email):
    auth_reset.forgot_password("nobody@example.com")
    assert fake_send_email == []


def test_forgot_password_invalid_email_silent(tmp_db, fake_send_email):
    auth_reset.forgot_password("not-an-email")
    assert fake_send_email == []


def test_forgot_password_cooldown_raises(tmp_db, fake_send_email):
    _register("cd@example.com")
    auth_reset.forgot_password("cd@example.com")
    with pytest.raises(OTPCooldown):
        auth_reset.forgot_password("cd@example.com")


# ── reset_password_by_otp ──────────────────────────────────────────────────

def _issue_code(email: str) -> str:
    """Issue a reset OTP for an already-registered email, return plaintext code."""
    from services import otp
    from services.auth_email import normalize_email
    email_norm = normalize_email(email)
    return otp.issue(
        channel="email",
        destination=email_norm,
        purpose="password_reset",
        ttl_seconds=600,
        cooldown_seconds=0,
    )


def test_reset_by_otp_success(tmp_db):
    uid = _register("pw@example.com")
    code = _issue_code("pw@example.com")
    auth_reset.reset_password_by_otp("pw@example.com", code, "newpassword123")
    assert auth_email.login("pw@example.com", "newpassword123") == uid
    with pytest.raises(InvalidCredentials):
        auth_email.login("pw@example.com", "password123")


def test_reset_by_otp_wrong_code(tmp_db):
    _register("wrong@example.com")
    _issue_code("wrong@example.com")
    with pytest.raises(OTPInvalid):
        auth_reset.reset_password_by_otp("wrong@example.com", "000000", "newpassword123")


def test_reset_by_otp_expired(tmp_db):
    import sqlite3
    _register("exp@example.com")
    code = _issue_code("exp@example.com")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE otp_codes SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE destination = 'exp@example.com' AND purpose = 'password_reset'"
        )
        con.commit()
    with pytest.raises(OTPExpired):
        auth_reset.reset_password_by_otp("exp@example.com", code, "newpassword123")


def test_reset_by_otp_short_password(tmp_db):
    _register("short@example.com")
    code = _issue_code("short@example.com")
    with pytest.raises(ValueError):
        auth_reset.reset_password_by_otp("short@example.com", code, "short")


def test_reset_by_otp_invalid_email(tmp_db):
    with pytest.raises(OTPInvalid):
        auth_reset.reset_password_by_otp("not-an-email", "123456", "newpassword123")
