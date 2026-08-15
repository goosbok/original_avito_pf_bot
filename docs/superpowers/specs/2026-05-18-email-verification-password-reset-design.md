# Email Verification, Password Confirm & Password Reset — Design

**Date:** 2026-05-18  
**Status:** Approved

## Problem

1. `POST /api/auth/link/email` links an email to an authenticated account immediately, without verifying the user owns that email address. Any email can be linked without proof.
2. No "confirm password" field when setting a password — typos go undetected.
3. No password reset mechanism exists; users who forget their email-login password are locked out.

---

## Architecture

Three independent changes to the existing auth system:

1. **Email link verification** — the existing one-step `POST /api/auth/link/email` becomes a 2-step OTP flow matching the registration pattern. New table `pending_email_links`. All existing OTP infrastructure (`send_email`, code generation, TTL, cooldown constants) is reused from `services/auth_email.py`.

2. **Password confirmation** — `password_confirm` field added to Pydantic schemas for all endpoints where the user sets a password for the first time (link email, registration). Validated via `model_validator(mode='after')` — mismatch raises 422. The service layer receives a single `password` as before; confirmation is a schema concern only.

3. **Password reset** — new service `services/auth_reset.py`. Uses URL tokens rather than OTP codes: `secrets.token_urlsafe(32)` raw token, stored as SHA-256 hex hash, TTL 1 hour, one-time use. New table `password_reset_tokens`.

---

## Data Model

Two new tables added to `get_schema_statements()` in `utils/sqlite3.py`.

### `pending_email_links`

Stores OTP codes for email-link verification. Mirrors `pending_email_registrations` but includes `user_id` instead of `first_name`.

```sql
CREATE TABLE IF NOT EXISTS pending_email_links(
  email         TEXT PRIMARY KEY,
  user_id       INTEGER NOT NULL,
  password_hash TEXT NOT NULL,
  code          TEXT NOT NULL,
  expires_at    TIMESTAMP NOT NULL,
  created_at    TIMESTAMP NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### `password_reset_tokens`

One-time URL tokens for password reset.

```sql
CREATE TABLE IF NOT EXISTS password_reset_tokens(
  token_hash TEXT PRIMARY KEY,
  email      TEXT NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  used_at    TIMESTAMP,
  created_at TIMESTAMP NOT NULL
)
```

### Migration

`scripts/migrate_phase3.py` — idempotent script that creates both tables via `CREATE TABLE IF NOT EXISTS` on the existing production DB. Safe to run multiple times.

---

## API Endpoints

### Email Link (replacing `POST /api/auth/link/email`)

The old one-step endpoint is removed. Replaced by two steps, both requiring JWT auth.

**Step 1 — request OTP**

```
POST /api/auth/link/email/request
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secret123",
  "password_confirm": "secret123"
}
```

Responses:
- `204` — OTP sent to email
- `400` — invalid email or password < 8 chars
- `409` — email already linked (to this or another account)
- `422` — `password != password_confirm`
- `429` — cooldown (< 60 s since last request); `Retry-After` header set
- `502` — SMTP failure

**Step 2 — verify OTP**

```
POST /api/auth/link/email/verify
Authorization: Bearer <jwt>

{
  "email": "user@example.com",
  "code": "123456"
}
```

Responses:
- `204` — email linked successfully
- `401` — wrong code
- `410` — code expired

---

### Registration (`POST /api/auth/email/register-request`)

`EmailRegisterRequest` gains `password_confirm`. Mismatch → 422.

```json
{
  "email": "user@example.com",
  "password": "secret123",
  "password_confirm": "secret123",
  "first_name": "Ivan"
}
```

Legacy `POST /api/auth/email/register` (no OTP) keeps its current schema unchanged — it already has a deprecation note in code.

---

### Password Reset

**Forgot password — request reset link**

```
POST /api/auth/email/forgot-password

{ "email": "user@example.com" }
```

Always returns `200 OK` with an empty body. Never reveals whether the email is registered.

If the email has an active `auth_providers` row with `provider='email'`:
- generates `secrets.token_urlsafe(32)` (raw token, never stored)
- stores `SHA-256(raw_token)` in `password_reset_tokens` with `expires_at = now + 1h`
- deletes any prior unexpired tokens for this email before inserting
- sends email to the address with link: `{SITE_URL}/reset-password?token={raw_token}`

If the email is not registered: silently does nothing.

**Reset password — consume token**

```
POST /api/auth/email/reset-password

{
  "token": "<raw_token_from_url>",
  "new_password": "newsecret123",
  "new_password_confirm": "newsecret123"
}
```

Responses:
- `204` — password updated
- `400` — token not found, expired, or already used
- `422` — `new_password != new_password_confirm` or password too short

On success:
- computes `SHA-256(token)`, looks up `password_reset_tokens`
- validates not expired and `used_at IS NULL`
- updates `credential_hash` in `auth_providers` for this email
- sets `used_at = now` on the token

---

## Service Layer

### `services/auth_email.py` additions

```python
def link_email_request(user_id: int, email: str, password: str) -> None:
    """Step 1: validate, store pending row, send OTP. Mirrors register_request."""
    # Raises: InvalidCredentials, ProviderAlreadyLinked, OTPCooldown, EmailSendError

def link_email_verify(user_id: int, email: str, code: str) -> None:
    """Step 2: verify OTP, call identity.link_provider."""
    # Raises: OTPExpired, OTPInvalid, ProviderAlreadyLinked
```

Reuses `CODE_TTL_MINUTES = 10`, `CODE_RESEND_COOLDOWN_SECONDS = 60`, `_generate_code()` from the same module.

### `services/auth_reset.py` (new file)

```python
RESET_TOKEN_TTL_HOURS = 1

def forgot_password(email: str) -> None:
    """Generate reset token and send link. Always silent if email unknown."""

def reset_password(raw_token: str, new_password: str) -> None:
    """Validate token, update credential_hash, mark token used."""
    # Raises: ValueError (token invalid/expired/used), ValueError (password too short)
```

---

## Schema Changes (`web/schemas.py`)

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

`EmailRegisterRequest` gains `password_confirm` with the same `model_validator`.

---

## Router Changes

### `web/routers/auth_link.py`

- Remove `POST /api/auth/link/email` (old one-step endpoint)
- Add `POST /api/auth/link/email/request` → calls `auth_email.link_email_request`
- Add `POST /api/auth/link/email/verify` → calls `auth_email.link_email_verify`

### `web/routers/auth_email.py`

- Add `POST /api/auth/email/forgot-password` → calls `auth_reset.forgot_password`
- Add `POST /api/auth/email/reset-password` → calls `auth_reset.reset_password`
- Update `POST /api/auth/email/register-request` to use updated `EmailRegisterRequest` schema

---

## Error Handling

| Flow | Condition | HTTP code |
|---|---|---|
| link/request | email invalid | 400 |
| link/request | password < 8 chars | 400 |
| link/request | email already linked (same user) | 400 |
| link/request | email linked to another user | 409 |
| link/request | cooldown active | 429 + Retry-After |
| link/request | SMTP failure | 502 |
| link/verify | wrong code | 401 |
| link/verify | code expired | 410 |
| link/verify | email already linked (race) | 409 |
| forgot-password | any case | 200 (always) |
| reset-password | passwords mismatch | 422 |
| reset-password | token invalid / expired / used | 400 |
| any set-password | passwords mismatch | 422 |

---

## Testing

- Unit tests for `link_email_request` / `link_email_verify` in `tests/unit/test_auth_email.py` (mirrors existing `register_request` / `register_verify` tests)
- Unit tests for `forgot_password` / `reset_password` in `tests/unit/test_auth_reset.py`
- Web tests for new endpoints in `tests/web/test_routers_auth_link.py` and `tests/web/test_routers_auth_email.py`
- Schema validation tests for `password_confirm` mismatch → 422
