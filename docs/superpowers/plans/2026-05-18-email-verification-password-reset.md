# Email Verification, Password Confirm & Password Reset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OTP-based email verification when linking email to an account, server-side password-confirm validation, and a secure password-reset-via-email-link flow.

**Architecture:** Two new SQLite tables (`pending_email_links`, `password_reset_tokens`) back three independent changes: (1) the single-step `POST /api/auth/link/email` is replaced by a 2-step OTP flow matching the registration pattern, reusing all existing email/OTP infrastructure; (2) `password_confirm` is added server-side to schemas where a password is first set; (3) a new `services/auth_reset.py` handles password reset via `secrets.token_urlsafe(32)` tokens stored as SHA-256 hashes with a 1-hour TTL.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (via `services/db.py`), Pydantic v2, bcrypt, aiogram (bot, untouched by this plan), pytest, smtplib.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `utils/sqlite3.py` | Modify | Add 2 new table DDLs to `get_schema_statements()` |
| `web/schemas.py` | Modify | Add `password_confirm` to `EmailRegisterRequest`; add 4 new schemas |
| `tests/unit/test_schemas.py` | Create | Unit tests for password-confirm validation |
| `services/auth_email.py` | Modify | Add `link_email_request()` and `link_email_verify()` |
| `tests/unit/test_auth_email.py` | Modify | Add tests for link flow |
| `web/routers/auth_link.py` | Modify | Replace old `/email` with `/email/request` + `/email/verify` |
| `tests/web/test_routers_auth_link.py` | Modify | Replace old link-email tests with 2-step flow tests |
| `tests/web/test_routers_auth_email.py` | Modify | Update existing tests (password_confirm field), add reset tests |
| `services/auth_reset.py` | Create | `forgot_password()` and `reset_password()` |
| `tests/unit/test_auth_reset.py` | Create | Unit tests for reset flow |
| `web/routers/auth_email.py` | Modify | Add `forgot-password` and `reset-password` endpoints |
| `scripts/migrate_phase3.py` | Create | Idempotent one-shot migration for existing prod DBs |

---

## Task 1: DB Schema — Add Two New Tables

**Files:**
- Modify: `utils/sqlite3.py` (inside `get_schema_statements()`, after the `pending_email_registrations` entry)

- [ ] **Step 1: Write a failing test that checks both new tables exist**

Create `tests/unit/test_db_schema.py`:

```python
import sqlite3
from pathlib import Path
import pytest


def test_pending_email_links_table_exists(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_email_links'"
        ).fetchone()
        assert row is not None


def test_password_reset_tokens_table_exists(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset_tokens'"
        ).fetchone()
        assert row is not None


def test_pending_email_links_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pending_email_links)").fetchall()}
    assert cols == {"email", "user_id", "password_hash", "code", "expires_at", "created_at"}


def test_password_reset_tokens_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(password_reset_tokens)").fetchall()}
    assert cols == {"token_hash", "email", "expires_at", "used_at", "created_at"}
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/unit/test_db_schema.py -v
```

Expected: `FAILED` — `AssertionError: assert None is not None`

- [ ] **Step 3: Add both tables to `get_schema_statements()` in `utils/sqlite3.py`**

Insert after the `pending_email_registrations` tuple (after line ~981), before the closing `]`:

```python
        (
            "pending_email_links",
            "CREATE TABLE IF NOT EXISTS pending_email_links("
            "email TEXT PRIMARY KEY,"
            "user_id INTEGER NOT NULL,"
            "password_hash TEXT NOT NULL,"
            "code TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
        (
            "password_reset_tokens",
            "CREATE TABLE IF NOT EXISTS password_reset_tokens("
            "token_hash TEXT PRIMARY KEY,"
            "email TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "used_at TIMESTAMP,"
            "created_at TIMESTAMP NOT NULL)",
            5,
        ),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_db_schema.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_db_schema.py
git commit -m "feat(db): add pending_email_links and password_reset_tokens tables"
```

---

## Task 2: Pydantic Schemas — password_confirm + New Schemas

**Files:**
- Modify: `web/schemas.py`
- Create: `tests/unit/test_schemas.py`
- Modify: `tests/web/test_routers_auth_email.py` (update existing tests)

- [ ] **Step 1: Write failing schema unit tests**

Create `tests/unit/test_schemas.py`:

```python
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/unit/test_schemas.py -v
```

Expected: `ImportError` or `ValidationError not raised` — schemas don't exist yet.

- [ ] **Step 3: Update `web/schemas.py`**

Change the import line at the top of `web/schemas.py`:

```python
# Before:
from pydantic import BaseModel, EmailStr, Field, field_validator

# After:
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
```

Replace the existing `EmailRegisterRequest` class:

```python
class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=1, max_length=128)
    first_name: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def passwords_match(self) -> 'EmailRegisterRequest':
        if self.password != self.password_confirm:
            raise ValueError('passwords do not match')
        return self
```

Add these four new schemas after `EmailRegisterVerifyRequest`:

```python
class LinkEmailRequestStep1(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'LinkEmailRequestStep1':
        if self.password != self.password_confirm:
            raise ValueError('passwords do not match')
        return self


class LinkEmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def passwords_match(self) -> 'ResetPasswordRequest':
        if self.new_password != self.new_password_confirm:
            raise ValueError('passwords do not match')
        return self
```

- [ ] **Step 4: Run schema unit tests to verify they pass**

```bash
pytest tests/unit/test_schemas.py -v
```

Expected: 8 passed

- [ ] **Step 5: Fix existing web tests broken by the `EmailRegisterRequest` change**

`EmailRegisterRequest` now requires `password_confirm`. The tests in `tests/web/test_routers_auth_email.py` that POST to `/api/auth/email/register` or `/api/auth/email/register-request` without this field will return 422. Update them:

In `tests/web/test_routers_auth_email.py`, add `"password_confirm": "password123"` to every JSON payload that has `"password": "password123"`. The full updated file:

```python
"""Tests for email registration and login endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def test_register_returns_jwt(client):
    r = client.post("/api/auth/email/register", json={
        "email": "alice@example.com",
        "password": "password123",
        "password_confirm": "password123",
        "first_name": "Alice",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_register_duplicate_email_409(client):
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }
    client.post("/api/auth/email/register", json=payload).raise_for_status()
    r = client.post("/api/auth/email/register", json=payload)
    assert r.status_code == 409


def test_register_invalid_email_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "not-an-email",
        "password": "password123",
        "password_confirm": "password123",
    })
    assert r.status_code == 422


def test_register_short_password_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com",
        "password": "short",
        "password_confirm": "short",
    })
    assert r.status_code == 422


def test_register_password_mismatch_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com",
        "password": "password123",
        "password_confirm": "different123",
    })
    assert r.status_code == 422


def test_login_success(client):
    client.post("/api/auth/email/register", json={
        "email": "login@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "login@example.com",
        "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_401(client):
    client.post("/api/auth/email/register", json={
        "email": "user@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "user@example.com",
        "password": "wrongpass",
    })
    assert r.status_code == 401


def test_login_unknown_email_401(client):
    r = client.post("/api/auth/email/login", json={
        "email": "nobody@example.com",
        "password": "password123",
    })
    assert r.status_code == 401
```

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all existing tests pass (schema unit tests pass, web tests pass with updated payloads).

- [ ] **Step 7: Commit**

```bash
git add web/schemas.py tests/unit/test_schemas.py tests/web/test_routers_auth_email.py
git commit -m "feat(schemas): add password_confirm validation and new auth schemas"
```

---

## Task 3: Service — `link_email_request` and `link_email_verify`

**Files:**
- Modify: `services/auth_email.py`
- Modify: `tests/unit/test_auth_email.py`

- [ ] **Step 1: Write failing unit tests**

Append to `tests/unit/test_auth_email.py`:

```python
# ── link_email_request / link_email_verify tests ─────────────────────────────

from services import identity as _identity
from services.exceptions import ProviderAlreadyLinked


def _get_pending_link(tmp_db: Path, email: str):
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT * FROM pending_email_links WHERE email = ?", (email,)
        ).fetchone()


def _extract_link_code(tmp_db: Path, email: str) -> str:
    row = _get_pending_link(tmp_db, email)
    assert row is not None, f"no pending link row for {email}"
    return row["code"]


def test_link_email_request_creates_pending(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1001)
    auth_email.link_email_request(uid, "link@example.com", "password123")
    row = _get_pending_link(tmp_db, "link@example.com")
    assert row is not None
    assert int(row["user_id"]) == uid
    assert len(row["code"]) == 6
    assert row["code"].isdigit()


def test_link_email_request_sends_email(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1002)
    auth_email.link_email_request(uid, "sendlink@example.com", "password123")
    assert len(fake_send_email) == 1
    sent = fake_send_email[0]
    assert sent["to"] == "sendlink@example.com"
    assert _extract_link_code(tmp_db, "sendlink@example.com") in sent["body"]


def test_link_email_request_already_linked_raises(tmp_db: Path, fake_send_email):
    uid_a = auth_email.register("takenlink@example.com", "password123")
    uid_b = _identity.get_or_create_user_by_telegram(1003)
    with pytest.raises(ProviderAlreadyLinked):
        auth_email.link_email_request(uid_b, "takenlink@example.com", "password123")
    assert fake_send_email == []


def test_link_email_request_cooldown(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1004)
    auth_email.link_email_request(uid, "coollink@example.com", "password123")
    with pytest.raises(OTPCooldown) as exc_info:
        auth_email.link_email_request(uid, "coollink@example.com", "password123")
    assert exc_info.value.retry_after_seconds > 0


def test_link_email_verify_success(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1005)
    auth_email.link_email_request(uid, "verify@example.com", "password123")
    code = _extract_link_code(tmp_db, "verify@example.com")
    auth_email.link_email_verify(uid, "verify@example.com", code)
    assert _identity.find_user_id_by_provider("email", "verify@example.com") == uid
    assert _get_pending_link(tmp_db, "verify@example.com") is None


def test_link_email_verify_can_login_after(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1006)
    auth_email.link_email_request(uid, "loginafter@example.com", "password123")
    code = _extract_link_code(tmp_db, "loginafter@example.com")
    auth_email.link_email_verify(uid, "loginafter@example.com", code)
    assert auth_email.login("loginafter@example.com", "password123") == uid


def test_link_email_verify_wrong_code(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1007)
    auth_email.link_email_request(uid, "wrongcode@example.com", "password123")
    with pytest.raises(OTPInvalid):
        auth_email.link_email_verify(uid, "wrongcode@example.com", "000000")
    assert _get_pending_link(tmp_db, "wrongcode@example.com") is not None


def test_link_email_verify_no_pending(tmp_db: Path):
    uid = _identity.get_or_create_user_by_telegram(1008)
    with pytest.raises(OTPInvalid):
        auth_email.link_email_verify(uid, "nopending@example.com", "123456")


def test_link_email_verify_expired(tmp_db: Path, fake_send_email):
    uid = _identity.get_or_create_user_by_telegram(1009)
    auth_email.link_email_request(uid, "explink@example.com", "password123")
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE pending_email_links SET expires_at = ? WHERE email = ?",
            ("2000-01-01T00:00:00+00:00", "explink@example.com"),
        )
        con.commit()
    code = _extract_link_code(tmp_db, "explink@example.com")
    with pytest.raises(OTPExpired):
        auth_email.link_email_verify(uid, "explink@example.com", code)


def test_link_email_verify_wrong_user(tmp_db: Path, fake_send_email):
    uid1 = _identity.get_or_create_user_by_telegram(1010)
    uid2 = _identity.get_or_create_user_by_telegram(1011)
    auth_email.link_email_request(uid1, "wronguser@example.com", "password123")
    code = _extract_link_code(tmp_db, "wronguser@example.com")
    with pytest.raises(OTPInvalid):
        auth_email.link_email_verify(uid2, "wronguser@example.com", code)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/unit/test_auth_email.py -k "link_email" -v
```

Expected: `AttributeError: module 'services.auth_email' has no attribute 'link_email_request'`

- [ ] **Step 3: Implement `link_email_request` and `link_email_verify` in `services/auth_email.py`**

Add `ProviderAlreadyLinked` to the existing import block at the top of `services/auth_email.py`:

```python
# Before:
from services.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
)

# After:
from services.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
    ProviderAlreadyLinked,
)
```

Append to the end of `services/auth_email.py`:

```python
def link_email_request(user_id: int, email: str, password: str) -> None:
    """Step 1 of email-link flow: validate, store pending row, send OTP.

    Raises:
      - InvalidCredentials: invalid email format
      - ProviderAlreadyLinked: email already linked to any account
      - OTPCooldown: last request < CODE_RESEND_COOLDOWN_SECONDS ago
      - EmailSendError: SMTP failure
      - ValueError: password too short
    """
    email_norm = normalize_email(email)

    existing = identity.find_user_id_by_provider("email", email_norm)
    if existing is not None:
        raise ProviderAlreadyLinked("email", email_norm, existing)

    cred = hash_password(password)

    from services.db import connect

    now = datetime.now(timezone.utc)
    with connect() as con:
        row = con.execute(
            "SELECT created_at FROM pending_email_links WHERE email = ?",
            (email_norm,),
        ).fetchone()
        if row is not None:
            try:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                elapsed = (now - created).total_seconds()
                if elapsed < CODE_RESEND_COOLDOWN_SECONDS:
                    raise OTPCooldown(int(CODE_RESEND_COOLDOWN_SECONDS - elapsed))
            except (ValueError, KeyError):
                pass

        code = _generate_code()
        expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)

        con.execute(
            "INSERT INTO pending_email_links"
            "(email, user_id, password_hash, code, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET "
            "user_id = excluded.user_id, "
            "password_hash = excluded.password_hash, "
            "code = excluded.code, "
            "expires_at = excluded.expires_at, "
            "created_at = excluded.created_at",
            (email_norm, user_id, cred, code, expires_at.isoformat(), now.isoformat()),
        )
        con.commit()

    from services.email_sender import send_email

    subject = "ProBoost — код подтверждения привязки почты"
    body = (
        f"Ваш код подтверждения: {code}\n\n"
        f"Код действителен {CODE_TTL_MINUTES} минут.\n\n"
        f"Если вы не запрашивали это, просто проигнорируйте письмо."
    )
    send_email(email_norm, subject, body)


def link_email_verify(user_id: int, email: str, code: str) -> None:
    """Step 2: verify OTP, link email to user account.

    Raises:
      - OTPInvalid: wrong code, no pending row, or wrong user_id
      - OTPExpired: code TTL passed
      - ProviderAlreadyLinked: race condition (email linked between request and verify)
    """
    email_norm = normalize_email(email)

    from services.db import connect

    now = datetime.now(timezone.utc)
    with connect() as con:
        row = con.execute(
            "SELECT user_id, password_hash, code, expires_at "
            "FROM pending_email_links WHERE email = ?",
            (email_norm,),
        ).fetchone()
        if row is None:
            raise OTPInvalid("Запросите код заново")
        if int(row["user_id"]) != user_id:
            raise OTPInvalid("Запросите код заново")

        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            raise OTPExpired("Код истёк, запросите новый")
        if str(row["code"]) != str(code).strip():
            raise OTPInvalid("Неверный код")

        password_hash = row["password_hash"]
        con.execute("DELETE FROM pending_email_links WHERE email = ?", (email_norm,))
        con.commit()

    identity.link_provider(user_id, "email", email_norm, credential_hash=password_hash)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_auth_email.py -v
```

Expected: all tests pass (existing + new link_email tests)

- [ ] **Step 5: Commit**

```bash
git add services/auth_email.py tests/unit/test_auth_email.py
git commit -m "feat(auth): add link_email_request and link_email_verify service functions"
```

---

## Task 4: Router — Replace `/email` with `/email/request` + `/email/verify`

**Files:**
- Modify: `web/routers/auth_link.py`
- Modify: `tests/web/test_routers_auth_link.py`

- [ ] **Step 1: Write new failing web tests and update broken ones**

Replace the full content of `tests/web/test_routers_auth_link.py` with:

```python
"""Tests for web/routers/auth_link.py endpoints."""
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    from web.main import app
    return TestClient(app)


def _make_headers(uid: int) -> dict:
    from web.auth import create_jwt
    return {"Authorization": f"Bearer {create_jwt(uid)}"}


@pytest.fixture
def no_email(monkeypatch):
    """Suppress actual email sends."""
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda *a, **kw: None)


def _get_link_code(tmp_db: Path, email: str) -> str:
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT code FROM pending_email_links WHERE email = ?", (email,)
        ).fetchone()
    assert row is not None
    return row["code"]


# ── /email/request ────────────────────────────────────────────────────────────

def test_link_email_request_204(client, tmp_db, no_email):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(2001)
    r = client.post("/api/auth/link/email/request", json={
        "email": "newlink@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_link_email_request_password_mismatch_422(client, tmp_db):
    from services import identity
    uid = identity.get_or_create_user_by_telegram(2002)
    r = client.post("/api/auth/link/email/request", json={
        "email": "mismatch@example.com",
        "password": "password123",
        "password_confirm": "different123",
    }, headers=_make_headers(uid))
    assert r.status_code == 422


def test_link_email_request_email_taken_by_other_409(client, tmp_db, no_email):
    from services import auth_email, identity
    uid_a = auth_email.register("taken@example.com", "password123")
    uid_b = identity.get_or_create_user_by_telegram(2003)
    r = client.post("/api/auth/link/email/request", json={
        "email": "taken@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }, headers=_make_headers(uid_b))
    assert r.status_code == 409


def test_link_email_request_requires_auth(client, tmp_db):
    r = client.post("/api/auth/link/email/request", json={
        "email": "a@b.com",
        "password": "password123",
        "password_confirm": "password123",
    })
    assert r.status_code == 401


# ── /email/verify ─────────────────────────────────────────────────────────────

def test_link_email_verify_204(client, tmp_db, no_email):
    from services import auth_email, identity
    uid = identity.get_or_create_user_by_telegram(2004)
    auth_email.link_email_request(uid, "verifylink@example.com", "password123")
    code = _get_link_code(tmp_db, "verifylink@example.com")
    r = client.post("/api/auth/link/email/verify", json={
        "email": "verifylink@example.com",
        "code": code,
    }, headers=_make_headers(uid))
    assert r.status_code == 204
    assert identity.find_user_id_by_provider("email", "verifylink@example.com") == uid


def test_link_email_verify_wrong_code_401(client, tmp_db, no_email):
    from services import auth_email, identity
    uid = identity.get_or_create_user_by_telegram(2005)
    auth_email.link_email_request(uid, "badcode@example.com", "password123")
    r = client.post("/api/auth/link/email/verify", json={
        "email": "badcode@example.com",
        "code": "000000",
    }, headers=_make_headers(uid))
    assert r.status_code == 401


def test_link_email_verify_requires_auth(client, tmp_db):
    r = client.post("/api/auth/link/email/verify", json={
        "email": "a@b.com",
        "code": "123456",
    })
    assert r.status_code == 401


# ── Remaining provider linking tests (unchanged) ──────────────────────────────

def test_unlink_when_only_one_provider_400(client, tmp_db):
    from services import auth_email
    uid = auth_email.register("solo@example.com", "password123")
    r = client.delete("/api/auth/link/email/solo@example.com", headers=_make_headers(uid))
    assert r.status_code == 400


def test_link_telegram_to_email_user(client, tmp_db, monkeypatch):
    from services import auth_email, auth_telegram
    uid = auth_email.register("linkme@example.com", "password123")
    captured = {}
    def fake_send(token, tg_id, text):
        m = re.search(r"\b(\d{6})\b", text)
        captured["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)
    r = client.post("/api/auth/link/telegram/request-code", json={
        "identifier": "555666",
    }, headers=_make_headers(uid))
    assert r.status_code == 204
    r = client.post("/api/auth/link/telegram/verify-code", json={
        "identifier": "555666", "code": captured["code"],
    }, headers=_make_headers(uid))
    assert r.status_code == 204


def test_unlink_provider_success(client, tmp_db):
    from services import auth_email, identity
    uid = auth_email.register("two@example.com", "password123")
    identity.link_provider(uid, "telegram", "111222")
    r = client.delete("/api/auth/link/email/two@example.com", headers=_make_headers(uid))
    assert r.status_code == 204
    assert identity.find_user_id_by_provider("email", "two@example.com") is None
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/web/test_routers_auth_link.py -k "link_email" -v
```

Expected: `FAILED` with 404 (endpoints don't exist yet) or `PASSED` for tests that don't use new endpoints.

- [ ] **Step 3: Rewrite `web/routers/auth_link.py`**

Replace the full content with:

```python
"""Provider linking/unlinking endpoints.

Allows authenticated users to:
- Link email with password to their account (2-step OTP)
- Link telegram via OTP code
- Unlink a provider (with guard against unlinking last provider)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services import auth_email, auth_telegram, identity
from services.exceptions import (
    EmailSendError,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
    ProviderAlreadyLinked,
)
from web.deps import require_user
from web.schemas import (
    LinkEmailRequestStep1,
    LinkEmailVerifyRequest,
    OTPRequestBody,
    OTPVerifyBody,
)

router = APIRouter(prefix="/api/auth/link", tags=["auth-link"])


@router.post("/email/request", status_code=204, response_model=None)
async def link_email_request(
    body: LinkEmailRequestStep1,
    user_id: int = Depends(require_user),
) -> None:
    """Step 1: validate email/password, send OTP to the email address."""
    try:
        auth_email.link_email_request(user_id, body.email, body.password)
    except ProviderAlreadyLinked as exc:
        if exc.existing_user_id == user_id:
            raise HTTPException(status_code=400, detail="email already linked to your account") from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except EmailSendError as exc:
        raise HTTPException(status_code=502, detail=f"email send failed: {exc}") from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/email/verify", status_code=204, response_model=None)
async def link_email_verify(
    body: LinkEmailVerifyRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Step 2: verify OTP, link email to the authenticated account."""
    try:
        auth_email.link_email_verify(user_id, body.email, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/telegram/request-code", status_code=204, response_model=None)
async def link_telegram_request(
    body: OTPRequestBody,
    user_id: int = Depends(require_user),
) -> None:
    """Request OTP code for linking telegram to current user."""
    try:
        auth_telegram.request_code(body.identifier, purpose="link", user_id_to_link=user_id)
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/telegram/verify-code", status_code=204, response_model=None)
async def link_telegram_verify(
    body: OTPVerifyBody,
    user_id: int = Depends(require_user),
) -> None:
    """Verify OTP code and link telegram to current user."""
    try:
        auth_telegram.verify_code_link(body.identifier, body.code, user_id)
    except OTPExpired:
        raise HTTPException(status_code=410, detail="code expired")
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{provider}/{identifier}", status_code=204, response_model=None)
async def unlink(
    provider: str,
    identifier: str,
    user_id: int = Depends(require_user),
) -> None:
    """Unlink a provider. Prevents unlinking the last provider."""
    providers = identity.list_providers(user_id)
    if len(providers) <= 1:
        raise HTTPException(status_code=400, detail="cannot unlink last provider")
    identity.unlink_provider(user_id, provider, identifier)
```

- [ ] **Step 4: Run the full auth_link test suite**

```bash
pytest tests/web/test_routers_auth_link.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/routers/auth_link.py tests/web/test_routers_auth_link.py
git commit -m "feat(router): replace link/email with 2-step OTP flow (request + verify)"
```

---

## Task 5: Service — `auth_reset` (password reset via URL token)

**Files:**
- Create: `services/auth_reset.py`
- Create: `tests/unit/test_auth_reset.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_auth_reset.py`:

```python
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/unit/test_auth_reset.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.auth_reset'`

- [ ] **Step 3: Create `services/auth_reset.py`**

```python
"""Password reset via secure URL tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

RESET_TOKEN_TTL_HOURS = 1


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def forgot_password(email: str) -> None:
    """Generate reset token and send link. Always silent if email is unknown or invalid."""
    from services.auth_email import normalize_email
    from services.exceptions import InvalidCredentials

    try:
        email_norm = normalize_email(email)
    except InvalidCredentials:
        return

    from services import identity

    if identity.find_user_id_by_provider("email", email_norm) is None:
        return

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=RESET_TOKEN_TTL_HOURS)

    from services.db import connect

    with connect() as con:
        con.execute("DELETE FROM password_reset_tokens WHERE email = ?", (email_norm,))
        con.execute(
            "INSERT INTO password_reset_tokens(token_hash, email, expires_at, created_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, email_norm, expires_at.isoformat(), now.isoformat()),
        )
        con.commit()

    from data import config as bot_config

    site_url = getattr(bot_config, "SITE_URL", "")
    reset_url = f"{site_url}/reset-password?token={raw_token}"

    from services.email_sender import send_email

    subject = "ProBoost — сброс пароля"
    body = (
        f"Для сброса пароля перейдите по ссылке:\n{reset_url}\n\n"
        f"Ссылка действительна {RESET_TOKEN_TTL_HOURS} час.\n\n"
        f"Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
    )
    send_email(email_norm, subject, body)


def reset_password(raw_token: str, new_password: str) -> None:
    """Validate token, update credential_hash, mark token used.

    Raises:
      - ValueError: token not found, expired, or already used
      - ValueError: new_password too short (from hash_password)
    """
    from services.auth_password import hash_password

    new_hash = hash_password(new_password)

    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    from services.db import connect

    with connect() as con:
        row = con.execute(
            "SELECT email, expires_at, used_at FROM password_reset_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()

        if row is None:
            raise ValueError("invalid or expired token")
        if row["used_at"] is not None:
            raise ValueError("token already used")

        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            raise ValueError("invalid or expired token")

        email = row["email"]

        con.execute(
            "UPDATE auth_providers SET credential_hash = ? "
            "WHERE provider = 'email' AND identifier = ?",
            (new_hash, email),
        )
        con.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
            (now.isoformat(), token_hash),
        )
        con.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_auth_reset.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add services/auth_reset.py tests/unit/test_auth_reset.py
git commit -m "feat(auth): add password reset service (forgot_password, reset_password)"
```

---

## Task 6: Router — `forgot-password` and `reset-password` Endpoints

**Files:**
- Modify: `web/routers/auth_email.py`
- Modify: `tests/web/test_routers_auth_email.py`

- [ ] **Step 1: Write failing web tests**

Append to `tests/web/test_routers_auth_email.py`:

```python
# ── password reset endpoint tests ─────────────────────────────────────────────

import re as _re


def _register_and_get_reset_token(client, monkeypatch, email: str) -> str:
    """Register a user, call forgot-password, return the raw token from the email."""
    captured = {}

    import services.email_sender as es
    monkeypatch.setattr(
        es, "send_email",
        lambda to, subject, body, **kw: captured.update({"body": body}),
    )
    client.post("/api/auth/email/register", json={
        "email": email,
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    client.post("/api/auth/email/forgot-password", json={"email": email})
    m = _re.search(r"token=([^\s\n]+)", captured["body"])
    assert m, "no token in reset email"
    return m.group(1)


def test_forgot_password_always_200(client, monkeypatch):
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda *a, **kw: None)
    r = client.post("/api/auth/email/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200


def test_forgot_password_sends_email_for_known_address(client, monkeypatch):
    calls = []
    import services.email_sender as es
    monkeypatch.setattr(es, "send_email", lambda to, *a, **kw: calls.append(to))
    client.post("/api/auth/email/register", json={
        "email": "knownreset@example.com",
        "password": "password123",
        "password_confirm": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/forgot-password", json={"email": "knownreset@example.com"})
    assert r.status_code == 200
    assert calls == ["knownreset@example.com"]


def test_reset_password_success_204(client, tmp_db, monkeypatch):
    raw_token = _register_and_get_reset_token(client, monkeypatch, "newpw@example.com")
    r = client.post("/api/auth/email/reset-password", json={
        "token": raw_token,
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123",
    })
    assert r.status_code == 204
    # Can now log in with new password
    r2 = client.post("/api/auth/email/login", json={
        "email": "newpw@example.com",
        "password": "newpassword123",
    })
    assert r2.status_code == 200


def test_reset_password_mismatch_422(client):
    r = client.post("/api/auth/email/reset-password", json={
        "token": "anytoken",
        "new_password": "password123",
        "new_password_confirm": "different123",
    })
    assert r.status_code == 422


def test_reset_password_invalid_token_400(client, tmp_db):
    r = client.post("/api/auth/email/reset-password", json={
        "token": "invalidtoken",
        "new_password": "password123",
        "new_password_confirm": "password123",
    })
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/web/test_routers_auth_email.py -k "forgot or reset" -v
```

Expected: `FAILED` — 404 (endpoints don't exist yet)

- [ ] **Step 3: Add endpoints to `web/routers/auth_email.py`**

Add these imports at the top of `web/routers/auth_email.py` (merge into existing import blocks):

```python
from fastapi import APIRouter, HTTPException, Response   # Response already present, just noting
from services import auth_reset as _auth_reset           # new import
from web.schemas import (
    # existing imports …
    ForgotPasswordRequest,   # new
    ResetPasswordRequest,    # new
)
```

Then append two new endpoint functions after the existing `login` function:

```python
@router.post("/forgot-password", response_model=None)
async def forgot_password(body: ForgotPasswordRequest) -> Response:
    """Send password reset link to email. Always returns 200 — never reveals registration status."""
    try:
        _auth_reset.forgot_password(body.email)
    except Exception:
        pass
    return Response(status_code=200)


@router.post("/reset-password", status_code=204, response_model=None)
async def reset_password(body: ResetPasswordRequest) -> None:
    """Consume reset token and set a new password."""
    try:
        _auth_reset.reset_password(body.token, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add web/routers/auth_email.py tests/web/test_routers_auth_email.py
git commit -m "feat(router): add forgot-password and reset-password endpoints"
```

---

## Task 7: Migration Script for Existing Production DBs

**Files:**
- Create: `scripts/migrate_phase3.py`

- [ ] **Step 1: Create the migration script**

```python
"""One-shot migration Phase 3: add pending_email_links and password_reset_tokens.

Idempotent — safe to run multiple times.
Run AFTER deploying the new code: python scripts/migrate_phase3.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


def main() -> None:
    con = sqlite3.connect(path_database)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS pending_email_links("
            "email TEXT PRIMARY KEY,"
            "user_id INTEGER NOT NULL,"
            "password_hash TEXT NOT NULL,"
            "code TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS password_reset_tokens("
            "token_hash TEXT PRIMARY KEY,"
            "email TEXT NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "used_at TIMESTAMP,"
            "created_at TIMESTAMP NOT NULL)"
        )
        con.commit()
        print("migrate_phase3: done — pending_email_links and password_reset_tokens created")
    finally:
        con.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/migrate_phase3.py
git commit -m "chore(migrate): phase3 — pending_email_links and password_reset_tokens"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| OTP verification when linking email | Task 3, Task 4 |
| `password_confirm` server-side validation | Task 2 |
| Password reset via email link | Task 5, Task 6 |
| Two new DB tables | Task 1 |
| Migration script | Task 7 |
| `forgot-password` always 200 | Task 6 |
| Token one-time use | Task 5 |
| Token TTL 1 hour | Task 5 |
| Token stored as SHA-256 hash | Task 5 |
| `password_confirm` in registration flow | Task 2 |
| 409 on email already linked to another user | Task 4 |
| 410 on expired OTP code | Task 4 |

**Placeholder scan:** No TBDs, TODOs, or "similar to task N" patterns.

**Type consistency:**
- `link_email_request(user_id: int, email: str, password: str)` — used in Task 3, Task 4 ✓
- `link_email_verify(user_id: int, email: str, code: str)` — used in Task 3, Task 4 ✓
- `forgot_password(email: str)` — used in Task 5, Task 6 ✓
- `reset_password(raw_token: str, new_password: str)` — used in Task 5, Task 6 ✓
- `LinkEmailRequestStep1` — defined in Task 2, used in Task 4 ✓
- `LinkEmailVerifyRequest` — defined in Task 2, used in Task 4 ✓
- `ForgotPasswordRequest` — defined in Task 2, used in Task 6 ✓
- `ResetPasswordRequest` — defined in Task 2, used in Task 6 ✓
