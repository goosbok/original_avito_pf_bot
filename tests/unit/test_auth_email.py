import sqlite3
from pathlib import Path

import pytest

from services import auth_email
from services.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
)


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


# ── 2-step email registration with verification code (Feature 2) ────────────

@pytest.fixture
def fake_send_email(monkeypatch):
    """Captures send_email calls instead of actually sending. Yields the call list."""
    calls: list[dict] = []

    def _capture(to: str, subject: str, body: str, *, html: bool = False) -> None:
        calls.append({"to": to, "subject": subject, "body": body, "html": html})

    # auth_email.register_request does `from services.email_sender import send_email`
    # inside the function, so patching the source module is enough.
    import services.email_sender as email_sender
    monkeypatch.setattr(email_sender, "send_email", _capture)
    return calls


def _get_pending(tmp_db: Path, email: str):
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT * FROM pending_email_registrations WHERE email = ?",
            (email,),
        ).fetchone()


def _extract_code(tmp_db: Path, email: str) -> str:
    row = _get_pending(tmp_db, email)
    assert row is not None, f"no pending row for {email}"
    return row["code"]


def test_register_request_creates_pending_and_sends_email(tmp_db: Path, fake_send_email):
    auth_email.register_request("alice@example.com", "password123", first_name="Alice")
    row = _get_pending(tmp_db, "alice@example.com")
    assert row is not None
    assert row["first_name"] == "Alice"
    assert len(row["code"]) == 6
    assert row["code"].isdigit()
    # send_email called once
    assert len(fake_send_email) == 1
    sent = fake_send_email[0]
    assert sent["to"] == "alice@example.com"
    assert row["code"] in sent["body"]


def test_register_request_existing_user_raises(tmp_db: Path, fake_send_email):
    # First, register a real user.
    auth_email.register("dup@example.com", "password123")
    with pytest.raises(EmailAlreadyRegistered):
        auth_email.register_request("dup@example.com", "newpass123")
    # No email sent.
    assert fake_send_email == []


def test_register_request_cooldown(tmp_db: Path, fake_send_email):
    auth_email.register_request("cool@example.com", "password123")
    with pytest.raises(OTPCooldown) as exc_info:
        auth_email.register_request("cool@example.com", "password123")
    assert exc_info.value.retry_after_seconds > 0


def test_register_verify_succeeds(tmp_db: Path, fake_send_email):
    auth_email.register_request("bob@example.com", "password123", first_name="Bob")
    code = _extract_code(tmp_db, "bob@example.com")
    user_id = auth_email.register_verify("bob@example.com", code)
    assert user_id > 0
    # Pending row deleted.
    assert _get_pending(tmp_db, "bob@example.com") is None
    # Can now log in.
    assert auth_email.login("bob@example.com", "password123") == user_id


def test_register_verify_wrong_code(tmp_db: Path, fake_send_email):
    auth_email.register_request("eve@example.com", "password123")
    with pytest.raises(OTPInvalid):
        auth_email.register_verify("eve@example.com", "000000")
    # Pending row still there for retry.
    assert _get_pending(tmp_db, "eve@example.com") is not None


def test_register_verify_no_pending(tmp_db: Path, fake_send_email):
    with pytest.raises(OTPInvalid):
        auth_email.register_verify("ghost@example.com", "123456")


def test_register_verify_expired_code(tmp_db: Path, fake_send_email, monkeypatch):
    auth_email.register_request("exp@example.com", "password123")
    code = _extract_code(tmp_db, "exp@example.com")
    # Manually expire the row.
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE pending_email_registrations SET expires_at = ? WHERE email = ?",
            ("2000-01-01T00:00:00+00:00", "exp@example.com"),
        )
        con.commit()
    with pytest.raises(OTPExpired):
        auth_email.register_verify("exp@example.com", code)


def test_register_verify_email_normalization(tmp_db: Path, fake_send_email):
    """Verify is case-insensitive on email matching, mirroring register_request."""
    auth_email.register_request("Mixed@Example.com", "password123")
    code = _extract_code(tmp_db, "mixed@example.com")
    user_id = auth_email.register_verify("MIXED@example.com", code)
    assert user_id > 0
