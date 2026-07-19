"""REST партнерки + атрибуция при веб-регистрации."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from web.main import app
    return TestClient(app)


def _mk_user(tmp_db: Path, user_id: int) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (?, 0)", (user_id,))


def _token(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


# --------------------------------------------------- регистрация с ref_code

def _issue_phone_otp(phone: str) -> str:
    from services import otp
    return otp.issue(channel='sms', destination=phone, purpose='phone_login',
                     ttl_seconds=300, cooldown_seconds=0)


def test_phone_verify_new_user_attributed(tmp_db: Path) -> None:
    _mk_user(tmp_db, 42)
    code = _issue_phone_otp("+79990001122")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001122", "code": code, "ref_code": "42",
    })
    assert r.status_code == 200
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT u.ref_id FROM users u "
            "JOIN auth_providers ap ON ap.user_id = u.id "
            "WHERE ap.provider='phone' AND ap.identifier='+79990001122'"
        ).fetchone()
    assert row[0] == 42


def test_phone_verify_existing_user_not_reattributed(tmp_db: Path) -> None:
    from services import identity
    _mk_user(tmp_db, 42)
    existing = identity.find_or_create_user_by_phone("+79990001122", verified=True)
    code = _issue_phone_otp("+79990001122")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001122", "code": code, "ref_code": "42",
    })
    assert r.status_code == 200
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = ?", (existing,)
        ).fetchone()[0] is None


def test_phone_verify_bad_ref_code_ignored(tmp_db: Path) -> None:
    """Битый ref_code не должен ломать регистрацию."""
    code = _issue_phone_otp("+79990001133")
    r = _client().post("/api/auth/phone/verify", json={
        "phone": "+79990001133", "code": code, "ref_code": "999-nope",
    })
    assert r.status_code == 200


def test_email_verify_new_user_attributed(tmp_db: Path, monkeypatch) -> None:
    """Email-регистрация с ref_code атрибуцирует нового юзера."""
    import sqlite3 as _sqlite3
    import services.email_sender as email_sender
    monkeypatch.setattr(email_sender, "send_email", lambda *a, **k: None)
    from services import auth_email
    _mk_user(tmp_db, 42)
    auth_email.register_request("newbie@example.com", "password123", first_name="Newbie")
    with _sqlite3.connect(tmp_db) as con:
        con.row_factory = _sqlite3.Row
        code = con.execute(
            "SELECT code FROM pending_email_registrations WHERE email = ?",
            ("newbie@example.com",),
        ).fetchone()["code"]
    r = _client().post("/api/auth/email/register-verify", json={
        "email": "newbie@example.com", "code": code, "ref_code": "42",
    })
    assert r.status_code == 200
    from web.auth import decode_jwt
    new_user_id = decode_jwt(r.json()["access_token"])
    with _sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT ref_id FROM users WHERE id = ?", (new_user_id,)
        ).fetchone()[0] == 42
