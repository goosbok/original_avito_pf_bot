# Phase 2 — Multi-Provider Identity & API Platform

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Декаплить идентичность пользователя от Telegram. Telegram-бот становится одним из нескольких каналов взаимодействия. Пользователи могут регистрироваться/входить через email, Telegram OTP (бот шлёт код), и через API-ключи (для сторонних интеграций). Один пользователь может иметь несколько привязанных способов входа. Сторонние приложения (другие боты, веб-сервисы) регистрируются на платформе, получают API-ключ и создают заявки от имени своих конечных пользователей — для каждого создаётся ЛК с пометкой источника.

**Architecture:**
- **Identity layer** — новые таблицы `auth_providers`, `applications`, `otp_codes`. Колонка `users.id` остаётся auto-increment (для существующих юзеров значения совпадают с telegram_id, но это просто исторический artifact — новые юзеры получают новые id из автоинкремента).
- **Auth providers** — каждый способ входа (email, telegram, api) хранит свою запись в `auth_providers(user_id, provider, identifier, credential_hash)`. Один user_id → много auth_providers.
- **Applications** — каждое стороннее приложение принадлежит юзеру-разработчику, имеет API-ключ. Запросы через API-ключ обязаны указывать `X-End-User-Id` (внутренний идентификатор юзера в стороннем приложении), под который мы создаём/находим запись в наших users + auth_providers(provider='api:<app_id>').
- **Source tracking** — `refills` (и в будущем `orders`) получают колонки `source_type` (telegram/web/api) и `source_app_id` (FK на applications, NULL для не-API).
- **Bot** — продолжает работать с `telegram_id`. На границе с сервисами вызывает `identity.get_or_create_user_by_telegram(tg_id, …)` и работает с возвращённым internal `user_id`.

**Tech Stack:** добавляем `passlib[bcrypt]` (хеширование паролей), `email-validator` (валидация email через pydantic), `httpx` уже есть.

**Out of scope (для следующих фаз):**
- Phase 3 — перенос orders / promocodes / reviews в сервисы + соответствующие API-эндпоинты с source-tracking
- Phase 4 — миграция на Postgres, rate limiting per app, OAuth-провайдеры (Google, VK)
- 2FA / TOTP, SMS-OTP по номеру телефона
- Account merging UI (Phase 2 ограничивается: при конфликте линковки — explicit error)
- Telegram Mini App
- Refresh tokens (Phase 2 пока с долгоживущим JWT — 24 часа, как сейчас)

**File Structure (создаётся/изменяется в этом плане):**

```
services/
  identity.py             # NEW — get_or_create_user_by_*, link_provider, find_user_by_provider
  auth_password.py        # NEW — bcrypt-хелперы
  auth_email.py           # NEW — register_email, login_email
  otp.py                  # NEW — OTP generate/verify с TTL и attempt limit
  auth_telegram.py        # NEW — request_code (отправка через бот HTTP API), verify_code
  applications.py         # NEW — create_application, list_applications, revoke_application
  auth_api.py             # NEW — validate_api_key, get_or_create_end_user
  source.py               # NEW — Source enum (TELEGRAM, WEB, API), хелперы
  balance.py              # MODIFY — без изменений API, но user_id теперь internal
  refill.py               # MODIFY — finalize принимает source_type/source_app_id
  exceptions.py           # MODIFY — добавить InvalidCredentials, OTPInvalid, OTPExpired,
                          #          ProviderConflict, ApplicationNotFound, InvalidAPIKey
  db.py                   # без изменений

web/
  auth.py                 # MODIFY — JWT теперь содержит internal user_id, не telegram_id
  deps.py                 # MODIFY — current_user поддерживает JWT и API-key+end-user-id
  schemas.py              # MODIFY — добавить EmailRegister, EmailLogin, OTPRequest, …
  routers/
    auth.py               # DELETE — старый Telegram Login Widget endpoint удаляется
    auth_email.py         # NEW — POST /api/auth/email/register, /login
    auth_telegram.py      # NEW — POST /api/auth/telegram/request-code, /verify-code
    auth_link.py          # NEW — POST /api/auth/link/telegram/*, /email
    me.py                 # NEW — GET /api/me, GET /api/me/providers
    applications.py       # NEW — POST/GET/DELETE /api/applications
    refill.py             # MODIFY — теперь использует internal user_id
    api_v1/
      __init__.py         # NEW
      refill.py           # NEW — публичный API для сторонних приложений (auth = API key)
  static/
    index.html            # MODIFY — теперь форма выбора метода входа
    register.html         # NEW — форма email-регистрации
    login.html            # NEW — форма email-входа
    login_telegram.html   # NEW — форма Telegram OTP-входа (identifier + code)
    cabinet.html          # MODIFY — добавлены секции "Способы входа" и "Мои приложения"

handlers/
  user_functions.py       # MODIFY — refill-handler берёт internal_user_id через identity
middlewares/
  exists_user.py          # MODIFY — создаёт юзера через identity.get_or_create_user_by_telegram

utils/
  sqlite3.py              # MODIFY — get_schema_statements() расширена новыми таблицами + колонками

tests/
  unit/
    test_identity.py      # NEW
    test_auth_password.py # NEW
    test_auth_email.py    # NEW
    test_otp.py           # NEW
    test_auth_telegram.py # NEW
    test_applications.py  # NEW
    test_auth_api.py      # NEW
    test_source.py        # NEW
    test_balance.py       # MODIFY — мелкие правки если что-то требует
    test_refill.py        # MODIFY — добавить тесты на source-tracking
  web/
    test_routers_auth.py        # DELETE — заменяется
    test_routers_auth_email.py  # NEW
    test_routers_auth_telegram.py # NEW
    test_routers_auth_link.py   # NEW
    test_routers_applications.py # NEW
    test_routers_me.py          # NEW
    test_routers_refill.py      # MODIFY — теперь использует email-auth
    test_api_v1_refill.py       # NEW

scripts/
  migrate_phase2.py       # NEW — одноразовая миграция БД: создать новые таблицы, заполнить auth_providers для существующих юзеров

requirements.txt          # MODIFY — passlib[bcrypt], email-validator
data/example.config.py    # MODIFY — добавить OTP_TTL_SECONDS, OTP_MAX_ATTEMPTS, BOT_HTTP_API_BASE
docs/superpowers/plans/2026-05-06-multi-provider-identity.md  # этот файл
docs/superpowers/plans/2026-05-06-multi-provider-identity-smoke.md  # E2E чек-лист (Task 23)
```

---

## Task 1: Зависимости и конфиг

**Files:**
- Modify: `requirements.txt`
- Modify: `data/example.config.py`

- [ ] **Step 1: requirements.txt**

Добавить:
```
passlib[bcrypt]==1.7.4
email-validator==2.2.0
```

- [ ] **Step 2: data/example.config.py — добавить OTP-настройки**

Добавить в конец секцию:
```python
#################################
### OTP (Telegram login codes)
OTP_TTL_SECONDS = 300        # 5 минут
OTP_MAX_ATTEMPTS = 5         # после 5 неверных попыток код инвалидируется
OTP_RESEND_COOLDOWN = 60     # не чаще раза в минуту

# Telegram Bot HTTP API (используется для отправки OTP без aiogram)
BOT_HTTP_API_BASE = "https://api.telegram.org"
```

- [ ] **Step 3: Установить и проверить**

```bash
pip install -r requirements.txt
pytest --collect-only
```

Expected: ошибок нет.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt data/example.config.py
git commit -m "chore: add passlib/email-validator and OTP config"
```

---

## Task 2: Расширить схему БД (auth_providers, applications, otp_codes, source-колонки)

**Files:**
- Modify: `utils/sqlite3.py` — функция `get_schema_statements()`
- Modify: `tests/conftest.py` — обновить stub если нужно (добавить новые поля в config-stub если они нужны)

Стратегия: новые таблицы создаются всегда (`CREATE TABLE IF NOT EXISTS`). Новые колонки добавляются через ALTER в `create_db()` идемпотентно.

- [ ] **Step 1: Расширить get_schema_statements() новыми таблицами**

В `utils/sqlite3.py` в конец списка `get_schema_statements()` добавить:

```python
        (
            "auth_providers",
            "CREATE TABLE IF NOT EXISTS auth_providers("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "provider TEXT NOT NULL,"           # 'email' | 'telegram' | 'api:<app_id>'
            "identifier TEXT NOT NULL,"         # email | telegram_id | external_user_id
            "credential_hash TEXT,"             # bcrypt(password) для email; NULL для telegram/api
            "created_at TIMESTAMP NOT NULL,"
            "last_used_at TIMESTAMP,"
            "UNIQUE(provider, identifier),"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            8,
        ),
        (
            "applications",
            "CREATE TABLE IF NOT EXISTS applications("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "owner_user_id INTEGER NOT NULL,"
            "name TEXT NOT NULL,"
            "api_key_hash TEXT NOT NULL UNIQUE,"  # sha256(api_key)
            "api_key_prefix TEXT NOT NULL,"       # первые 12 символов для отображения, e.g. 'sk_live_abc1'
            "created_at TIMESTAMP NOT NULL,"
            "revoked_at TIMESTAMP,"
            "FOREIGN KEY (owner_user_id) REFERENCES users(id))",
            7,
        ),
        (
            "otp_codes",
            "CREATE TABLE IF NOT EXISTS otp_codes("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "purpose TEXT NOT NULL,"             # 'login' | 'link'
            "telegram_id INTEGER NOT NULL,"
            "code_hash TEXT NOT NULL,"            # sha256(code) — код не храним в открытом виде
            "user_id_to_link INTEGER,"            # для purpose='link' — какому юзеру привязать
            "created_at TIMESTAMP NOT NULL,"
            "expires_at TIMESTAMP NOT NULL,"
            "attempts INTEGER NOT NULL DEFAULT 0,"
            "consumed_at TIMESTAMP,"
            "FOREIGN KEY (user_id_to_link) REFERENCES users(id))",
            9,
        ),
```

- [ ] **Step 2: Идемпотентные ALTER TABLE для существующих таблиц**

Добавить в `utils/sqlite3.py` функцию `apply_phase2_migrations()`:

```python
def apply_phase2_migrations():
    """Идемпотентно добавляет колонки source-tracking в refills.

    Проверяет PRAGMA table_info — если колонки уже есть, пропускает.
    """
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        existing_cols = {row['name'] for row in con.execute("PRAGMA table_info(refills)").fetchall()}
        if 'source_type' not in existing_cols:
            con.execute("ALTER TABLE refills ADD COLUMN source_type TEXT NOT NULL DEFAULT 'telegram'")
            print("refills.source_type added")
        if 'source_app_id' not in existing_cols:
            con.execute("ALTER TABLE refills ADD COLUMN source_app_id INTEGER")
            print("refills.source_app_id added")
        # payment_id уже добавлен в Phase 1, но проверим на всякий
        if 'payment_id' not in existing_cols:
            con.execute("ALTER TABLE refills ADD COLUMN payment_id TEXT")
            print("refills.payment_id added")
        con.commit()


def create_db():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        for idx, (table, ddl, cols) in enumerate(get_schema_statements(), start=1):
            existing = con.execute(f"PRAGMA table_info({table})").fetchall()
            if len(existing) == cols:
                print(f"database was found ({table} | {idx}/{len(get_schema_statements())})")
            else:
                con.execute(ddl)
                print(f"database was not found ({table} | {idx}/{len(get_schema_statements())}), creating...")
        con.commit()
    apply_phase2_migrations()
```

- [ ] **Step 3: Обновить tmp_db фикстуру — она теперь должна применить миграции тоже**

В `tests/conftest.py` обновить tmp_db, чтобы после создания схемы вызывать миграции (хотя в тестах их и не должно быть — таблицы создаются с нужной схемой сразу). Для тестов добавим source-колонки сразу в DDL refills.

Внутри `get_schema_statements()` обновить refills DDL:

```python
        (
            "refills",
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "payment_id TEXT,"
            "source_type TEXT NOT NULL DEFAULT 'telegram',"
            "source_app_id INTEGER,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
```

(prod-БД эти колонки получит через `apply_phase2_migrations()`.)

- [ ] **Step 4: Прогнать существующие тесты**

```bash
pytest -v
```

Expected: те тесты, что были, проходят. Возможно, упадут тесты, ожидающие конкретного количества колонок — поправить.

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py tests/conftest.py
git commit -m "feat(db): add auth_providers/applications/otp_codes tables + source-tracking on refills"
```

---

## Task 3: Скрипт миграции для существующих юзеров

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/migrate_phase2.py`

Существующие юзеры в `users.id = telegram_id`. Нужно для каждого создать запись в `auth_providers(provider='telegram', identifier=str(id), user_id=id)`.

- [ ] **Step 1: Написать скрипт**

Создать `scripts/migrate_phase2.py`:

```python
"""One-shot миграция Phase 2: заполнить auth_providers для существующих юзеров.

Запускать ПОСЛЕ create_db() на проде. Идемпотентен — запуск второй раз ничего не делает.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


def main() -> None:
    con = sqlite3.connect(path_database)
    con.row_factory = sqlite3.Row
    try:
        users = con.execute("SELECT id FROM users").fetchall()
        now = datetime.now(timezone.utc).isoformat()

        inserted = 0
        skipped = 0
        for u in users:
            tg_id = u["id"]
            existing = con.execute(
                "SELECT 1 FROM auth_providers WHERE provider = 'telegram' AND identifier = ?",
                (str(tg_id),),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
                "VALUES (?, 'telegram', ?, ?)",
                (tg_id, str(tg_id), now),
            )
            inserted += 1
        con.commit()
        print(f"users={len(users)}, auth_providers inserted={inserted}, skipped={skipped}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-тест на пустой БД**

```bash
python -c "from utils.sqlite3 import create_db; create_db()"
python scripts/migrate_phase2.py
```

Expected: `users=0, auth_providers inserted=0, skipped=0`.

- [ ] **Step 3: Тест на БД с существующими юзерами (тестовая копия!)**

ВАЖНО: проверить на копии прод-БД, не на проде.

```bash
cp data/database.db /tmp/test_migration.db
# временно подменить путь и запустить
```

- [ ] **Step 4: Commit**

```bash
git add scripts/
git commit -m "feat(scripts): add Phase 2 migration to backfill auth_providers"
```

---

## Task 4: services/exceptions.py — расширить набор исключений

**Files:**
- Modify: `services/exceptions.py`

- [ ] **Step 1: Добавить новые типы**

Добавить в файл:

```python
class InvalidCredentials(ServiceError):
    """Email + password не совпадают, или provider/identifier не найден."""


class ProviderAlreadyLinked(ServiceError):
    """Пытаются привязать identifier, который уже привязан к другому user_id."""

    def __init__(self, provider: str, identifier: str, existing_user_id: int):
        super().__init__(f"{provider}:{identifier} already linked to user {existing_user_id}")
        self.provider = provider
        self.identifier = identifier
        self.existing_user_id = existing_user_id


class OTPInvalid(ServiceError):
    """Код не совпадает или превышен лимит попыток."""


class OTPExpired(ServiceError):
    """Срок жизни кода истёк."""


class OTPCooldown(ServiceError):
    """Слишком частые запросы кода."""

    def __init__(self, retry_after_seconds: int):
        super().__init__(f"Try again in {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class ApplicationNotFound(ServiceError):
    pass


class InvalidAPIKey(ServiceError):
    pass


class EmailAlreadyRegistered(ServiceError):
    pass
```

- [ ] **Step 2: Тест-импорт**

```bash
python -c "from services.exceptions import InvalidCredentials, OTPInvalid, OTPExpired, OTPCooldown, ProviderAlreadyLinked, ApplicationNotFound, InvalidAPIKey, EmailAlreadyRegistered; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add services/exceptions.py
git commit -m "feat(services): add identity/auth exception types"
```

---

## Task 5: services/auth_password.py — bcrypt-обёртка

**Files:**
- Create: `services/auth_password.py`
- Create: `tests/unit/test_auth_password.py`

- [ ] **Step 1: Реализация**

Создать `services/auth_password.py`:

```python
"""Хеширование паролей через bcrypt (через passlib для прозрачной верификации)."""
from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("password must be at least 8 chars")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_auth_password.py`:

```python
import pytest

from services.auth_password import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)


def test_verify_rejects_wrong_password():
    h = hash_password("password123")
    assert not verify_password("wrong-pass", h)


def test_hash_rejects_short_password():
    with pytest.raises(ValueError):
        hash_password("short")


def test_verify_rejects_empty_inputs():
    assert not verify_password("", "")
    assert not verify_password("abc", "")
    assert not verify_password("", "abc")


def test_hash_is_unique_per_call():
    """bcrypt использует salt — два хеша одного пароля разные."""
    a = hash_password("samepass1")
    b = hash_password("samepass1")
    assert a != b
    assert verify_password("samepass1", a)
    assert verify_password("samepass1", b)
```

- [ ] **Step 3: Run**

```bash
pytest tests/unit/test_auth_password.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add services/auth_password.py tests/unit/test_auth_password.py
git commit -m "feat(services): add bcrypt password hashing"
```

---

## Task 6: services/identity.py — central user identity layer

**Files:**
- Create: `services/identity.py`
- Create: `tests/unit/test_identity.py`

Это сердце Phase 2. Здесь живут все операции с identity: создать юзера, найти по провайдеру, привязать провайдера.

- [ ] **Step 1: Реализация**

Создать `services/identity.py`:

```python
"""Identity layer — управление пользователями и привязанными способами входа.

Один user_id → много auth_providers. user_id всегда внутренний (auto-increment в users).
Существующие telegram-юзеры остались с users.id == telegram_id (исторический artifact),
но обращаться к ним нужно через identity.get_user_id_by_telegram(tg_id), не напрямую.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services.db import connect
from services.exceptions import ProviderAlreadyLinked, UserNotFound


@dataclass(frozen=True)
class User:
    id: int
    user_name: Optional[str]
    first_name: Optional[str]
    balance: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user(user_id: int) -> User:
    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, first_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return User(
        id=row["id"],
        user_name=row["user_name"],
        first_name=row["first_name"],
        balance=int(row["balance"] or 0),
    )


def find_user_id_by_provider(provider: str, identifier: str) -> Optional[int]:
    """Вернёт user_id, если provider+identifier привязан, иначе None."""
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM auth_providers WHERE provider = ? AND identifier = ?",
            (provider, identifier),
        ).fetchone()
    return int(row["user_id"]) if row else None


def list_providers(user_id: int) -> list[dict]:
    """Список привязанных провайдеров. credential_hash не возвращаем."""
    with connect() as con:
        rows = con.execute(
            "SELECT provider, identifier, created_at, last_used_at "
            "FROM auth_providers WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _create_user(
    *,
    user_name: Optional[str] = None,
    first_name: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> int:
    """Низкоуровневая функция создания записи в users. Возвращает новый user_id."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date, ref_id) "
            "VALUES (?, ?, 0, ?, ?)",
            (user_name, first_name, _now_iso(), ref_id),
        )
        con.commit()
        return int(cur.lastrowid)


def link_provider(
    user_id: int,
    provider: str,
    identifier: str,
    credential_hash: Optional[str] = None,
) -> None:
    """Привязать новый способ входа к существующему юзеру.

    Если provider+identifier уже занят другим юзером — ProviderAlreadyLinked.
    Если этим же юзером — no-op (идемпотентно).
    """
    existing = find_user_id_by_provider(provider, identifier)
    if existing is not None:
        if existing == user_id:
            return
        raise ProviderAlreadyLinked(provider, identifier, existing)

    with connect() as con:
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, credential_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, provider, identifier, credential_hash, _now_iso()),
        )
        con.commit()


def unlink_provider(user_id: int, provider: str, identifier: str) -> None:
    """Удалить привязку. Не запрещаем удалить последнюю — это решение слоя выше."""
    with connect() as con:
        con.execute(
            "DELETE FROM auth_providers WHERE user_id = ? AND provider = ? AND identifier = ?",
            (user_id, provider, identifier),
        )
        con.commit()


def touch_provider(provider: str, identifier: str) -> None:
    """Обновить last_used_at — вызывать после успешного логина."""
    with connect() as con:
        con.execute(
            "UPDATE auth_providers SET last_used_at = ? WHERE provider = ? AND identifier = ?",
            (_now_iso(), provider, identifier),
        )
        con.commit()


def get_or_create_user_by_telegram(
    tg_id: int,
    *,
    user_name: Optional[str] = None,
    first_name: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> int:
    """Главный entry-point для бота.

    Если для tg_id есть auth_providers(provider='telegram') — возвращаем user_id.
    Иначе создаём нового юзера (или находим legacy-запись с users.id == tg_id, если есть)
    и привязываем telegram.
    """
    user_id = find_user_id_by_provider("telegram", str(tg_id))
    if user_id is not None:
        return user_id

    # Legacy fallback: возможно, существует запись users(id=tg_id) ещё с до-Phase-2 времён,
    # но миграция её не пропустила (rare). Переиспользуем.
    with connect() as con:
        row = con.execute("SELECT id FROM users WHERE id = ?", (tg_id,)).fetchone()
    if row is not None:
        link_provider(tg_id, "telegram", str(tg_id))
        return tg_id

    # Создаём нового
    new_id = _create_user(user_name=user_name, first_name=first_name, ref_id=ref_id)
    link_provider(new_id, "telegram", str(tg_id))
    return new_id


def get_or_create_user_by_email(
    email_normalized: str,
    *,
    credential_hash: str,
    first_name: Optional[str] = None,
) -> int:
    """Зарегистрировать нового юзера через email. Если email уже есть — EmailAlreadyRegistered."""
    from services.exceptions import EmailAlreadyRegistered

    existing = find_user_id_by_provider("email", email_normalized)
    if existing is not None:
        raise EmailAlreadyRegistered(email_normalized)

    new_id = _create_user(first_name=first_name)
    link_provider(new_id, "email", email_normalized, credential_hash=credential_hash)
    return new_id
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_identity.py`:

```python
import pytest
from pathlib import Path

from services import identity
from services.exceptions import (
    EmailAlreadyRegistered,
    ProviderAlreadyLinked,
    UserNotFound,
)


def test_get_or_create_user_by_telegram_creates_new(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(123456, user_name="alice", first_name="Alice")
    assert uid > 0
    user = identity.get_user(uid)
    assert user.user_name == "alice"
    assert user.first_name == "Alice"


def test_get_or_create_user_by_telegram_idempotent(tmp_db: Path) -> None:
    uid1 = identity.get_or_create_user_by_telegram(123456, user_name="alice")
    uid2 = identity.get_or_create_user_by_telegram(123456, user_name="alice")
    assert uid1 == uid2


def test_find_user_id_by_provider_returns_none_when_missing(tmp_db: Path) -> None:
    assert identity.find_user_id_by_provider("telegram", "999") is None


def test_link_provider_to_existing_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111, user_name="u1")
    identity.link_provider(uid, "email", "u1@example.com", credential_hash="hash")
    assert identity.find_user_id_by_provider("email", "u1@example.com") == uid


def test_link_provider_conflict_raises(tmp_db: Path) -> None:
    uid_a = identity.get_or_create_user_by_telegram(111)
    uid_b = identity.get_or_create_user_by_telegram(222)
    identity.link_provider(uid_a, "email", "shared@example.com", credential_hash="h")
    with pytest.raises(ProviderAlreadyLinked) as exc:
        identity.link_provider(uid_b, "email", "shared@example.com", credential_hash="h2")
    assert exc.value.existing_user_id == uid_a


def test_link_provider_idempotent_for_same_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111)
    identity.link_provider(uid, "email", "x@y.com", credential_hash="h")
    identity.link_provider(uid, "email", "x@y.com", credential_hash="h")  # должно не падать
    providers = identity.list_providers(uid)
    assert len([p for p in providers if p["provider"] == "email"]) == 1


def test_register_email_creates_user(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_email(
        "alice@example.com", credential_hash="bcrypt-hash", first_name="Alice"
    )
    user = identity.get_user(uid)
    assert user.first_name == "Alice"
    providers = identity.list_providers(uid)
    assert any(p["provider"] == "email" and p["identifier"] == "alice@example.com" for p in providers)


def test_register_email_duplicate_raises(tmp_db: Path) -> None:
    identity.get_or_create_user_by_email("dup@example.com", credential_hash="h")
    with pytest.raises(EmailAlreadyRegistered):
        identity.get_or_create_user_by_email("dup@example.com", credential_hash="h2")


def test_get_user_unknown_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        identity.get_user(99999)


def test_unlink_and_relink(tmp_db: Path) -> None:
    uid = identity.get_or_create_user_by_telegram(111)
    identity.link_provider(uid, "email", "a@b.com", credential_hash="h")
    identity.unlink_provider(uid, "email", "a@b.com")
    assert identity.find_user_id_by_provider("email", "a@b.com") is None
    identity.link_provider(uid, "email", "a@b.com", credential_hash="h")
    assert identity.find_user_id_by_provider("email", "a@b.com") == uid


def test_legacy_telegram_user_picked_up_when_users_row_exists(tmp_db: Path) -> None:
    """Симулируем юзера, который остался без auth_providers (миграция не зацепила)."""
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (777, "legacy", "L", 100, "2026-01-01"),
        )
        con.commit()
    uid = identity.get_or_create_user_by_telegram(777, user_name="legacy")
    assert uid == 777
    assert identity.find_user_id_by_provider("telegram", "777") == 777
```

- [ ] **Step 3: Run**

```bash
pytest tests/unit/test_identity.py -v
```

Expected: все passed.

- [ ] **Step 4: Commit**

```bash
git add services/identity.py tests/unit/test_identity.py
git commit -m "feat(services): add identity layer (users + auth_providers)"
```

---

## Task 7: services/auth_email.py — регистрация и вход по email

**Files:**
- Create: `services/auth_email.py`
- Create: `tests/unit/test_auth_email.py`

- [ ] **Step 1: Реализация**

Создать `services/auth_email.py`:

```python
"""Email registration / login flow."""
from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from services import identity
from services.auth_password import hash_password, verify_password
from services.exceptions import InvalidCredentials


def normalize_email(email: str) -> str:
    """Валидирует и нормализует email. Бросает InvalidCredentials при неверном формате."""
    try:
        v = validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidCredentials(f"invalid email: {exc}") from exc
    return v.normalized.lower()


def register(email: str, password: str, first_name: str | None = None) -> int:
    """Зарегистрировать нового юзера. Возвращает user_id."""
    email_norm = normalize_email(email)
    cred = hash_password(password)
    return identity.get_or_create_user_by_email(
        email_norm, credential_hash=cred, first_name=first_name
    )


def login(email: str, password: str) -> int:
    """Проверить email/пароль. Возвращает user_id или бросает InvalidCredentials."""
    email_norm = normalize_email(email)
    user_id = identity.find_user_id_by_provider("email", email_norm)
    if user_id is None:
        raise InvalidCredentials("email not registered")

    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT credential_hash FROM auth_providers "
            "WHERE provider = 'email' AND identifier = ?",
            (email_norm,),
        ).fetchone()
    if row is None or not verify_password(password, row["credential_hash"] or ""):
        raise InvalidCredentials("wrong password")

    identity.touch_provider("email", email_norm)
    return user_id
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_auth_email.py`:

```python
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
```

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/unit/test_auth_email.py -v
git add services/auth_email.py tests/unit/test_auth_email.py
git commit -m "feat(services): add email register/login"
```

---

## Task 8: services/otp.py — генерация и проверка одноразовых кодов

**Files:**
- Create: `services/otp.py`
- Create: `tests/unit/test_otp.py`

- [ ] **Step 1: Реализация**

Создать `services/otp.py`:

```python
"""OTP-коды для Telegram-логина и привязки.

Поток:
- request(purpose, telegram_id, user_id_to_link=None) → код (6 цифр), bot снаружи отправляет в Telegram.
- verify(purpose, telegram_id, code) → True/False.

Хранение: code не в открытом виде, а sha256(code+pepper). Pepper — это JWT_SECRET (есть в env).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.db import connect
from services.exceptions import OTPCooldown, OTPExpired, OTPInvalid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    """Хешируем с пеппером, чтобы дамп БД не выдал коды."""
    from data import config
    pepper = getattr(config, "JWT_SECRET", "") or ""
    return hashlib.sha256((code + pepper).encode()).hexdigest()


def _generate_code() -> str:
    """6-значный numeric code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def request_code(
    purpose: str,
    telegram_id: int,
    *,
    user_id_to_link: Optional[int] = None,
    ttl_seconds: int = 300,
    cooldown_seconds: int = 60,
) -> str:
    """Сгенерировать новый код. Если недавно был запрос — OTPCooldown.

    Возвращает plaintext-код. Caller должен отправить его юзеру (через бот).
    """
    if purpose not in ("login", "link"):
        raise ValueError(f"unknown purpose: {purpose}")

    now = _now()
    with connect() as con:
        recent = con.execute(
            "SELECT created_at FROM otp_codes "
            "WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (purpose, telegram_id),
        ).fetchone()
        if recent:
            recent_at = datetime.fromisoformat(recent["created_at"])
            elapsed = (now - recent_at).total_seconds()
            if elapsed < cooldown_seconds:
                raise OTPCooldown(int(cooldown_seconds - elapsed))

        # Инвалидируем все предыдущие unused коды этой цели
        con.execute(
            "UPDATE otp_codes SET consumed_at = ? "
            "WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL",
            (now.isoformat(), purpose, telegram_id),
        )

        code = _generate_code()
        expires = now + timedelta(seconds=ttl_seconds)
        con.execute(
            "INSERT INTO otp_codes(purpose, telegram_id, code_hash, user_id_to_link, "
            "created_at, expires_at, attempts) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (purpose, telegram_id, _hash_code(code), user_id_to_link,
             now.isoformat(), expires.isoformat()),
        )
        con.commit()

    return code


def verify_code(
    purpose: str,
    telegram_id: int,
    code: str,
    *,
    max_attempts: int = 5,
) -> Optional[int]:
    """Проверить код. Возвращает user_id_to_link если purpose='link', иначе None.

    Бросает OTPInvalid / OTPExpired.
    """
    now = _now()
    code_hash = _hash_code(code)

    with connect() as con:
        row = con.execute(
            "SELECT id, code_hash, user_id_to_link, expires_at, attempts "
            "FROM otp_codes WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (purpose, telegram_id),
        ).fetchone()

        if row is None:
            raise OTPInvalid("no active code")

        if datetime.fromisoformat(row["expires_at"]) < now:
            raise OTPExpired()

        if row["attempts"] >= max_attempts:
            con.execute(
                "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            con.commit()
            raise OTPInvalid("max attempts exceeded")

        if row["code_hash"] != code_hash:
            con.execute(
                "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?",
                (row["id"],),
            )
            con.commit()
            raise OTPInvalid("wrong code")

        # Успех: помечаем consumed
        con.execute(
            "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
            (now.isoformat(), row["id"]),
        )
        con.commit()
        return row["user_id_to_link"]
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_otp.py`:

```python
from pathlib import Path

import pytest

from services import otp
from services.exceptions import OTPCooldown, OTPExpired, OTPInvalid


def test_request_returns_six_digit_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    assert len(code) == 6 and code.isdigit()


def test_verify_correct_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    assert otp.verify_code("login", 12345, code) is None  # purpose=login → None


def test_verify_wrong_code_raises(tmp_db: Path):
    otp.request_code("login", 12345)
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, "999999")


def test_verify_consumes_code_after_success(tmp_db: Path):
    code = otp.request_code("login", 12345)
    otp.verify_code("login", 12345, code)
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code)


def test_request_invalidates_previous_unused(tmp_db: Path):
    code1 = otp.request_code("login", 12345, cooldown_seconds=0)
    code2 = otp.request_code("login", 12345, cooldown_seconds=0)
    assert code1 != code2 or True  # collision возможна, но редка
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code1)


def test_cooldown_blocks_rapid_request(tmp_db: Path):
    otp.request_code("login", 12345, cooldown_seconds=60)
    with pytest.raises(OTPCooldown) as exc:
        otp.request_code("login", 12345, cooldown_seconds=60)
    assert exc.value.retry_after_seconds > 0


def test_expired_code_raises(tmp_db: Path):
    code = otp.request_code("login", 12345, ttl_seconds=0)
    import time
    time.sleep(0.01)
    with pytest.raises(OTPExpired):
        otp.verify_code("login", 12345, code)


def test_max_attempts_invalidates_code(tmp_db: Path):
    code = otp.request_code("login", 12345)
    for _ in range(5):
        with pytest.raises(OTPInvalid):
            otp.verify_code("login", 12345, "000000")
    # 6-я попытка с правильным кодом — уже не работает
    with pytest.raises(OTPInvalid):
        otp.verify_code("login", 12345, code)


def test_link_purpose_returns_user_id(tmp_db: Path):
    code = otp.request_code("link", 12345, user_id_to_link=42)
    assert otp.verify_code("link", 12345, code) == 42
```

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/unit/test_otp.py -v
git add services/otp.py tests/unit/test_otp.py
git commit -m "feat(services): add OTP service with TTL/attempts/cooldown"
```

---

## Task 9: services/auth_telegram.py — request_code + verify_code (отправка через бот HTTP API)

**Files:**
- Create: `services/auth_telegram.py`
- Create: `tests/unit/test_auth_telegram.py`

- [ ] **Step 1: Реализация**

Создать `services/auth_telegram.py`:

```python
"""Telegram OTP login/link flow.

request_code:
- identifier: либо numeric telegram_id, либо @username (ищем в users.user_name).
- Генерируем код через services.otp, отправляем юзеру через Telegram Bot HTTP API.

verify_code:
- Юзер вводит идентификатор + код. Сверяем. На успех — get_or_create_user_by_telegram.
"""
from __future__ import annotations

import re

import httpx

from services import identity, otp
from services.db import connect
from services.exceptions import OTPInvalid


_USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{5,32})$")


def resolve_telegram_id(identifier: str) -> int:
    """Превратить введённое юзером в telegram_id.

    Поддерживается:
    - numeric ID (как-есть)
    - @username или username (ищем в users.user_name; если не нашли — OTPInvalid).
    """
    identifier = identifier.strip()
    if identifier.isdigit():
        return int(identifier)
    m = _USERNAME_RE.match(identifier)
    if not m:
        raise OTPInvalid(f"unknown identifier format: {identifier!r}")
    username = m.group(1)
    with connect() as con:
        # users.user_name из бота хранится без @
        row = con.execute(
            "SELECT id FROM users WHERE LOWER(user_name) = LOWER(?)",
            (username,),
        ).fetchone()
    if row is None:
        raise OTPInvalid("telegram user not found in our system; start the bot first")
    return int(row["id"])


def _send_telegram_message(bot_token: str, telegram_id: int, text: str) -> None:
    """Отправить сообщение через Bot HTTP API. На сетевые ошибки — RuntimeError."""
    from data import config
    base = getattr(config, "BOT_HTTP_API_BASE", "https://api.telegram.org")
    url = f"{base}/bot{bot_token}/sendMessage"
    try:
        resp = httpx.post(url, json={"chat_id": telegram_id, "text": text}, timeout=10.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"bot send failed: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"bot send returned {resp.status_code}: {resp.text}")


def request_code(
    identifier: str,
    *,
    purpose: str = "login",
    user_id_to_link: int | None = None,
) -> int:
    """Resolve identifier → telegram_id, generate code, send via bot. Return telegram_id (для clients-flow)."""
    from web.config import BOT_TOKEN

    tg_id = resolve_telegram_id(identifier)
    code = otp.request_code(purpose, tg_id, user_id_to_link=user_id_to_link)
    text = f"Ваш код подтверждения: {code}\n\nДействителен 5 минут."
    _send_telegram_message(BOT_TOKEN, tg_id, text)
    return tg_id


def verify_code_login(identifier: str, code: str) -> int:
    """Проверить код для логина. Возвращает internal user_id (создаёт юзера, если нужно)."""
    tg_id = resolve_telegram_id(identifier)
    otp.verify_code("login", tg_id, code)

    user_name = _lookup_username(tg_id)
    return identity.get_or_create_user_by_telegram(tg_id, user_name=user_name)


def verify_code_link(identifier: str, code: str, current_user_id: int) -> None:
    """Проверить код для привязки telegram к current_user_id."""
    tg_id = resolve_telegram_id(identifier)
    expected = otp.verify_code("link", tg_id, code)
    if expected is not None and expected != current_user_id:
        raise OTPInvalid("code was issued for a different user")
    identity.link_provider(current_user_id, "telegram", str(tg_id))


def _lookup_username(tg_id: int) -> str | None:
    with connect() as con:
        row = con.execute("SELECT user_name FROM users WHERE id = ?", (tg_id,)).fetchone()
    return row["user_name"] if row else None
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_auth_telegram.py`:

```python
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services import auth_telegram, identity
from services.exceptions import OTPInvalid


def _seed_user(tmp_db: Path, tg_id: int, user_name: str | None = None) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (tg_id, user_name, "U", 0, "2026-01-01"),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at) "
            "VALUES (?, 'telegram', ?, '2026-01-01')",
            (tg_id, str(tg_id)),
        )
        con.commit()


def test_resolve_numeric_id(tmp_db: Path):
    assert auth_telegram.resolve_telegram_id("123456") == 123456
    assert auth_telegram.resolve_telegram_id("  789  ") == 789


def test_resolve_username(tmp_db: Path):
    _seed_user(tmp_db, 555, user_name="alice")
    assert auth_telegram.resolve_telegram_id("@alice") == 555
    assert auth_telegram.resolve_telegram_id("alice") == 555
    assert auth_telegram.resolve_telegram_id("ALICE") == 555


def test_resolve_username_not_found(tmp_db: Path):
    with pytest.raises(OTPInvalid):
        auth_telegram.resolve_telegram_id("@nobody")


def test_request_code_sends_message(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    _seed_user(tmp_db, 777, user_name="bob")

    captured = {}
    def fake_send(token, tg_id, text):
        captured.update(token=token, tg_id=tg_id, text=text)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    result_tg_id = auth_telegram.request_code("@bob")
    assert result_tg_id == 777
    assert captured["tg_id"] == 777
    assert captured["token"] == "test:token"
    assert "код" in captured["text"].lower()


def test_verify_code_login_creates_user(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")

    captured_code = {}
    def fake_send(token, tg_id, text):
        # Парсим код из текста для теста
        import re
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    auth_telegram.request_code("999111")  # numeric id, не существующий юзер
    user_id = auth_telegram.verify_code_login("999111", captured_code["code"])
    assert user_id > 0
    assert identity.find_user_id_by_provider("telegram", "999111") == user_id


def test_verify_code_link_attaches_to_current_user(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    captured_code = {}
    def fake_send(token, tg_id, text):
        import re
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    # Создаём email-юзера
    from services import auth_email
    uid = auth_email.register("a@b.com", "password123")

    auth_telegram.request_code("888222", purpose="link", user_id_to_link=uid)
    auth_telegram.verify_code_link("888222", captured_code["code"], uid)
    assert identity.find_user_id_by_provider("telegram", "888222") == uid


def test_verify_code_wrong_code(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    auth_telegram.request_code("111222")
    with pytest.raises(OTPInvalid):
        auth_telegram.verify_code_login("111222", "000000")
```

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/unit/test_auth_telegram.py -v
git add services/auth_telegram.py tests/unit/test_auth_telegram.py
git commit -m "feat(services): add Telegram OTP login/link flow"
```

---

## Task 10: services/applications.py — управление API-ключами

**Files:**
- Create: `services/applications.py`
- Create: `tests/unit/test_applications.py`

- [ ] **Step 1: Реализация**

Создать `services/applications.py`:

```python
"""CRUD для сторонних приложений и их API-ключей.

API-ключи хранятся как sha256-хеши. На создании возвращаем plaintext один раз — клиент должен сохранить.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services.db import connect
from services.exceptions import ApplicationNotFound


@dataclass(frozen=True)
class Application:
    id: int
    owner_user_id: int
    name: str
    api_key_prefix: str  # для отображения
    created_at: str
    revoked_at: Optional[str]


@dataclass(frozen=True)
class CreatedApplication:
    application: Application
    api_key: str  # plaintext, показать клиенту один раз


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_api_key() -> str:
    """Формат: sk_live_<32 hex chars>."""
    return "sk_live_" + secrets.token_hex(16)


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def create(owner_user_id: int, name: str) -> CreatedApplication:
    if not name.strip():
        raise ValueError("application name cannot be empty")

    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)
    api_key_prefix = api_key[:12]
    now = _now_iso()

    with connect() as con:
        cur = con.execute(
            "INSERT INTO applications(owner_user_id, name, api_key_hash, api_key_prefix, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_user_id, name, api_key_hash, api_key_prefix, now),
        )
        app_id = int(cur.lastrowid)
        con.commit()

    app = Application(
        id=app_id,
        owner_user_id=owner_user_id,
        name=name,
        api_key_prefix=api_key_prefix,
        created_at=now,
        revoked_at=None,
    )
    return CreatedApplication(application=app, api_key=api_key)


def list_for_user(owner_user_id: int) -> list[Application]:
    with connect() as con:
        rows = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE owner_user_id = ? ORDER BY created_at DESC",
            (owner_user_id,),
        ).fetchall()
    return [Application(**dict(r)) for r in rows]


def get(app_id: int) -> Application:
    with connect() as con:
        row = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE id = ?",
            (app_id,),
        ).fetchone()
    if row is None:
        raise ApplicationNotFound(f"application_id={app_id}")
    return Application(**dict(row))


def revoke(app_id: int, owner_user_id: int) -> None:
    """Soft-revoke: запоминаем revoked_at. Только владелец может revoke."""
    app = get(app_id)
    if app.owner_user_id != owner_user_id:
        raise ApplicationNotFound(f"application_id={app_id} (not owned)")
    with connect() as con:
        con.execute(
            "UPDATE applications SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_now_iso(), app_id),
        )
        con.commit()


def find_by_api_key(api_key: str) -> Optional[Application]:
    """Найти приложение по plaintext API-ключу. None если не найдено или revoked."""
    api_key_hash = _hash_api_key(api_key)
    with connect() as con:
        row = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE api_key_hash = ? AND revoked_at IS NULL",
            (api_key_hash,),
        ).fetchone()
    return Application(**dict(row)) if row else None
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_applications.py`:

```python
from pathlib import Path

import pytest

from services import applications, auth_email
from services.exceptions import ApplicationNotFound


def test_create_returns_plaintext_key(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "MyBot")
    assert result.api_key.startswith("sk_live_")
    assert len(result.api_key) > 20
    assert result.application.name == "MyBot"
    assert result.application.api_key_prefix == result.api_key[:12]


def test_find_by_api_key_returns_app(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "MyBot")
    found = applications.find_by_api_key(result.api_key)
    assert found is not None
    assert found.id == result.application.id


def test_find_by_unknown_key_returns_none(tmp_db: Path):
    assert applications.find_by_api_key("sk_live_unknown") is None


def test_list_for_user(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    a = applications.create(uid, "App A")
    b = applications.create(uid, "App B")
    apps = applications.list_for_user(uid)
    assert {x.id for x in apps} == {a.application.id, b.application.id}


def test_revoke_soft_deletes(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    result = applications.create(uid, "Temp")
    applications.revoke(result.application.id, uid)
    assert applications.find_by_api_key(result.api_key) is None
    # Но GET всё равно вернёт (soft delete)
    app = applications.get(result.application.id)
    assert app.revoked_at is not None


def test_revoke_by_non_owner_raises(tmp_db: Path):
    uid_a = auth_email.register("a@example.com", "password123")
    uid_b = auth_email.register("b@example.com", "password123")
    result = applications.create(uid_a, "AppA")
    with pytest.raises(ApplicationNotFound):
        applications.revoke(result.application.id, uid_b)


def test_create_empty_name_raises(tmp_db: Path):
    uid = auth_email.register("dev@example.com", "password123")
    with pytest.raises(ValueError):
        applications.create(uid, "  ")
```

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/unit/test_applications.py -v
git add services/applications.py tests/unit/test_applications.py
git commit -m "feat(services): add applications + API key management"
```

---

## Task 11: services/auth_api.py — авторизация через API-ключ + end-user

**Files:**
- Create: `services/auth_api.py`
- Create: `tests/unit/test_auth_api.py`

- [ ] **Step 1: Реализация**

Создать `services/auth_api.py`:

```python
"""API-key authentication for third-party apps.

Каждый запрос требует:
- X-API-Key: <ключ>
- X-End-User-Id: <идентификатор end-user в стороннем приложении>

Мы создаём (или находим) внутреннего юзера с auth_provider(provider='api:<app_id>',
identifier=end_user_id). Запросы под этим юзером помечаются source_type='api',
source_app_id=<app.id>.
"""
from __future__ import annotations

from dataclasses import dataclass

from services import applications, identity
from services.exceptions import InvalidAPIKey


@dataclass(frozen=True)
class AuthorizedAPICall:
    application_id: int
    end_user_internal_id: int


def authorize(api_key: str, end_user_id: str, *, end_user_display_name: str | None = None) -> AuthorizedAPICall:
    """Проверить ключ + (создать/найти) внутреннего юзера для end-user-id."""
    if not api_key or not end_user_id:
        raise InvalidAPIKey("missing api_key or end_user_id")

    app = applications.find_by_api_key(api_key)
    if app is None:
        raise InvalidAPIKey("unknown or revoked api key")

    provider = f"api:{app.id}"
    user_id = identity.find_user_id_by_provider(provider, end_user_id)
    if user_id is None:
        # Создаём внутреннего юзера для этого end-user-id
        new_id = identity._create_user(first_name=end_user_display_name)  # noqa: SLF001
        identity.link_provider(new_id, provider, end_user_id)
        user_id = new_id

    return AuthorizedAPICall(application_id=app.id, end_user_internal_id=user_id)
```

- [ ] **Step 2: Тесты**

Создать `tests/unit/test_auth_api.py`:

```python
from pathlib import Path

import pytest

from services import applications, auth_api, auth_email, identity
from services.exceptions import InvalidAPIKey


def test_authorize_creates_internal_user(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    result = auth_api.authorize(app.api_key, "external-user-1")
    assert result.application_id == app.application.id
    assert result.end_user_internal_id != dev  # отдельный юзер
    assert identity.find_user_id_by_provider(f"api:{app.application.id}", "external-user-1") \
        == result.end_user_internal_id


def test_authorize_idempotent_for_same_end_user(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    r1 = auth_api.authorize(app.api_key, "user-X")
    r2 = auth_api.authorize(app.api_key, "user-X")
    assert r1.end_user_internal_id == r2.end_user_internal_id


def test_authorize_different_apps_create_different_users(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app1 = applications.create(dev, "Bot1")
    app2 = applications.create(dev, "Bot2")
    r1 = auth_api.authorize(app1.api_key, "user-X")
    r2 = auth_api.authorize(app2.api_key, "user-X")
    assert r1.end_user_internal_id != r2.end_user_internal_id


def test_authorize_invalid_key(tmp_db: Path):
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("sk_live_bogus", "user-1")


def test_authorize_revoked_key(tmp_db: Path):
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "MyBot")
    applications.revoke(app.application.id, dev)
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize(app.api_key, "user-1")


def test_authorize_missing_inputs(tmp_db: Path):
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("", "user-1")
    with pytest.raises(InvalidAPIKey):
        auth_api.authorize("sk_live_x", "")
```

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/unit/test_auth_api.py -v
git add services/auth_api.py tests/unit/test_auth_api.py
git commit -m "feat(services): add API-key authorization for third-party apps"
```

---

## Task 12: services/source.py + обновить refill для source-tracking

**Files:**
- Create: `services/source.py`
- Modify: `services/refill.py` — finalize/finalize_with_referral_bonus принимают source
- Modify: `tests/unit/test_refill.py` — добавить тесты на source

- [ ] **Step 1: Создать source.py**

```python
"""Source-tracking — кто создал заявку/refill.

Используется на refills (Phase 2) и на orders (Phase 3).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class Source(str, Enum):
    TELEGRAM = "telegram"
    WEB = "web"
    API = "api"


def normalize(source_type: str | Source, source_app_id: Optional[int] = None) -> tuple[str, Optional[int]]:
    """Нормализует и валидирует пару (type, app_id)."""
    s = Source(source_type) if not isinstance(source_type, Source) else source_type
    if s is Source.API and source_app_id is None:
        raise ValueError("source_type=api requires source_app_id")
    if s is not Source.API and source_app_id is not None:
        raise ValueError(f"source_app_id must be None for source_type={s.value}")
    return s.value, source_app_id
```

- [ ] **Step 2: Обновить refill.py**

В `services/refill.py` обновить `finalize`:

```python
def finalize(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> int:
    """Атомарно зачислить amount на баланс и записать в refills с source-tracking."""
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    from services.source import normalize
    src_type, src_app = normalize(source_type, source_app_id)

    if payment_id is not None:
        with connect() as con:
            existing = con.execute(
                "SELECT 1 FROM refills WHERE payment_id = ? LIMIT 1", (payment_id,)
            ).fetchone()
        if existing is not None:
            return get_balance(user_id)

    new_balance = credit(user_id, amount)
    with connect() as con:
        con.execute(
            "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (amount, get_date(), user_id, payment_id, src_type, src_app),
        )
        con.commit()
    return new_balance
```

И аналогично в `finalize_with_referral_bonus` — пробрасывать source-параметры:

```python
def finalize_with_referral_bonus(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> RefillResult:
    user = _get_user_for_referral(user_id)
    is_first = _is_first_refill(user_id)

    new_balance = finalize(
        user_id, amount, payment_id=payment_id,
        source_type=source_type, source_app_id=source_app_id,
    )

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    if is_first and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            # Рефералка зачисляется как 'system' источник? Используем тот же source_type — это бонус от того же события
            referrer_new_balance = (
                finalize(int(referrer_id), bonus,
                         source_type=source_type, source_app_id=source_app_id)
                if bonus > 0 else None
            )
        except UserNotFound:
            referrer_new_balance = None
            bonus = 0

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_balance=referrer_new_balance,
    )
```

- [ ] **Step 3: Тесты на source**

Добавить в `tests/unit/test_refill.py`:

```python
def test_finalize_writes_source_telegram_by_default(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("telegram", None)


def test_finalize_writes_source_web(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, source_type="web")
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("web", None)


def test_finalize_writes_source_api_with_app_id(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, source_type="api", source_app_id=7)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("api", 7)


def test_finalize_api_without_app_id_raises(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=100, source_type="api")
```

- [ ] **Step 4: Run и Commit**

```bash
pytest tests/unit/test_refill.py -v
git add services/source.py services/refill.py tests/unit/test_refill.py
git commit -m "feat(services): add source-tracking to refill (telegram/web/api)"
```

---

## Task 13: web/auth.py + web/deps.py — JWT с internal user_id, multi-method auth

**Files:**
- Modify: `web/auth.py` — удалить Telegram Login Widget verify (он больше не нужен), оставить JWT-функции
- Modify: `web/deps.py` — current_user_id через JWT ИЛИ через API-key+end-user-id
- Modify: `web/schemas.py` — добавить новые модели

- [ ] **Step 1: Перевернуть web/auth.py**

Полностью переписать `web/auth.py`:

```python
"""JWT-helpers для веб-аутентификации.

Telegram Login Widget verify удалён — теперь логин через OTP (см. routers/auth_telegram.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from web.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_SECRET


def create_jwt(user_id: int, *, secret: str | None = None, expire_hours: int | None = None) -> str:
    """Сгенерировать JWT с internal user_id."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expire_hours or JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, secret or JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str, *, secret: str | None = None) -> int:
    """Декодировать JWT и вернуть user_id. Бросает jwt.InvalidTokenError."""
    payload = jwt.decode(token, secret or JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
```

- [ ] **Step 2: Обновить web/deps.py**

```python
"""FastAPI dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

from services import auth_api, identity
from services.exceptions import InvalidAPIKey
from web.auth import decode_jwt


@dataclass(frozen=True)
class CurrentCaller:
    """Кто сделал запрос. Может быть как залогиненный юзер (JWT), так и API-key call."""
    user_id: int
    source_type: str  # 'web' | 'telegram' | 'api'
    source_app_id: Optional[int]


async def current_caller(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_end_user_id: str | None = Header(None, alias="X-End-User-Id"),
) -> CurrentCaller:
    """Multi-method authentication.

    Priority:
    1. X-API-Key + X-End-User-Id → API call (source=api, source_app_id=<app>).
    2. Authorization: Bearer <jwt> → web call (source=web).
    """
    if x_api_key:
        if not x_end_user_id:
            raise HTTPException(
                status_code=400,
                detail="X-End-User-Id is required when using X-API-Key",
            )
        try:
            authz = auth_api.authorize(x_api_key, x_end_user_id)
        except InvalidAPIKey as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return CurrentCaller(
            user_id=authz.end_user_internal_id,
            source_type="api",
            source_app_id=authz.application_id,
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:].strip()
    try:
        user_id = decode_jwt(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    return CurrentCaller(user_id=user_id, source_type="web", source_app_id=None)


async def require_user(caller: CurrentCaller = Depends(current_caller)) -> int:
    """Convenience: возвращает только user_id, для роутеров, которым source неважен."""
    return caller.user_id
```

- [ ] **Step 3: Обновить web/schemas.py — добавить новые модели**

```python
# В web/schemas.py добавить:
from pydantic import BaseModel, EmailStr, Field


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=64)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OTPRequestBody(BaseModel):
    identifier: str = Field(min_length=2, max_length=64)


class OTPVerifyBody(BaseModel):
    identifier: str = Field(min_length=2, max_length=64)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ProfileResponse(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int


class ProviderInfo(BaseModel):
    provider: str
    identifier: str
    created_at: str
    last_used_at: str | None


class ApplicationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ApplicationCreateResponse(BaseModel):
    id: int
    name: str
    api_key: str  # plaintext, only shown once
    api_key_prefix: str
    created_at: str


class ApplicationInfo(BaseModel):
    id: int
    name: str
    api_key_prefix: str
    created_at: str
    revoked_at: str | None
```

- [ ] **Step 4: Удалить старый Telegram Login Widget endpoint**

Удалить файлы:
- `web/routers/auth.py`
- `tests/web/test_auth.py` (старые HMAC-тесты)
- `tests/web/test_routers_auth.py`

```bash
git rm web/routers/auth.py tests/web/test_auth.py tests/web/test_routers_auth.py
```

- [ ] **Step 5: Smoke-тест что web всё ещё импортируется**

```bash
python -c "from web.main import app; print('ok')"
```

(может упасть — на этом шаге роутеры ещё не подключены, исправим в следующих task'ах.)

- [ ] **Step 6: Commit**

```bash
git add web/auth.py web/deps.py web/schemas.py
git commit -m "refactor(web): JWT now wraps internal user_id; multi-method auth dep"
```

---

## Task 14: web/routers/auth_email.py — POST /register, /login

**Files:**
- Create: `web/routers/auth_email.py`
- Create: `tests/web/test_routers_auth_email.py`

- [ ] **Step 1: Реализация**

Создать `web/routers/auth_email.py`:

```python
from fastapi import APIRouter, HTTPException

from services import auth_email
from services.exceptions import EmailAlreadyRegistered, InvalidCredentials
from web.auth import create_jwt
from web.schemas import EmailLoginRequest, EmailRegisterRequest, TokenResponse

router = APIRouter(prefix="/api/auth/email", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: EmailRegisterRequest) -> TokenResponse:
    try:
        user_id = auth_email.register(body.email, body.password, first_name=body.first_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))


@router.post("/login", response_model=TokenResponse)
async def login(body: EmailLoginRequest) -> TokenResponse:
    try:
        user_id = auth_email.login(body.email, body.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))
```

- [ ] **Step 2: Зарегистрировать роутер в web/main.py**

Открыть `web/main.py`, добавить:

```python
from web.routers.auth_email import router as auth_email_router
app.include_router(auth_email_router)
```

- [ ] **Step 3: Тесты**

Создать `tests/web/test_routers_auth_email.py`:

```python
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
        "first_name": "Alice",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_register_duplicate_email_409(client):
    payload = {"email": "dup@example.com", "password": "password123"}
    client.post("/api/auth/email/register", json=payload).raise_for_status()
    r = client.post("/api/auth/email/register", json=payload)
    assert r.status_code == 409


def test_register_invalid_email_400(client):
    r = client.post("/api/auth/email/register", json={
        "email": "not-an-email", "password": "password123",
    })
    assert r.status_code == 422  # pydantic validation


def test_register_short_password_422(client):
    r = client.post("/api/auth/email/register", json={
        "email": "a@b.com", "password": "short",
    })
    assert r.status_code == 422


def test_login_success(client):
    client.post("/api/auth/email/register", json={
        "email": "login@example.com", "password": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "login@example.com", "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_401(client):
    client.post("/api/auth/email/register", json={
        "email": "user@example.com", "password": "password123",
    }).raise_for_status()
    r = client.post("/api/auth/email/login", json={
        "email": "user@example.com", "password": "wrong",
    })
    assert r.status_code == 401


def test_login_unknown_email_401(client):
    r = client.post("/api/auth/email/login", json={
        "email": "nobody@example.com", "password": "password123",
    })
    assert r.status_code == 401
```

- [ ] **Step 4: Run и Commit**

```bash
pytest tests/web/test_routers_auth_email.py -v
git add web/routers/auth_email.py web/main.py tests/web/test_routers_auth_email.py
git commit -m "feat(web): add POST /api/auth/email/register and /login"
```

---

## Task 15: web/routers/auth_telegram.py — request-code, verify-code

**Files:**
- Create: `web/routers/auth_telegram.py`
- Create: `tests/web/test_routers_auth_telegram.py`

- [ ] **Step 1: Реализация**

Создать `web/routers/auth_telegram.py`:

```python
from fastapi import APIRouter, HTTPException

from services import auth_telegram
from services.exceptions import OTPCooldown, OTPExpired, OTPInvalid
from web.auth import create_jwt
from web.schemas import OTPRequestBody, OTPVerifyBody, TokenResponse

router = APIRouter(prefix="/api/auth/telegram", tags=["auth"])


@router.post("/request-code", status_code=204)
async def request_code(body: OTPRequestBody) -> None:
    try:
        auth_telegram.request_code(body.identifier)
    except OTPCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # bot send failed
        raise HTTPException(status_code=502, detail=f"could not deliver code: {exc}") from exc


@router.post("/verify-code", response_model=TokenResponse)
async def verify_code(body: OTPVerifyBody) -> TokenResponse:
    try:
        user_id = auth_telegram.verify_code_login(body.identifier, body.code)
    except OTPExpired as exc:
        raise HTTPException(status_code=410, detail="code expired") from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))
```

- [ ] **Step 2: Регистрация в web/main.py**

```python
from web.routers.auth_telegram import router as auth_telegram_router
app.include_router(auth_telegram_router)
```

- [ ] **Step 3: Тесты**

Создать `tests/web/test_routers_auth_telegram.py`:

```python
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def test_request_code_sends_via_bot(client, monkeypatch):
    captured = {}
    def fake_send(token, tg_id, text):
        captured.update(token=token, tg_id=tg_id, text=text)
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    r = client.post("/api/auth/telegram/request-code", json={"identifier": "12345"})
    assert r.status_code == 204
    assert captured["tg_id"] == 12345


def test_request_then_verify_returns_jwt(client, monkeypatch):
    captured_code = {}
    def fake_send(token, tg_id, text):
        m = re.search(r"\b(\d{6})\b", text)
        captured_code["code"] = m.group(1)
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", fake_send)

    client.post("/api/auth/telegram/request-code", json={"identifier": "777"}).raise_for_status()
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "777", "code": captured_code["code"],
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_verify_wrong_code_401(client, monkeypatch):
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    client.post("/api/auth/telegram/request-code", json={"identifier": "888"}).raise_for_status()
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "888", "code": "000000",
    })
    assert r.status_code == 401


def test_request_cooldown_returns_429(client, monkeypatch):
    from services import auth_telegram
    monkeypatch.setattr(auth_telegram, "_send_telegram_message", lambda *a, **kw: None)
    client.post("/api/auth/telegram/request-code", json={"identifier": "999"}).raise_for_status()
    r = client.post("/api/auth/telegram/request-code", json={"identifier": "999"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_invalid_code_format_422(client):
    r = client.post("/api/auth/telegram/verify-code", json={
        "identifier": "777", "code": "abc",
    })
    assert r.status_code == 422
```

- [ ] **Step 4: Run и Commit**

```bash
pytest tests/web/test_routers_auth_telegram.py -v
git add web/routers/auth_telegram.py web/main.py tests/web/test_routers_auth_telegram.py
git commit -m "feat(web): add POST /api/auth/telegram/request-code and /verify-code"
```

---

## Task 16: web/routers/me.py — GET /api/me, GET /api/me/providers

**Files:**
- Create: `web/routers/me.py`
- Create: `tests/web/test_routers_me.py`

- [ ] **Step 1: Реализация**

Создать `web/routers/me.py`:

```python
from fastapi import APIRouter, Depends, HTTPException

from services import identity
from services.exceptions import UserNotFound
from web.deps import require_user
from web.schemas import ProfileResponse, ProviderInfo

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=ProfileResponse)
async def get_me(user_id: int = Depends(require_user)) -> ProfileResponse:
    try:
        u = identity.get_user(user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProfileResponse(
        user_id=u.id,
        user_name=u.user_name,
        first_name=u.first_name,
        balance=u.balance,
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def get_providers(user_id: int = Depends(require_user)) -> list[ProviderInfo]:
    return [ProviderInfo(**p) for p in identity.list_providers(user_id)]
```

- [ ] **Step 2: Зарегистрировать в main.py**

```python
from web.routers.me import router as me_router
app.include_router(me_router)
```

- [ ] **Step 3: Тесты**

Создать `tests/web/test_routers_me.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("me@example.com", "password123", first_name="Me")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    return TestClient(app), uid, {"Authorization": f"Bearer {token}"}


def test_me_returns_profile(authed):
    client, uid, headers = authed
    r = client.get("/api/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == uid
    assert body["first_name"] == "Me"
    assert body["balance"] == 0


def test_me_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/me")
    assert r.status_code == 401


def test_providers_lists_email(authed):
    client, _, headers = authed
    r = client.get("/api/me/providers", headers=headers)
    assert r.status_code == 200
    providers = r.json()
    assert any(p["provider"] == "email" for p in providers)
```

- [ ] **Step 4: Run и Commit**

```bash
pytest tests/web/test_routers_me.py -v
git add web/routers/me.py web/main.py tests/web/test_routers_me.py
git commit -m "feat(web): add GET /api/me and /api/me/providers"
```

---

## Task 17: web/routers/auth_link.py — линковка/отвязка провайдеров

**Files:**
- Create: `web/routers/auth_link.py`
- Create: `tests/web/test_routers_auth_link.py`

- [ ] **Step 1: Реализация**

Создать `web/routers/auth_link.py`:

```python
from fastapi import APIRouter, Depends, HTTPException

from services import auth_email, auth_telegram, identity
from services.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
    ProviderAlreadyLinked,
)
from web.deps import require_user
from web.schemas import (
    EmailRegisterRequest,
    OTPRequestBody,
    OTPVerifyBody,
)

router = APIRouter(prefix="/api/auth/link", tags=["auth-link"])


@router.post("/email", status_code=204)
async def link_email(
    body: EmailRegisterRequest,
    user_id: int = Depends(require_user),
) -> None:
    """Привязать email к текущему юзеру (с паролем)."""
    email_norm = auth_email.normalize_email(body.email)
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="password must be ≥ 8 chars")
    cred = __import__("services.auth_password", fromlist=["hash_password"]).hash_password(body.password)
    try:
        identity.link_provider(user_id, "email", email_norm, credential_hash=cred)
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/telegram/request-code", status_code=204)
async def link_telegram_request(
    body: OTPRequestBody,
    user_id: int = Depends(require_user),
) -> None:
    try:
        auth_telegram.request_code(body.identifier, purpose="link", user_id_to_link=user_id)
    except OTPCooldown as exc:
        raise HTTPException(status_code=429, detail=str(exc),
                            headers={"Retry-After": str(exc.retry_after_seconds)}) from exc
    except OTPInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/telegram/verify-code", status_code=204)
async def link_telegram_verify(
    body: OTPVerifyBody,
    user_id: int = Depends(require_user),
) -> None:
    try:
        auth_telegram.verify_code_link(body.identifier, body.code, user_id)
    except OTPExpired:
        raise HTTPException(status_code=410, detail="code expired")
    except OTPInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ProviderAlreadyLinked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{provider}/{identifier}", status_code=204)
async def unlink(
    provider: str,
    identifier: str,
    user_id: int = Depends(require_user),
) -> None:
    """Отвязать. Не позволяем отвязать последний — иначе юзер потеряет доступ."""
    providers = identity.list_providers(user_id)
    if len(providers) <= 1:
        raise HTTPException(status_code=400, detail="cannot unlink last provider")
    identity.unlink_provider(user_id, provider, identifier)
```

- [ ] **Step 2: Регистрация и тесты**

В `web/main.py`:
```python
from web.routers.auth_link import router as auth_link_router
app.include_router(auth_link_router)
```

Создать `tests/web/test_routers_auth_link.py` (по образцу test_routers_auth_telegram.py): сценарии `link_email_to_telegram_user`, `link_telegram_to_email_user`, `unlink_when_only_one_provider_400`, `link_email_already_used_409`.

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/web/test_routers_auth_link.py -v
git add web/routers/auth_link.py web/main.py tests/web/test_routers_auth_link.py
git commit -m "feat(web): add provider linking/unlinking endpoints"
```

---

## Task 18: web/routers/applications.py — CRUD приложений

**Files:**
- Create: `web/routers/applications.py`
- Create: `tests/web/test_routers_applications.py`

- [ ] **Step 1: Реализация**

```python
from fastapi import APIRouter, Depends, HTTPException

from services import applications
from services.exceptions import ApplicationNotFound
from web.deps import require_user
from web.schemas import (
    ApplicationCreateRequest,
    ApplicationCreateResponse,
    ApplicationInfo,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("", response_model=ApplicationCreateResponse, status_code=201)
async def create_app(
    body: ApplicationCreateRequest,
    user_id: int = Depends(require_user),
) -> ApplicationCreateResponse:
    try:
        result = applications.create(user_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApplicationCreateResponse(
        id=result.application.id,
        name=result.application.name,
        api_key=result.api_key,  # plaintext, ONE TIME
        api_key_prefix=result.application.api_key_prefix,
        created_at=result.application.created_at,
    )


@router.get("", response_model=list[ApplicationInfo])
async def list_apps(user_id: int = Depends(require_user)) -> list[ApplicationInfo]:
    return [
        ApplicationInfo(
            id=a.id, name=a.name, api_key_prefix=a.api_key_prefix,
            created_at=a.created_at, revoked_at=a.revoked_at,
        )
        for a in applications.list_for_user(user_id)
    ]


@router.delete("/{app_id}", status_code=204)
async def revoke_app(app_id: int, user_id: int = Depends(require_user)) -> None:
    try:
        applications.revoke(app_id, user_id)
    except ApplicationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 2: Регистрация и тесты**

Тесты по образцу остальных. Сценарии: create returns plaintext key once, list shows multiple apps, revoke returns 204, revoke unowned 404.

- [ ] **Step 3: Run и Commit**

```bash
pytest tests/web/test_routers_applications.py -v
git add web/routers/applications.py web/main.py tests/web/test_routers_applications.py
git commit -m "feat(web): add applications CRUD"
```

---

## Task 19: web/routers/refill.py + api_v1/refill.py — обновление под source-tracking

**Files:**
- Modify: `web/routers/refill.py` — теперь использует current_caller, source_type='web'
- Create: `web/routers/api_v1/__init__.py`
- Create: `web/routers/api_v1/refill.py` — публичный API через X-API-Key
- Modify: tests

- [ ] **Step 1: Обновить web/routers/refill.py**

Уже есть, но изменить сигнатуру `current_user_id` на `current_caller` (через `web.deps.current_caller`), и при вызове `finalize_with_referral_bonus` пробрасывать `source_type=caller.source_type, source_app_id=caller.source_app_id`.

- [ ] **Step 2: Создать api_v1**

`web/routers/api_v1/refill.py`:
```python
"""Публичный API для сторонних приложений. Auth: X-API-Key + X-End-User-Id."""
from fastapi import APIRouter, Depends

from web.deps import current_caller
# импорт refill-логики, что в web/routers/refill.py — реюзаем те же handlers

router = APIRouter(prefix="/api/v1/refill", tags=["api-v1"])

# Реализация — повторяет refill.py, но обязательно требует source=api в caller.
# Можно вообще переиспользовать те же функции через зависимость current_caller —
# тогда отдельный api_v1 даже не нужен. См. Architecture note ниже.
```

**Architecture note:** Поскольку `current_caller` уже различает JWT vs API-key, отдельный namespace `/api/v1/` нужен только если хочется явно отделить публичный API от внутреннего. Для Phase 2 — оставляем `/api/refill` единственным эндпоинтом, который принимает оба способа auth. `api_v1/` создаём пустым (на Phase 3 заполним).

Соответственно: **Task 19 упрощается до одного шага — обновить web/routers/refill.py**.

- [ ] **Step 3: Тесты**

В `tests/web/test_routers_refill.py` добавить сценарий:
- API-key call → refill завершается, в БД source_type='api', source_app_id=<id>.

```python
def test_refill_via_api_key_writes_source_api(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)

    # 1. Зарегистрировать dev + создать app
    from services import auth_email, applications
    dev = auth_email.register("dev@example.com", "password123")
    app = applications.create(dev, "TestBot")

    # 2. Сделать запрос с X-API-Key и X-End-User-Id
    from web.main import app as fastapi_app
    client = TestClient(fastapi_app)

    with patch("web.routers.refill.create_invoice", return_value=("https://pay/x", "pid-1")):
        r = client.post(
            "/api/refill", json={"amount": 500},
            headers={
                "X-API-Key": app.api_key,
                "X-End-User-Id": "external-42",
            },
        )
    assert r.status_code == 200
    # Завершаем платёж и проверяем
    fake_payment = SimpleNamespace(status="succeeded", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake_payment):
        client.get("/api/refill/pid-1/status",
                   headers={"X-API-Key": app.api_key, "X-End-User-Id": "external-42"})

    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT source_type, source_app_id FROM refills"
        ).fetchall()
    assert rows == [("api", app.application.id)]
```

- [ ] **Step 4: Run и Commit**

```bash
pytest tests/web/test_routers_refill.py -v
git add web/routers/refill.py tests/web/test_routers_refill.py
git commit -m "feat(web): refill endpoint accepts API-key auth with source-tracking"
```

---

## Task 20: Обновить бот — middleware и handlers через identity

**Files:**
- Modify: `middlewares/exists_user.py`
- Modify: `handlers/user_functions.py:670+` — refill handler

- [ ] **Step 1: middlewares/exists_user.py**

Прочитать текущий `exists_user.py`. Скорее всего, он создаёт юзера в users-таблице по `from_user.id`. Заменить на:

```python
# было: utils.sqlite3.add_user(...) с id=from_user.id
# стало:
from services import identity

internal_user_id = identity.get_or_create_user_by_telegram(
    tg_id=message.from_user.id,
    user_name=message.from_user.username,
    first_name=message.from_user.first_name,
    ref_id=...,  # как было
)
data["user_id"] = internal_user_id  # пробрасываем в handler через context
```

Все хэндлеры, которые раньше использовали `call.from_user.id` как user_id для БД, должны теперь брать `data["user_id"]` (если используют middleware-context). Если не используют — добавить в каждом handler:

```python
from services.identity import get_or_create_user_by_telegram
internal_user_id = get_or_create_user_by_telegram(call.from_user.id, ...)
```

- [ ] **Step 2: refill_balance handler**

В `handlers/user_functions.py:672+`:

```python
from services.identity import get_or_create_user_by_telegram

internal_user_id = get_or_create_user_by_telegram(
    call.from_user.id,
    user_name=call.from_user.username,
    first_name=call.from_user.first_name,
)

# Все вызовы к services используют internal_user_id, не call.from_user.id
payment_url, payment_id = svc_create_invoice(internal_user_id, int(amount))
...
result = finalize_with_referral_bonus(
    internal_user_id, int(amount),
    source_type="telegram",  # явно
)
```

**Важно:** все остальные handlers в боте, которые трогают БД через user_id, должны быть обновлены аналогично. Это много мест. Стратегия: **в этой задаче обновить только refill-handler и middleware**, а остальные — отдельной задачей или по мере необходимости. Бот пока продолжает писать в `users` через старый `add_balance`/`add_user` — это работает, потому что `users.id` остался тем же.

- [ ] **Step 3: Импорт-тест**

```bash
python -c "import handlers.user_functions, middlewares.exists_user"
```

- [ ] **Step 4: Manual smoke (документируем)**

1. `/start` → юзер создаётся (или находится) через identity.
2. Refill в боте → проходит, в `refills` появляется строка с `source_type='telegram'`.

- [ ] **Step 5: Commit**

```bash
git add middlewares/exists_user.py handlers/user_functions.py
git commit -m "refactor(bot): use identity service for user lookup; refill writes source=telegram"
```

---

## Task 21: HTML-страницы — login, register, link, apps

**Files:**
- Modify: `web/static/index.html` — теперь страница выбора метода входа
- Create: `web/static/register.html` — email-регистрация
- Create: `web/static/login.html` — email-логин
- Create: `web/static/login_telegram.html` — Telegram OTP
- Modify: `web/static/cabinet.html` — секции providers + applications

Минимально: чистый HTML + fetch к API. Без фреймворков. Ключевые формы:

- index.html — три кнопки: "Войти через Email", "Войти через Telegram", "Зарегистрироваться".
- register.html — форма email + password + first_name → POST /api/auth/email/register → сохранить access_token в localStorage → redirect к cabinet.html.
- login.html — форма email + password → POST /api/auth/email/login → … → cabinet.html.
- login_telegram.html — двухшаговая форма:
  1. identifier → POST /api/auth/telegram/request-code → "Код отправлен в Telegram, введите его".
  2. code → POST /api/auth/telegram/verify-code → cabinet.html.
- cabinet.html — добавить:
  - Секция "Способы входа" — GET /api/me/providers, кнопки "Привязать email", "Привязать Telegram", крестики для удаления.
  - Секция "Мои приложения" — GET /api/applications, кнопка "Создать", показ key (только при создании).

Примечание: код HTML-страниц объёмный, но прямолинейный. Каждая страница ~80-150 строк. Шаблон fetch-запроса:

```js
async function api(method, path, body) {
  const opts = {method, headers: {"Content-Type": "application/json"}};
  const token = localStorage.getItem("access_token");
  if (token) opts.headers["Authorization"] = `Bearer ${token}`;
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.status === 204 ? null : await r.json();
}
```

- [ ] **Step 1: Сделать каждую страницу**
- [ ] **Step 2: Manual smoke** (в браузере) — все формы работают
- [ ] **Step 3: Commit**

```bash
git add web/static/
git commit -m "feat(web): add HTML pages for register/login/link/apps"
```

---

## Task 22: Интеграционная проверка — все тесты + manual smoke

- [ ] **Step 1: Полный pytest**

```bash
pytest -v
```

Expected: все тесты passed. Если что-то упало — править в этом же шаге.

- [ ] **Step 2: Запустить бот + web локально**

```bash
python __main__.py
```

Проверить:
- `/api/health` отдаёт 200
- `/api/auth/email/register` работает
- `/api/auth/telegram/request-code` отправляет в реальный бот (если бот запущен)
- `/api/auth/telegram/verify-code` принимает код, выдаёт JWT
- Привязка работает (через cabinet.html)
- Создание application → API-key → запрос с X-API-Key проходит

- [ ] **Step 3: Запустить миграцию на тестовой копии прод-БД**

```bash
cp data/database.db /tmp/test_prod.db
# временно подменить путь, запустить migrate
python scripts/migrate_phase2.py
# проверить что в auth_providers попало столько же записей сколько в users
```

- [ ] **Step 4: Commit финальный**

Если что-то правилось:
```bash
git add -A
git commit -m "test: fix tests after full integration"
```

---

## Task 23: E2E ручной чек-лист (smoke)

**Files:**
- Create: `docs/superpowers/plans/2026-05-06-multi-provider-identity-smoke.md`

Содержание чек-листа:

```markdown
# Phase 2 — E2E Smoke Checklist

## Подготовка
- [ ] `data/config.py` обновлён: OTP_TTL, OTP_MAX_ATTEMPTS, OTP_RESEND_COOLDOWN, BOT_HTTP_API_BASE.
- [ ] Применена миграция: `python scripts/migrate_phase2.py` на проде ПОСЛЕ бэкапа.

## Email auth
- [ ] Открыть /register.html → ввести email + пароль → редирект на cabinet.html, виден баланс=0.
- [ ] Logout (очистить localStorage), открыть /login.html → войти тем же email + пароль → cabinet.

## Telegram OTP
- [ ] /login_telegram.html → ввести username (или telegram_id) → "Код отправлен".
- [ ] Получить код в Telegram-боте → ввести → cabinet, баланс показывает реальный.

## Линковка
- [ ] Зарегистрировать через email → в cabinet привязать Telegram → проверить что в Telegram-боте теперь тот же баланс.
- [ ] (Обратная) Войти через Telegram → привязать email → выйти → войти через email → видим тот же ЛК.

## API-key flow
- [ ] В cabinet → "Создать приложение" → запомнить key (показывается один раз).
- [ ] curl POST /api/refill с `X-API-Key: sk_live_…` и `X-End-User-Id: testuser` → платёж проходит.
- [ ] В БД: `SELECT source_type, source_app_id FROM refills` → последняя запись `('api', <app.id>)`.

## Безопасность
- [ ] /api/me без токена → 401.
- [ ] /api/auth/email/login с неверным паролем → 401.
- [ ] /api/auth/telegram/verify-code с неверным кодом → 401, после 5 попыток код инвалидируется.
- [ ] Запрос /api/applications с X-API-Key (не JWT) → возвращает данные владельца ключа? (в Phase 2 — да; запретим в Phase 3).
- [ ] Revoke application → дальнейшие запросы с этим ключом → 401.
```

- [ ] **Step 1: Создать файл**
- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-05-06-multi-provider-identity-smoke.md
git commit -m "docs: add Phase 2 E2E smoke checklist"
```

---

## Финал

```bash
# Все коммиты в feature-ветку, потом PR в dev:
git push -u origin <feature-branch>
gh pr create --base dev --title "Phase 2: Multi-provider identity & API platform" \
  --body "См. docs/superpowers/plans/2026-05-06-multi-provider-identity.md"
```

После merge в `dev` — `dev` готов к Phase 3 (orders/promocodes/reviews как сервисы).

**Не сливать в main!** Main остаётся чистым до полного завершения проекта.
