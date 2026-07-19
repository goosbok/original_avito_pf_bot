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


# --------------------------------------------------- /api/me/referral

def test_me_referral_requires_auth(tmp_db: Path) -> None:
    assert _client().get("/api/me/referral").status_code == 401


def test_create_and_list_links(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    r = c.post("/api/me/referral/links", json={"slug": "youtube"}, headers=_auth(1))
    assert r.status_code == 201
    assert r.json()["slug"] == "youtube"
    r = c.post("/api/me/referral/links", json={}, headers=_auth(1))  # случайный
    assert r.status_code == 201
    summary = c.get("/api/me/referral", headers=_auth(1)).json()
    assert summary["percent"] == 10
    assert len(summary["links"]) == 2


def test_create_link_conflict_and_invalid(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    c.post("/api/me/referral/links", json={"slug": "youtube"}, headers=_auth(1))
    assert c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).status_code == 409
    assert c.post("/api/me/referral/links", json={"slug": "БАД слаг"},
                  headers=_auth(1)).status_code == 422


def test_archive_link_endpoint(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    link = c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).json()
    assert c.delete(f"/api/me/referral/links/{link['id']}",
                    headers=_auth(1)).status_code == 204
    assert c.delete(f"/api/me/referral/links/{link['id']}",
                    headers=_auth(1)).status_code == 404  # уже архивная


def test_click_endpoint_public_and_silent(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    c = _client()
    link = c.post("/api/me/referral/links", json={"slug": "youtube"},
                  headers=_auth(1)).json()
    assert c.post("/api/referral/click?code=1-youtube").status_code == 200
    assert c.post("/api/referral/click?code=мусор").status_code == 200
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT clicks FROM referral_links WHERE id = ?", (link["id"],)
        ).fetchone()[0] == 1


def test_create_link_deleted_user_is_404_not_500(tmp_db: Path) -> None:
    """JWT валиден, но пользователя нет (удалён/влит при merge) → 404, не 500."""
    r = _client().post("/api/me/referral/links", json={"slug": "youtube"}, headers=_auth(777))
    assert r.status_code == 404


def test_bonuses_history_endpoint(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id,"
            " link_id, amount, percent, created_at)"
            " VALUES (1, 2, NULL, NULL, 100, 10, '2026-07-18')"
        )
    rows = _client().get("/api/me/referral/bonuses", headers=_auth(1)).json()
    assert rows[0]["amount"] == 100


# --------------------------------------------------- admin

def _seed_admin(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '1')"
        )


def test_admin_referral_requires_admin(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 10)
    _seed_admin(tmp_db)
    c = _client()
    assert c.get("/api/admin/users/10/referral",
                 headers=_auth(10)).status_code == 403
    assert c.get("/api/admin/users/10/referral",
                 headers=_auth(1)).status_code == 200


def test_admin_sets_custom_percent(tmp_db: Path) -> None:
    from services.referral import create_link, get_bonus_percent
    _mk_user(tmp_db, 1)
    _mk_user(tmp_db, 10)
    _seed_admin(tmp_db)
    link = create_link(10, "vip-deal")
    c = _client()
    r = c.patch(f"/api/admin/referral/links/{link['id']}",
                json={"custom_percent": 30}, headers=_auth(1))
    assert r.status_code == 200
    assert get_bonus_percent(link["id"]) == 30
    # Сброс
    r = c.patch(f"/api/admin/referral/links/{link['id']}",
                json={"custom_percent": None}, headers=_auth(1))
    assert r.status_code == 200
    assert get_bonus_percent(link["id"]) == 10
    # Вне диапазона
    assert c.patch(f"/api/admin/referral/links/{link['id']}",
                   json={"custom_percent": 150}, headers=_auth(1)).status_code == 422
    # Пустое тело — 422 (поле обязательное), а не молчаливый сброс процента
    assert c.patch(f"/api/admin/referral/links/{link['id']}",
                   json={}, headers=_auth(1)).status_code == 422
    # Не существует
    assert c.patch("/api/admin/referral/links/9999",
                   json={"custom_percent": 30}, headers=_auth(1)).status_code == 404
