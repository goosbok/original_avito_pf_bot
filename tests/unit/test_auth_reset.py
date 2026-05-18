"""Unit tests for services/auth_reset.py."""
import re
import sqlite3
from pathlib import Path

import pytest

from services import auth_email, auth_reset


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


def _get_token_row(tmp_db: Path, email: str):
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT * FROM password_reset_tokens WHERE email = ?", (email,)
        ).fetchone()


def _extract_token(body: str) -> str:
    m = re.search(r"token=([^\s\n]+)", body)
    assert m, f"no token in body: {body!r}"
    return m.group(1)


def test_forgot_password_sends_email(tmp_db: Path, fake_send_email):
    _register("reset@example.com")
    auth_reset.forgot_password("reset@example.com")
    assert len(fake_send_email) == 1
    assert fake_send_email[0]["to"] == "reset@example.com"
    assert "reset-password" in fake_send_email[0]["body"]
    assert "token=" in fake_send_email[0]["body"]


def test_forgot_password_unknown_email_silent(tmp_db: Path, fake_send_email):
    auth_reset.forgot_password("nobody@example.com")
    assert fake_send_email == []


def test_forgot_password_invalid_email_silent(tmp_db: Path, fake_send_email):
    auth_reset.forgot_password("not-an-email")
    assert fake_send_email == []


def test_forgot_password_stores_token(tmp_db: Path, fake_send_email):
    _register("store@example.com")
    auth_reset.forgot_password("store@example.com")
    row = _get_token_row(tmp_db, "store@example.com")
    assert row is not None
    assert row["used_at"] is None


def test_forgot_password_replaces_old_token(tmp_db: Path, fake_send_email):
    _register("replace@example.com")
    auth_reset.forgot_password("replace@example.com")
    first_hash = _get_token_row(tmp_db, "replace@example.com")["token_hash"]
    auth_reset.forgot_password("replace@example.com")
    second_hash = _get_token_row(tmp_db, "replace@example.com")["token_hash"]
    assert first_hash != second_hash


def test_reset_password_success(tmp_db: Path, fake_send_email):
    uid = _register("pw@example.com")
    auth_reset.forgot_password("pw@example.com")
    raw_token = _extract_token(fake_send_email[0]["body"])
    auth_reset.reset_password(raw_token, "newpassword123")
    assert auth_email.login("pw@example.com", "newpassword123") == uid
    from services.exceptions import InvalidCredentials
    with pytest.raises(InvalidCredentials):
        auth_email.login("pw@example.com", "password123")


def test_reset_password_token_marked_used(tmp_db: Path, fake_send_email):
    _register("used@example.com")
    auth_reset.forgot_password("used@example.com")
    raw_token = _extract_token(fake_send_email[0]["body"])
    auth_reset.reset_password(raw_token, "newpassword123")
    row = _get_token_row(tmp_db, "used@example.com")
    assert row["used_at"] is not None


def test_reset_password_invalid_token_raises(tmp_db: Path):
    with pytest.raises(ValueError, match="invalid or expired"):
        auth_reset.reset_password("totally-invalid-token", "newpassword123")


def test_reset_password_already_used_raises(tmp_db: Path, fake_send_email):
    _register("twice@example.com")
    auth_reset.forgot_password("twice@example.com")
    raw_token = _extract_token(fake_send_email[0]["body"])
    auth_reset.reset_password(raw_token, "newpassword123")
    with pytest.raises(ValueError, match="already used"):
        auth_reset.reset_password(raw_token, "anotherpassword")


def test_reset_password_expired_token_raises(tmp_db: Path, fake_send_email):
    _register("exp@example.com")
    auth_reset.forgot_password("exp@example.com")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE password_reset_tokens SET expires_at = ? WHERE email = ?",
            ("2000-01-01T00:00:00+00:00", "exp@example.com"),
        )
        con.commit()
    raw_token = _extract_token(fake_send_email[0]["body"])
    with pytest.raises(ValueError, match="invalid or expired"):
        auth_reset.reset_password(raw_token, "newpassword123")


def test_reset_password_short_new_password_raises(tmp_db: Path, fake_send_email):
    _register("short@example.com")
    auth_reset.forgot_password("short@example.com")
    raw_token = _extract_token(fake_send_email[0]["body"])
    with pytest.raises(ValueError):
        auth_reset.reset_password(raw_token, "short")


def test_reset_password_email_provider_unlinked_raises(tmp_db: Path, fake_send_email):
    uid = _register("unlinked@example.com")
    auth_reset.forgot_password("unlinked@example.com")
    raw_token = _extract_token(fake_send_email[0]["body"])
    # Simulate email provider being unlinked after token was issued
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "DELETE FROM auth_providers WHERE provider = 'email' AND identifier = ?",
            ("unlinked@example.com",),
        )
        con.commit()
    with pytest.raises(ValueError, match="invalid or expired"):
        auth_reset.reset_password(raw_token, "newpassword123")
