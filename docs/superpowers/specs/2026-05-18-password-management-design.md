# Password Management — Design Spec

**Date:** 2026-05-18

## Overview

Two features:
- **Change password** — authenticated user with email linked can change their password from the Profile page
- **Forgot/Reset password** — unauthenticated user can reset password via email link (backend already exists)

---

## Feature A: Change Password

### Backend

**New endpoint:** `POST /api/auth/change-password`

- Requires auth (`require_user` dependency)
- Request body: `{ current_password, new_password, new_password_confirm }`
- Schema validation: `new_password` min 8 chars, `new_password_confirm` must match
- Service logic (`services/auth_email.py::change_password`):
  1. Fetch `auth_providers` row where `user_id=user_id` and `provider='email'`
  2. Raise `InvalidCredentials` if no email provider or `bcrypt.verify(current_password, stored_hash)` fails
  3. Raise `ValueError("new password must differ from current")` if new hash would match old
  4. Update `password_hash` in `auth_providers`
- HTTP error mapping:
  - 401 — `InvalidCredentials` (wrong current password)
  - 400 — `ValueError` (new == old, or no email linked)

**New schema:** `ChangePasswordRequest`
```
current_password: str (min 1)
new_password: str (min 8, max 128)
new_password_confirm: str (min 1)
@validator: new_password == new_password_confirm
```

**Router:** add to `web/routers/auth_email.py`.

### Frontend (Profile.jsx)

When `emailProvider` is linked, the ProviderCard shows the linked email + a "Сменить пароль" button.

Note: `ProviderCard` currently hides `children` when `linked=true`. The change-password form renders as a separate sibling `<div>` inside the same card, outside the `ProviderCard` children slot — or `ProviderCard` gets a new `linkedChildren` prop rendered unconditionally.

Clicking the button toggles an inline form (new state: `changePwOpen bool`):
- Field: Текущий пароль
- Field: Новый пароль (min 8)
- Field: Повторите новый пароль
- Button: "Сохранить"
- Button: "Отмена" (collapses form, clears fields)

On success: inline `alert--success` "Пароль изменён", form collapses.

Error handling:
- 401 → "Неверный текущий пароль"
- 400 → server message or "Ошибка смены пароля"

State added: `changePwOpen`, `changePwCurrent`, `changePwNew`, `changePwConfirm`, `changePwLoading`, `changePwError`, `changePwSuccess`.

---

## Feature B: Forgot / Reset Password

### Backend

Already implemented:
- `POST /api/auth/forgot-password` — `{ email }` → sends reset token to email (always returns 200)
- `POST /api/auth/reset-password` — `{ token, new_password, new_password_confirm }` → resets password, invalidates token

### Frontend (Auth.jsx)

#### New mode: `forgot`

Triggered by "Забыл пароль?" link below the password field in `login` mode.

UI:
- Heading: "Восстановление пароля"
- Field: Email
- Button: "Отправить ссылку"
- On success (any response): show "Если аккаунт существует, письмо отправлено" — always, to prevent email enumeration
- Link: "← Назад ко входу"

#### New mode: `reset`

Triggered on SPA load when `window.location.pathname === '/reset-password'` and `?token=xxx` is present in `window.location.search`. The server already serves `index.html` for all unknown paths via `StaticFiles(html=True)`, so no server changes needed.

`index.html`: on script init, extract token with `new URLSearchParams(location.search).get('token')` and pass to `AuthPage` as prop `resetToken`.

`AuthPage`: if `resetToken` is non-empty, set initial mode to `reset`.

UI:
- Heading: "Новый пароль"
- Field: Новый пароль (min 8)
- Field: Повторите пароль
- Button: "Сохранить"
- On success: show "Пароль изменён — войдите с новым паролем", switch to `login` mode, clear token from URL (`history.replaceState`)
- Error handling:
  - 410 → "Ссылка истекла — запросите новую"
  - 400 → server message or "Ошибка сброса пароля"

---

## Testing

### Unit tests (`tests/unit/test_auth_email.py`)
- `test_change_password_success` — updates hash, old password no longer works
- `test_change_password_wrong_current` — raises `InvalidCredentials`
- `test_change_password_same_password` — raises `ValueError`
- `test_change_password_no_email_provider` — raises `InvalidCredentials`

### Router tests (`tests/web/test_routers_auth_email.py` or new file)
- `test_change_password_204`
- `test_change_password_wrong_current_401`
- `test_change_password_mismatch_422`
- `test_change_password_requires_auth_401`

---

## Out of Scope

- Password strength meter
- Email notification on password change
- Rate limiting on `/change-password` (existing OTP cooldown infra not needed here)
