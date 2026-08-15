# Landing / LK split + унификация order flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разделить лендинг и ЛК на разные поддомены и унифицировать order flow (один путь "unpaid → выбор оплаты → paid" для всех), удалив legacy `guest_orders`.

**Architecture:** Big-bang миграция в одном PR. Лендинг — статика nginx на `avito-pf.com`. ЛК — FastAPI+SPA на `lk.avito-pf.com`. Слияние гостевой и авторизованной модели через `auth_providers(provider='phone')`, добавление `verified` для разделения "ввёл номер при заказе" vs "подтвердил по СМС". Новые статусы заказа: `unpaid/paid/done/failed/payment_failed/cancelled` (переименование старых `Posted/Completed/Cancelled/Pending`).

**Tech Stack:** Python 3.x + FastAPI + sqlite3, aiogram (TG-бот), React (внутри SPA), YooKassa SDK, nginx.

**Спека:** [2026-06-05-landing-lk-split-design.md](../specs/2026-06-05-landing-lk-split-design.md)

---

## File Structure

### Создаваемые файлы

| Файл | Ответственность |
|------|-----------------|
| `services/sms.py` | `SmsGateway` Protocol + `StubSmsGateway` + `get_gateway()` |
| `services/payment_expiry.py` | Background job: переводит просроченные `unpaid` в `payment_failed` |
| `web/routers/auth_phone.py` | `/api/auth/phone/request-code` + `/api/auth/phone/verify` |
| `web/landing/index.html` | Standalone HTML лендинга (копия артефакта) |
| `nginx/avito-pf.conf` | nginx-конфиг для двух поддоменов |
| `web/static/components/PhoneLogin.jsx` | UI входа по номеру телефона |
| `tests/unit/test_sms.py` | Тесты SmsGateway |
| `tests/unit/test_otp_unified.py` | Тесты OTP с channel='sms' / 'telegram' |
| `tests/unit/test_identity_phone.py` | Тесты `find_or_create_user_by_phone`, `link_phone_provider`, merge |
| `tests/unit/test_orders_new_flow.py` | Тесты `create_unpaid`, `pay_with_*`, `mark_paid`, `mark_payment_failed` |
| `tests/unit/test_payment_expiry.py` | Тесты expiry-job |
| `tests/web/test_order_pf_flow.py` | Integration: полный flow заказа |
| `tests/web/test_phone_login.py` | Integration: SMS-OTP вход |
| `tests/unit/test_status_migration.py` | Тесты миграции `Posted → paid` в существующих БД |

### Модифицируемые файлы

| Файл | Что меняем |
|------|-----------|
| `utils/sqlite3.py` | `apply_phase2_migrations()` — добавить новые ALTER TABLE + миграция данных guest_orders + миграция статусов |
| `services/otp.py` | Обобщить: `channel`/`destination` вместо `telegram_id` |
| `services/identity.py` | Новые: `find_or_create_user_by_phone`, `link_phone_provider`, `_is_phone_only_user`, `merge_phone_only_into` |
| `services/orders.py` | Полностью переписать: новые функции, удалить `create_pf_order` |
| `services/notifications.py` | Маппинг статусов в строки |
| `services/exceptions.py` | Добавить `AccountMergeConflict`, `OrderNotFound`, `OrderStatusConflict`, `PaymentExpired` |
| `handlers/connect.py` | Использовать `link_phone_provider` (резолв коллизии) |
| `handlers/pf_order.py`, `handlers/profile.py`, `handlers/reviews.py`, `handlers/admin_orders.py`, `handlers/admin_reviews.py` | Переименовать статусы `Posted/Completed/Cancelled/Pending` |
| `web/schemas.py` | Обновить `_ORDER_STATUSES`, новые модели запросов/ответов |
| `web/routers/orders.py` | Новые эндпоинты: `POST /pf`, `POST /{id}/pay`, `GET /{id}/payment-status` |
| `web/main.py` | Снять `guest_orders_router`, добавить `auth_phone_router`, запустить expiry-task на startup |
| `web/static/app.jsx` | Маршрутизация: `/` → redirect на `/order/new` для незалогиненного |
| `web/static/components/OrderForm.jsx` | Шаги 1-2-3 (параметры → auth-choice → payment-method) |
| `web/static/components/OrderDetail.jsx` | Универсальная страница: все статусы + polling + кнопка "Повторить" |
| `web/static/components/Orders.jsx`, `AdminOrders.jsx` | Новые цветные бейджи статусов |
| `web/static/components/Auth.jsx` | Добавить вкладку "По телефону" |
| `web/static/components/AppHeader.jsx` | Удалить логику `route === 'landing'` |
| `utils/googlesheets.py` | Маппинг статусов |
| `scripts/seed_load_test_orders.py` | Использовать новые статусы |
| `docker-compose.yml` | (опционально) volume для `web/landing/` если nginx в отдельном контейнере |
| `.env.example` | Добавить `SMS_GATEWAY=stub` |
| `README.md` | Описать топологию и переменные |

### Удаляемые файлы

| Файл | Причина |
|------|---------|
| `services/guest_orders.py` | Логика мигрирует в унифицированный `services/orders.py` |
| `web/routers/guest_orders.py` | Эндпоинты заменяются на `/api/orders/*` |
| `web/static/components/Landing.jsx` | Лендинг переезжает на статический поддомен |
| `web/static/components/GuestOrderForm.jsx` | Сливается с `OrderForm.jsx` |
| `web/static/components/GuestOrderSuccess.jsx` | Сливается с `OrderDetail.jsx` |
| `tests/web/test_routers_guest_orders.py` | Тесты переписываются под новые эндпоинты |

---

## Task 1: Расширение схемы БД — новые колонки

**Files:**
- Modify: `utils/sqlite3.py:1061-1083` (функция `apply_phase2_migrations`)
- Modify: `utils/sqlite3.py:918-929` (определение `auth_providers` ddl — для свежих БД)
- Modify: `utils/sqlite3.py:945-957` (определение `otp_codes` ddl)
- Modify: `utils/sqlite3.py:852-866` (определение `orders` ddl)
- Test: `tests/unit/test_db_schema.py` (добавить кейсы)

### Step 1.1 — Написать failing test

Open `tests/unit/test_db_schema.py`, добавить:

```python
def test_orders_has_new_payment_columns(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(orders)").fetchall()}
    assert "payment_method" in cols
    assert "payment_expires_at" in cols
    assert "payment_id" in cols
    assert "phone" in cols


def test_auth_providers_has_verified_column(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(auth_providers)").fetchall()}
    assert "verified" in cols


def test_otp_codes_has_channel_and_destination_columns(tmp_db):
    from utils.sqlite3 import create_db
    create_db()
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(otp_codes)").fetchall()}
    assert "channel" in cols
    assert "destination" in cols
    assert "telegram_id" not in cols  # переименовано
```

- [ ] **Step 1.2 — Запустить тесты, убедиться что падают**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_db_schema.py::test_orders_has_new_payment_columns -v
```
Expected: FAIL (`KeyError` или `assert "payment_method" in {...}` не проходит).

(См. `feedback_docker_tests.md` — тесты только через docker exec.)

- [ ] **Step 1.3 — Обновить ddl `orders` в `get_schema_statements()`**

В `utils/sqlite3.py:852-866`, расширить CREATE TABLE orders новыми колонками. Внутри строки CREATE добавить:
```python
"payment_method TEXT,"
"payment_expires_at TIMESTAMP,"
"payment_id TEXT,"
"phone TEXT,"
```

- [ ] **Step 1.4 — Обновить ddl `auth_providers`**

В `utils/sqlite3.py:919-928`, добавить колонку `verified`:
```python
"verified INTEGER NOT NULL DEFAULT 1,"
```
*Дефолт 1 — для свежих БД новые TG/email регистрации сразу verified.*

- [ ] **Step 1.5 — Обновить ddl `otp_codes`**

Заменить `telegram_id INTEGER NOT NULL` на:
```python
"destination TEXT NOT NULL,"
"channel TEXT NOT NULL DEFAULT 'telegram',"
```

- [ ] **Step 1.6 — Добавить идемпотентные ALTER для существующих БД**

В `utils/sqlite3.py::apply_phase2_migrations()` после блока про `existing_orders` добавить:

```python
        # === unpaid order flow ===
        if 'payment_method' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT")
            print("orders.payment_method added")
        if 'payment_expires_at' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_expires_at TIMESTAMP")
            print("orders.payment_expires_at added")
        if 'payment_id' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN payment_id TEXT")
            print("orders.payment_id added")
        if 'phone' not in existing_orders:
            con.execute("ALTER TABLE orders ADD COLUMN phone TEXT")
            print("orders.phone added")

        # === auth_providers.verified ===
        existing_ap = {row['name'] for row in con.execute("PRAGMA table_info(auth_providers)").fetchall()}
        if 'verified' not in existing_ap:
            con.execute("ALTER TABLE auth_providers ADD COLUMN verified INTEGER NOT NULL DEFAULT 1")
            print("auth_providers.verified added (existing rows defaulted to verified=1)")

        # === otp_codes generalization ===
        existing_otp = {row['name'] for row in con.execute("PRAGMA table_info(otp_codes)").fetchall()}
        if 'destination' not in existing_otp:
            # Используем RENAME COLUMN (sqlite 3.25+). Если этой колонки уже нет — пропускаем.
            if 'telegram_id' in existing_otp:
                con.execute("ALTER TABLE otp_codes RENAME COLUMN telegram_id TO destination")
                print("otp_codes.telegram_id -> destination renamed")
        if 'channel' not in existing_otp:
            con.execute("ALTER TABLE otp_codes ADD COLUMN channel TEXT NOT NULL DEFAULT 'telegram'")
            print("otp_codes.channel added (default='telegram')")

        con.commit()
```

- [ ] **Step 1.7 — Запустить тесты, убедиться что проходят**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_db_schema.py -v
```
Expected: PASS.

- [ ] **Step 1.8 — Прогнать весь тестсьют, убедиться что нет регрессий**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Expected: PASS (некоторые тесты могут упасть если ссылаются на `telegram_id` в `otp_codes` — это разрулим в Task 4).

- [ ] **Step 1.9 — Commit**

```bash
git add utils/sqlite3.py tests/unit/test_db_schema.py
git commit -m "feat(db): добавлены колонки для unpaid order flow и SMS-OTP

orders: payment_method, payment_expires_at, payment_id, phone
auth_providers: verified (default=1 для legacy записей)
otp_codes: telegram_id -> destination, добавлена channel"
```

---

## Task 2: Миграция данных — статусы и guest_orders → orders

**Files:**
- Modify: `utils/sqlite3.py::apply_phase2_migrations` (продолжение)
- Test: `tests/unit/test_status_migration.py` (новый)

### Контекст

Старые статусы используются в 17+ местах. Маппинг:
- `Posted` → `paid`
- `Completed` → `done`
- `Cancelled` → `cancelled`
- `Pending` → `payment_failed`

Существующие `guest_orders.paid` мигрируются в `orders` (status=`paid` или `done`, в зависимости от того, был ли уже обработан — если в проде пусто, миграция тривиальна).

- [ ] **Step 2.1 — Написать failing test для миграции статусов**

Create `tests/unit/test_status_migration.py`:

```python
"""Тесты миграции старых статусов и данных guest_orders в новую схему."""
import sqlite3
import pytest


def _legacy_db_with_old_statuses(tmp_db_path):
    """Создаёт БД со старой схемой и парой записей со старыми статусами."""
    con = sqlite3.connect(tmp_db_path)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, balance INTEGER, user_name TEXT, first_name TEXT)")
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, increment INTEGER, user_id INTEGER, "
                "price INTEGER, position_name TEXT, status TEXT, links TEXT, contacts INTEGER, user_name TEXT)")
    con.execute("INSERT INTO users VALUES (1, 0, 'u1', NULL)")
    con.execute("INSERT INTO orders VALUES (1, 1, 1, 100, '1/1', 'Posted', '[]', 0, 'u1')")
    con.execute("INSERT INTO orders VALUES (2, 2, 1, 200, '1/1', 'Completed', '[]', 0, 'u1')")
    con.execute("INSERT INTO orders VALUES (3, 3, 1, 300, '1/1', 'Cancelled', '[]', 0, 'u1')")
    con.execute("INSERT INTO orders VALUES (4, 4, 1, 400, '1/1', 'Pending', '[]', 0, 'u1')")
    con.commit()
    con.close()


def test_status_migration_renames_legacy_statuses(tmp_db, monkeypatch):
    _legacy_db_with_old_statuses(tmp_db)
    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()
    with sqlite3.connect(tmp_db) as con:
        statuses = {row[0] for row in con.execute("SELECT status FROM orders").fetchall()}
    assert statuses == {"paid", "done", "cancelled", "payment_failed"}


def test_guest_orders_table_dropped_after_migration(tmp_db):
    from utils.sqlite3 import create_db, apply_phase2_migrations
    create_db()
    apply_phase2_migrations()
    with sqlite3.connect(tmp_db) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "guest_orders" not in tables
```

- [ ] **Step 2.2 — Run test, убедиться что падает**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_status_migration.py -v
```
Expected: FAIL (статусы не мигрируются, guest_orders ещё существует).

- [ ] **Step 2.3 — Добавить миграцию статусов в `apply_phase2_migrations`**

В `utils/sqlite3.py::apply_phase2_migrations` после блока otp_codes добавить:

```python
        # === order status renaming ===
        STATUS_MAP = {
            "Posted": "paid",
            "Completed": "done",
            "Cancelled": "cancelled",
            "Pending": "payment_failed",
        }
        for old, new in STATUS_MAP.items():
            con.execute("UPDATE orders SET status = ? WHERE status = ?", (new, old))
        con.commit()
```

- [ ] **Step 2.4 — Добавить миграцию данных и drop таблицы `guest_orders`**

После status renaming блока, добавить:

```python
        # === migrate guest_orders to orders, then drop ===
        existing_tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if 'guest_orders' in existing_tables:
            # Переносим только нетривиальные записи. Привязываем к user_id через phone-provider.
            rows = con.execute("SELECT * FROM guest_orders").fetchall()
            for row in rows:
                phone = row["phone"]
                # find or create user with phone-provider (verified=1 если статус paid, иначе 0)
                ap = con.execute(
                    "SELECT user_id FROM auth_providers WHERE provider='phone' AND identifier=?",
                    (phone,),
                ).fetchone()
                if ap:
                    user_id = ap["user_id"]
                else:
                    cur = con.execute(
                        "INSERT INTO users(balance, user_name, first_name) VALUES (0, NULL, NULL)"
                    )
                    user_id = cur.lastrowid
                    verified = 1 if row["status"] == "paid" else 0
                    con.execute(
                        "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
                        "VALUES (?, 'phone', ?, ?, ?)",
                        (user_id, phone, row["created_at"], verified),
                    )
                # Map guest status to order status
                new_status = {"paid": "paid", "pending_payment": "payment_failed", "failed": "payment_failed"}.get(
                    row["status"], "payment_failed"
                )
                con.execute(
                    "INSERT INTO orders(user_id, price, position_name, status, links, contacts, user_name, "
                    "payment_method, payment_id, phone) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL, 'yookassa', ?, ?)",
                    (user_id, row["price"], f"{row['days']}/{row['fix_count']}",
                     new_status, row["links"], row["contacts"], row["payment_id"], phone),
                )
            con.execute("DROP TABLE guest_orders")
            print(f"guest_orders migrated ({len(rows)} rows) and dropped")
        con.commit()
```

- [ ] **Step 2.5 — Run tests, убедиться что проходят**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_status_migration.py -v
```
Expected: PASS.

- [ ] **Step 2.6 — Commit**

```bash
git add utils/sqlite3.py tests/unit/test_status_migration.py
git commit -m "feat(db): миграция статусов Posted->paid и guest_orders в orders

STATUS_MAP: Posted->paid, Completed->done, Cancelled->cancelled, Pending->payment_failed.
guest_orders переносятся в orders через phone-provider, таблица удаляется."
```

---

## Task 3: Переименование статусов в коде (Posted → paid и т.д.)

**Files:** все из таблицы маппинга в Task 2.

Это механическая замена строковых литералов. TDD здесь — обновить ожидания существующих тестов после замены.

- [ ] **Step 3.1 — Найти все вхождения**

```bash
grep -rn "'Posted'\|\"Posted\"\|'Completed'\|\"Completed\"\|'Cancelled'\|\"Cancelled\"\|'Pending'\|\"Pending\"" services/ handlers/ web/ scripts/ utils/ tests/
```

Ожидаемо: ~30-50 совпадений в файлах из таблицы.

- [ ] **Step 3.2 — Заменить в `services/orders.py:66-73`**

```python
# Было:
status="Posted",
return PFOrderResult(order_id=order["increment"], total_price=total, status="Posted")
# Стало:
status="paid",
return PFOrderResult(order_id=order["increment"], total_price=total, status="paid")
```

*(Эту функцию мы всё равно удалим в Task 8, но пока — для целостности.)*

- [ ] **Step 3.3 — Заменить в `services/notifications.py:14`**

```python
# Было:
("order", "Posted"):    "📌 Заказ №{order_id} размещён.",
# Стало:
("order", "paid"):    "📌 Заказ №{order_id} оплачен и принят в работу.",
```

Добавить новые ключи:
```python
("order", "done"):     "✅ Заказ №{order_id} выполнен.",
("order", "failed"):   "❌ Заказ №{order_id} не выполнен. Свяжитесь с поддержкой.",
("order", "payment_failed"): "⏱ Заказ №{order_id} не оплачен в срок.",
("order", "cancelled"): "🚫 Заказ №{order_id} отменён.",
```

- [ ] **Step 3.4 — Заменить в `handlers/pf_order.py:237`**

```python
status="Posted",  →  status="paid",
```

- [ ] **Step 3.5 — Заменить в `handlers/profile.py:152`, `handlers/admin_orders.py:225,319`, `handlers/admin_reviews.py:146,212,221,316,325`, `handlers/reviews.py:139`**

Каждое сравнение/присвоение со старыми статусами поменять по маппингу.

```bash
# Удобно поштучно через sed на конкретные строки. Но я рекомендую открыть каждый файл
# глазами и применить Edit точечно — потому что в одном файле могут быть и другие 'Posted'
# (например, в комментах или строках сообщений), которые трогать не нужно.
```

- [ ] **Step 3.6 — Заменить в `web/schemas.py:294`**

```python
_ORDER_STATUSES = ("unpaid", "paid", "done", "failed", "payment_failed", "cancelled")
```

- [ ] **Step 3.7 — Заменить в `web/static/components/Orders.jsx:6`**

```jsx
const ORDER_STATUSES = [
  { key: 'unpaid',         label: 'Ожидает оплаты',   color: 'amber'  },
  { key: 'paid',           label: 'В работе',          color: 'blue'   },
  { key: 'done',           label: 'Выполнен',          color: 'green'  },
  { key: 'failed',         label: 'Ошибка накрутки',   color: 'red'    },
  { key: 'payment_failed', label: 'Не оплачен',        color: 'gray'   },
  { key: 'cancelled',      label: 'Отменён',           color: 'gray'   },
];
```

- [ ] **Step 3.8 — Заменить в `web/static/components/AdminOrders.jsx:4`**

```jsx
const ADMIN_STATUSES = ['unpaid', 'paid', 'done', 'failed', 'payment_failed', 'cancelled'];
```

- [ ] **Step 3.9 — Заменить в `utils/googlesheets.py:224,291,386`**

```python
# Было: 'Размещён' if order['status'] == 'Posted'
# Стало: 'В работе' if order['status'] == 'paid'
```

И добавить остальные случаи (done → "Выполнен" и т.п.).

- [ ] **Step 3.10 — Заменить в `scripts/seed_load_test_orders.py:27`**

```python
STATUS_CYCLE = ("paid", "done", "payment_failed")
```

- [ ] **Step 3.11 — Запустить весь тестсьют**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Expected: PASS. Если упали тесты с ожидаемым `'Posted'` — поправить ожидания на `'paid'`.

- [ ] **Step 3.12 — Commit**

```bash
git add -A
git commit -m "refactor: переименование статусов заказа в коде

Posted->paid, Completed->done, Cancelled->cancelled, Pending->payment_failed.
Затронуты: handlers/, services/orders.py, services/notifications.py,
web/schemas.py, web/static/components/{Orders,AdminOrders}.jsx,
utils/googlesheets.py, scripts/seed_load_test_orders.py.

Frontend: добавлены цветные метки для новых статусов unpaid и failed."
```

---

## Task 4: SmsGateway abstraction

**Files:**
- Create: `services/sms.py`
- Test: `tests/unit/test_sms.py`

- [ ] **Step 4.1 — Написать failing test**

Create `tests/unit/test_sms.py`:

```python
"""Тесты SmsGateway: stub-реализация и фабрика."""
import logging

import pytest


def test_stub_gateway_logs_and_stores_code(caplog):
    from services.sms import StubSmsGateway
    gw = StubSmsGateway()
    with caplog.at_level(logging.INFO):
        gw.send_code("+79991234567", "4521")
    assert gw.last_codes["+79991234567"] == "4521"
    assert any("4521" in rec.message for rec in caplog.records)


def test_get_gateway_returns_stub_when_env_not_set(monkeypatch):
    monkeypatch.delenv("SMS_GATEWAY", raising=False)
    from services.sms import get_gateway, StubSmsGateway
    gw = get_gateway()
    assert isinstance(gw, StubSmsGateway)


def test_get_gateway_returns_stub_when_env_set_to_stub(monkeypatch):
    monkeypatch.setenv("SMS_GATEWAY", "stub")
    from services.sms import get_gateway, StubSmsGateway
    gw = get_gateway()
    assert isinstance(gw, StubSmsGateway)


def test_get_gateway_raises_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("SMS_GATEWAY", "magic_provider_999")
    from services.sms import get_gateway
    with pytest.raises(ValueError, match="unknown SMS_GATEWAY"):
        get_gateway()
```

- [ ] **Step 4.2 — Run test, ожидаем FAIL**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_sms.py -v
```
Expected: FAIL — `ModuleNotFoundError: services.sms`.

- [ ] **Step 4.3 — Реализовать `services/sms.py`**

Create `services/sms.py`:

```python
"""SMS gateway abstraction. Конкретный провайдер выбирается через env SMS_GATEWAY."""
from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class SmsGateway(Protocol):
    def send_code(self, phone: str, code: str) -> None: ...


class StubSmsGateway:
    """Логирует код вместо реальной отправки. Для разработки и тестов."""

    def __init__(self) -> None:
        self.last_codes: dict[str, str] = {}

    def send_code(self, phone: str, code: str) -> None:
        self.last_codes[phone] = code
        logger.info("STUB SMS to %s: code=%s", phone, code)


_singleton: SmsGateway | None = None


def get_gateway() -> SmsGateway:
    global _singleton
    if _singleton is not None:
        return _singleton
    name = os.getenv("SMS_GATEWAY", "stub")
    if name == "stub":
        _singleton = StubSmsGateway()
    else:
        raise ValueError(f"unknown SMS_GATEWAY={name!r}. Реализуйте провайдер в services/sms.py")
    return _singleton


def _reset_for_tests() -> None:
    """Сбрасывает singleton — нужно в тестах, использующих monkeypatch на env."""
    global _singleton
    _singleton = None
```

- [ ] **Step 4.4 — Поправить тест чтобы сбрасывать singleton между кейсами**

В `tests/unit/test_sms.py` добавить fixture:

```python
@pytest.fixture(autouse=True)
def _reset_gateway_singleton():
    from services import sms
    sms._reset_for_tests()
    yield
    sms._reset_for_tests()
```

- [ ] **Step 4.5 — Run test, PASS**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_sms.py -v
```
Expected: PASS (все 4 теста).

- [ ] **Step 4.6 — Добавить в `.env.example`**

```
# SMS provider for OTP-based login. Допустимые значения: stub (по умолчанию).
# Реализации smsc/smsaero/etc добавляются по мере подключения.
SMS_GATEWAY=stub
```

- [ ] **Step 4.7 — Commit**

```bash
git add services/sms.py tests/unit/test_sms.py .env.example
git commit -m "feat(sms): добавлен SmsGateway Protocol + StubSmsGateway

Stub логирует код в STDOUT/log + сохраняет в memory для тестов.
get_gateway() читает env SMS_GATEWAY (default=stub).
Реальные провайдеры (SMSC.ru, Smsaero) — будут добавлены при подключении."
```

---

## Task 5: Обобщение services/otp.py под channel/destination

**Files:**
- Modify: `services/otp.py`
- Test: `tests/unit/test_otp_unified.py` (новый); `tests/unit/test_otp.py` (поправить ожидания)

### Контекст

Сейчас `services/otp.py` использует `telegram_id`. Нужно обобщить: `channel` ∈ {'telegram','sms'}, `destination` (str). Для telegram — `str(tg_id)`, для sms — нормализованный E.164.

- [ ] **Step 5.1 — Прочитать текущий services/otp.py**

```bash
cat services/otp.py
```
Зафиксировать функции `issue`, `verify`, `cleanup_expired`, и где они используют `telegram_id`.

- [ ] **Step 5.2 — Написать failing test для нового API**

Create `tests/unit/test_otp_unified.py`:

```python
"""Тесты обобщённого OTP-сервиса (channel='telegram' и channel='sms')."""
import pytest


def test_issue_sms_otp_stores_with_channel_and_destination(tmp_db):
    from services import otp
    code = otp.issue(channel='sms', destination='+79991234567', purpose='phone_login', ttl_seconds=300)
    assert len(code) >= 4
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT channel, destination, purpose FROM otp_codes").fetchone()
    assert row == ('sms', '+79991234567', 'phone_login')


def test_verify_sms_otp_consumes_record(tmp_db):
    from services import otp
    code = otp.issue(channel='sms', destination='+79991234567', purpose='phone_login', ttl_seconds=300)
    assert otp.verify(channel='sms', destination='+79991234567', code=code, purpose='phone_login') is True
    # повторный verify не проходит — consumed
    assert otp.verify(channel='sms', destination='+79991234567', code=code, purpose='phone_login') is False


def test_verify_wrong_code_increments_attempts_and_caps_at_three(tmp_db):
    from services import otp
    otp.issue(channel='sms', destination='+79991234567', purpose='phone_login', ttl_seconds=300)
    for _ in range(3):
        assert otp.verify(channel='sms', destination='+79991234567', code='0000', purpose='phone_login') is False
    # после 3 неверных — код сжигается, даже верный не пройдёт
    # (нужно знать актуальный код — здесь тест на лимит)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT attempts, consumed_at FROM otp_codes").fetchone()
    assert row[0] >= 3
    assert row[1] is not None  # сжат


def test_telegram_otp_still_works_after_generalization(tmp_db):
    """Регрессия: старый код, дёргающий issue с channel='telegram', должен работать."""
    from services import otp
    code = otp.issue(channel='telegram', destination='12345', purpose='link_account', ttl_seconds=300)
    assert otp.verify(channel='telegram', destination='12345', code=code, purpose='link_account') is True
```

- [ ] **Step 5.3 — Run test, FAIL**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_otp_unified.py -v
```
Expected: FAIL (API ещё не принимает channel/destination).

- [ ] **Step 5.4 — Переписать services/otp.py**

Полностью перепиши `services/otp.py` (адаптируй под существующие подписи где надо):

```python
"""OTP-коды для верификации действий пользователя (привязка TG, вход по SMS).

Хранятся в otp_codes(channel, destination, purpose, code_hash, ...).
- channel='telegram', destination=str(tg_id) — отправляется через TG-бота.
- channel='sms', destination=E.164-phone — отправляется через SmsGateway.

Сервис не отвечает за фактическую доставку — это делает caller.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from services.db import connect

MAX_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _gen_code() -> str:
    """4-значный числовой код. Достаточно для SMS UX, защищён attempts-лимитом."""
    return f"{secrets.randbelow(10000):04d}"


def issue(*, channel: str, destination: str, purpose: str, ttl_seconds: int,
          user_id_to_link: int | None = None) -> str:
    """Создаёт новый OTP, возвращает plaintext code (для отправки caller'ом).
    Идемпотентность: если есть активный неистёкший код для (channel, destination, purpose),
    сжигаем его и выдаём новый.
    """
    code = _gen_code()
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    with connect() as con:
        # Сжигаем старые активные коды для той же цели
        con.execute(
            "UPDATE otp_codes SET consumed_at=? "
            "WHERE channel=? AND destination=? AND purpose=? AND consumed_at IS NULL",
            (now.isoformat(), channel, destination, purpose),
        )
        con.execute(
            "INSERT INTO otp_codes(purpose, destination, channel, code_hash, "
            "user_id_to_link, created_at, expires_at, attempts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (purpose, destination, channel, _hash(code), user_id_to_link,
             now.isoformat(), expires_at.isoformat()),
        )
        con.commit()
    return code


def verify(*, channel: str, destination: str, code: str, purpose: str) -> bool:
    """Проверяет код. True/False. Каждая неверная попытка инкрементит attempts;
    после MAX_ATTEMPTS код сжигается."""
    now = _now()
    with connect() as con:
        row = con.execute(
            "SELECT id, code_hash, expires_at, attempts, consumed_at FROM otp_codes "
            "WHERE channel=? AND destination=? AND purpose=? "
            "ORDER BY id DESC LIMIT 1",
            (channel, destination, purpose),
        ).fetchone()
        if row is None:
            return False
        if row["consumed_at"] is not None:
            return False
        if datetime.fromisoformat(row["expires_at"]) < now:
            return False
        if row["attempts"] >= MAX_ATTEMPTS:
            con.execute("UPDATE otp_codes SET consumed_at=? WHERE id=?", (now.isoformat(), row["id"]))
            con.commit()
            return False
        if _hash(code) == row["code_hash"]:
            con.execute("UPDATE otp_codes SET consumed_at=? WHERE id=?", (now.isoformat(), row["id"]))
            con.commit()
            return True
        # неверный код
        new_attempts = row["attempts"] + 1
        if new_attempts >= MAX_ATTEMPTS:
            con.execute("UPDATE otp_codes SET attempts=?, consumed_at=? WHERE id=?",
                       (new_attempts, now.isoformat(), row["id"]))
        else:
            con.execute("UPDATE otp_codes SET attempts=? WHERE id=?",
                       (new_attempts, row["id"]))
        con.commit()
        return False


def get_user_id_to_link(*, channel: str, destination: str, code: str, purpose: str) -> int | None:
    """Возвращает user_id_to_link если код валиден, иначе None. Не консьюмит."""
    now = _now()
    with connect() as con:
        row = con.execute(
            "SELECT user_id_to_link, code_hash, expires_at, attempts, consumed_at FROM otp_codes "
            "WHERE channel=? AND destination=? AND purpose=? "
            "ORDER BY id DESC LIMIT 1",
            (channel, destination, purpose),
        ).fetchone()
        if row is None or row["consumed_at"] is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < now:
            return None
        if row["attempts"] >= MAX_ATTEMPTS:
            return None
        if _hash(code) == row["code_hash"]:
            return row["user_id_to_link"]
        return None
```

- [ ] **Step 5.5 — Run tests**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_otp_unified.py tests/unit/test_otp.py -v
```
Expected: новые тесты PASS, старые `test_otp.py` могут упасть если у них старый API. Поправить вызовы там: `issue(telegram_id=...)` → `issue(channel='telegram', destination=str(...))`.

- [ ] **Step 5.6 — Обновить вызовы issue/verify в production-коде**

```bash
grep -rn "otp\.issue\|otp\.verify" services/ handlers/ web/
```
Каждое вхождение: добавить `channel='telegram'` и `destination=str(tg_id)`.

- [ ] **Step 5.7 — Full test run**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Expected: PASS.

- [ ] **Step 5.8 — Commit**

```bash
git add services/otp.py tests/unit/test_otp_unified.py tests/unit/test_otp.py
git add handlers/ services/ web/  # обновлённые вызовы
git commit -m "refactor(otp): обобщение под channel/destination

services/otp.py принимает channel ('telegram'|'sms') + destination (str).
Обновлены вызовы в TG-хендлерах: issue(channel='telegram', destination=str(tg_id)).
Подготовка для phone-login через SMS-OTP."
```

---

## Task 6: services/exceptions.py — новые исключения

**Files:**
- Modify: `services/exceptions.py`

- [ ] **Step 6.1 — Прочитать текущий**

```bash
cat services/exceptions.py
```

- [ ] **Step 6.2 — Добавить новые классы**

В конец `services/exceptions.py` добавить:

```python
class AccountMergeConflict(Exception):
    """Попытка привязать phone к user A, когда тот же phone уже у user B
    с непустым provider-набором (полноценный аккаунт, не phone-only)."""

    def __init__(self, existing_user_id: int, target_user_id: int, phone: str):
        super().__init__(
            f"phone {phone} занят user_id={existing_user_id}, нельзя привязать к user_id={target_user_id}"
        )
        self.existing_user_id = existing_user_id
        self.target_user_id = target_user_id
        self.phone = phone


class OrderNotFound(Exception):
    pass


class OrderStatusConflict(Exception):
    """Попытка перевести заказ из недопустимого статуса (например, оплатить уже paid)."""


class PaymentExpired(Exception):
    """Попытка оплатить unpaid заказ после истечения TTL."""
```

- [ ] **Step 6.3 — Commit**

```bash
git add services/exceptions.py
git commit -m "feat(exceptions): добавлены AccountMergeConflict, OrderNotFound, OrderStatusConflict, PaymentExpired"
```

---

## Task 7: services/identity.py — phone-merge logic

**Files:**
- Modify: `services/identity.py`
- Test: `tests/unit/test_identity_phone.py` (новый)

- [ ] **Step 7.1 — Написать failing test**

Create `tests/unit/test_identity_phone.py`:

```python
"""Тесты identity-операций с phone-провайдером и резолвом коллизии."""
import sqlite3
import pytest


def _make_user(con, balance=0):
    cur = con.execute("INSERT INTO users(balance, user_name, first_name) VALUES (?, NULL, NULL)", (balance,))
    return cur.lastrowid


def _add_provider(con, user_id, provider, identifier, verified=1):
    from utils.dates import now_iso
    con.execute(
        "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, provider, identifier, now_iso(), verified),
    )


def test_find_or_create_user_by_phone_creates_new_user_when_phone_unknown(tmp_db):
    from services import identity
    user_id = identity.find_or_create_user_by_phone("+79991234567")
    assert user_id > 0
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, verified FROM auth_providers WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert row == (user_id, 0)  # verified=0 — phone не подтверждён


def test_find_or_create_user_by_phone_returns_existing_when_phone_known(tmp_db):
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        existing_id = _make_user(con)
        _add_provider(con, existing_id, "phone", "+79991234567", verified=1)
        con.commit()
    user_id = identity.find_or_create_user_by_phone("+79991234567")
    assert user_id == existing_id


def test_link_phone_provider_merges_phone_only_into_target(tmp_db):
    """Кейс: гость сделал быстрый заказ → phone-only-user. Потом регистрируется TG.
    Должно: orders перенесены в TG-user, phone-only удалён, phone теперь верифицирован."""
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        # сначала phone-only-user от быстрого заказа
        phone_only_id = _make_user(con, balance=50)
        _add_provider(con, phone_only_id, "phone", "+79991234567", verified=0)
        # его заказ
        con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, contacts, user_name) "
            "VALUES (?, 100, '1/1', 'paid', '[]', 0, NULL)", (phone_only_id,))
        # затем TG-user
        tg_id = _make_user(con, balance=0)
        _add_provider(con, tg_id, "telegram", "555000111", verified=1)
        con.commit()

    identity.link_phone_provider(tg_id, "+79991234567", set_verified=True)

    with sqlite3.connect(tmp_db) as con:
        # phone-only-user удалён
        rows = con.execute("SELECT id FROM users WHERE id=?", (phone_only_id,)).fetchall()
        assert rows == []
        # phone-provider теперь принадлежит TG-юзеру и verified=1
        ap = con.execute(
            "SELECT user_id, verified FROM auth_providers WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
        assert ap == (tg_id, 1)
        # заказы перенесены
        order_owner = con.execute("SELECT user_id FROM orders WHERE price=100").fetchone()
        assert order_owner == (tg_id,)
        # баланс перенесён (50 фо-only + 0 TG = 50)
        bal = con.execute("SELECT balance FROM users WHERE id=?", (tg_id,)).fetchone()
        assert bal == (50,)


def test_link_phone_provider_raises_conflict_when_other_user_has_other_providers(tmp_db):
    """Кейс: phone уже привязан к юзеру, у которого ЕСТЬ другие providers (email).
    Это конфликт двух полных аккаунтов — должен raise AccountMergeConflict."""
    from services import identity
    from services.exceptions import AccountMergeConflict
    with sqlite3.connect(tmp_db) as con:
        full_user_id = _make_user(con)
        _add_provider(con, full_user_id, "phone", "+79991234567", verified=1)
        _add_provider(con, full_user_id, "email", "user@example.com", verified=1)
        target_id = _make_user(con)
        _add_provider(con, target_id, "telegram", "555000111", verified=1)
        con.commit()

    with pytest.raises(AccountMergeConflict):
        identity.link_phone_provider(target_id, "+79991234567", set_verified=True)


def test_link_phone_provider_idempotent_relink_to_same_user_just_sets_verified(tmp_db):
    from services import identity
    with sqlite3.connect(tmp_db) as con:
        user_id = _make_user(con)
        _add_provider(con, user_id, "phone", "+79991234567", verified=0)
        con.commit()

    identity.link_phone_provider(user_id, "+79991234567", set_verified=True)

    with sqlite3.connect(tmp_db) as con:
        ap = con.execute(
            "SELECT user_id, verified FROM auth_providers WHERE provider='phone' AND identifier=?",
            ("+79991234567",),
        ).fetchone()
    assert ap == (user_id, 1)
```

- [ ] **Step 7.2 — Run test, FAIL**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_identity_phone.py -v
```
Expected: FAIL (функции не существуют).

- [ ] **Step 7.3 — Реализовать в services/identity.py**

В конец `services/identity.py` добавить:

```python
from services.exceptions import AccountMergeConflict


def find_or_create_user_by_phone(phone: str, *, verified: bool = False) -> int:
    """Возвращает user_id, к которому привязан phone-provider.
    Если такого нет — создаёт нового user с phone-provider (verified по флагу).
    """
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM auth_providers WHERE provider='phone' AND identifier=?",
            (phone,),
        ).fetchone()
        if row:
            return row["user_id"]
        cur = con.execute(
            "INSERT INTO users(balance, user_name, first_name) VALUES (0, NULL, NULL)"
        )
        new_user_id = cur.lastrowid
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (?, 'phone', ?, ?, ?)",
            (new_user_id, phone, _now_iso(), 1 if verified else 0),
        )
        con.commit()
        return new_user_id


def _is_phone_only_user(con, user_id: int) -> bool:
    rows = con.execute(
        "SELECT provider, verified FROM auth_providers WHERE user_id=?",
        (user_id,),
    ).fetchall()
    return len(rows) == 1 and rows[0]["provider"] == "phone" and rows[0]["verified"] == 0


def _merge_phone_only_into(con, source_user_id: int, target_user_id: int, set_verified: bool) -> None:
    """Переносит orders/refills/notifications/balance с source на target и удаляет source.
    auth_providers.phone у source перепривязывается к target."""
    # Заказы
    con.execute("UPDATE orders SET user_id=? WHERE user_id=?", (target_user_id, source_user_id))
    # Refills (если таблица есть)
    try:
        con.execute("UPDATE refills SET user_id=? WHERE user_id=?", (target_user_id, source_user_id))
    except Exception:
        pass
    # Notifications
    try:
        con.execute("UPDATE notifications SET user_id=? WHERE user_id=?", (target_user_id, source_user_id))
    except Exception:
        pass
    # Phone-provider передаём target
    con.execute(
        "UPDATE auth_providers SET user_id=?, verified=? "
        "WHERE provider='phone' AND user_id=?",
        (target_user_id, 1 if set_verified else 0, source_user_id),
    )
    # Баланс source приклеиваем к target
    src_balance = con.execute("SELECT balance FROM users WHERE id=?", (source_user_id,)).fetchone()
    if src_balance:
        con.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                    (int(src_balance["balance"] or 0), target_user_id))
    # Удаляем source-user
    con.execute("DELETE FROM users WHERE id=?", (source_user_id,))


def link_phone_provider(target_user_id: int, phone: str, *, set_verified: bool = False) -> None:
    """Привязывает phone к target_user_id. Резолвит коллизию через merge или conflict.

    - Если phone не привязан — INSERT.
    - Если уже на target — апдейт verified (если нужно).
    - Если на другом user phone-only (verified=0, единственный provider) — мерджит этого
      пользователя в target.
    - Иначе — raise AccountMergeConflict.
    """
    with connect() as con:
        existing = con.execute(
            "SELECT id, user_id, verified FROM auth_providers WHERE provider='phone' AND identifier=?",
            (phone,),
        ).fetchone()
        if existing is None:
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
                "VALUES (?, 'phone', ?, ?, ?)",
                (target_user_id, phone, _now_iso(), 1 if set_verified else 0),
            )
            con.commit()
            return
        if existing["user_id"] == target_user_id:
            if set_verified and not existing["verified"]:
                con.execute("UPDATE auth_providers SET verified=1 WHERE id=?", (existing["id"],))
                con.commit()
            return
        other_user_id = existing["user_id"]
        if _is_phone_only_user(con, other_user_id):
            _merge_phone_only_into(con, source_user_id=other_user_id,
                                   target_user_id=target_user_id, set_verified=set_verified)
            con.commit()
            return
        raise AccountMergeConflict(other_user_id, target_user_id, phone)
```

- [ ] **Step 7.4 — Run tests, PASS**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_identity_phone.py -v
```
Expected: 5 PASS.

- [ ] **Step 7.5 — Commit**

```bash
git add services/identity.py tests/unit/test_identity_phone.py
git commit -m "feat(identity): find_or_create_user_by_phone + link_phone_provider с merge

link_phone_provider резолвит UNIQUE-коллизию:
- phone не занят → INSERT
- phone на target → апдейт verified
- phone на другом user phone-only (verified=0) → merge заказов/refills/notifications/баланса
- иначе → AccountMergeConflict"
```

---

## Task 8: handlers/connect.py — использовать link_phone_provider

**Files:**
- Modify: `handlers/connect.py:85`

- [ ] **Step 8.1 — Прочитать текущий код**

```bash
sed -n '70,100p' handlers/connect.py
```

- [ ] **Step 8.2 — Заменить вызов**

В `handlers/connect.py:85`, заменить:
```python
identity.link_provider(user_id, "phone", phone, credential_hash=None)
```
на:
```python
identity.link_phone_provider(user_id, phone, set_verified=True)
```

*Telegram-контакт = верифицированный номер по умолчанию.*

- [ ] **Step 8.3 — Добавить обработку AccountMergeConflict**

В обёртке try/except (см. `connect.py:97-98`) добавить отдельный блок:

```python
from services.exceptions import AccountMergeConflict
...
try:
    identity.link_phone_provider(user_id, phone, set_verified=True)
except AccountMergeConflict as exc:
    logger.warning("phone-merge conflict: %s", exc)
    await message.answer(
        "⚠️ Этот номер уже привязан к другому аккаунту. "
        "Свяжитесь с поддержкой для слияния."
    )
    return
except Exception:
    logger.exception("link_phone_provider(%s) failed for user %s", phone, user_id)
    ...
```

- [ ] **Step 8.4 — Прогнать тесты**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Expected: PASS.

- [ ] **Step 8.5 — Commit**

```bash
git add handlers/connect.py
git commit -m "refactor(connect): handlers/connect использует link_phone_provider

При TG-шеринге контакта вызываем merge-логику. AccountMergeConflict ловим и
показываем юзеру сообщение про обращение в поддержку."
```

---

## Task 9: services/orders.py — переписать под новый flow

**Files:**
- Modify: `services/orders.py` (полностью переписать)
- Test: `tests/unit/test_orders_new_flow.py` (новый)

- [ ] **Step 9.1 — Написать failing test**

Create `tests/unit/test_orders_new_flow.py`:

```python
"""Тесты нового unpaid → paid flow."""
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone


def _make_user(con, balance=0):
    cur = con.execute("INSERT INTO users(balance, user_name, first_name) VALUES (?, NULL, NULL)", (balance,))
    return cur.lastrowid


def test_create_unpaid_inserts_row_with_status_unpaid(tmp_db):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    order_id = orders.create_unpaid(user_id=uid, links=["https://avito.ru/x"],
                                    days=1, fix_count=1, contacts=False, phone=None)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT status, payment_method, price FROM orders WHERE id=?", (order_id,)).fetchone()
    assert row[0] == "unpaid"
    assert row[1] is None  # ещё не выбран
    assert row[2] > 0


def test_pay_with_balance_success_marks_paid_and_decrements_balance(tmp_db):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=1000)
        con.commit()
    oid = orders.create_unpaid(user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None)
    orders.pay_with_balance(order_id=oid, user_id=uid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()[0]
        balance = con.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert status == "paid"
    # цена 1*1*1*price_per_unit (price_per_unit = 1 в дефолте) = 1
    assert balance == 999


def test_pay_with_balance_insufficient_raises(tmp_db):
    from services import orders
    from services.exceptions import InsufficientBalance  # имя — см. services/exceptions.py
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=0)
        con.commit()
    oid = orders.create_unpaid(user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None)
    with pytest.raises(InsufficientBalance):
        orders.pay_with_balance(order_id=oid, user_id=uid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()[0]
    assert status == "unpaid"  # не изменился


def test_pay_with_balance_on_already_paid_raises(tmp_db):
    from services import orders
    from services.exceptions import OrderStatusConflict
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con, balance=10)
        con.commit()
    oid = orders.create_unpaid(user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None)
    orders.pay_with_balance(order_id=oid, user_id=uid)
    with pytest.raises(OrderStatusConflict):
        orders.pay_with_balance(order_id=oid, user_id=uid)


def test_mark_payment_failed_sets_status(tmp_db):
    from services import orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.commit()
    oid = orders.create_unpaid(user_id=uid, links=["x"], days=1, fix_count=1, contacts=False, phone=None)
    orders.mark_payment_failed(order_id=oid)
    with sqlite3.connect(tmp_db) as con:
        status = con.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()[0]
    assert status == "payment_failed"
```

*Примечание: `InsufficientBalance` уже есть в `services/orders.py:17-18`. Если переезжаем в `services/exceptions.py` — соответственно правим импорт.*

- [ ] **Step 9.2 — Run test, FAIL**

Expected: `AttributeError: module 'services.orders' has no attribute 'create_unpaid'`.

- [ ] **Step 9.3 — Полностью переписать services/orders.py**

Заменить содержимое `services/orders.py` на:

```python
"""Business logic для нового unpaid → paid flow заказов."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.db import connect
from services.exceptions import (
    InsufficientBalance,
    OrderNotFound,
    OrderStatusConflict,
    PaymentError,
    PaymentExpired,
)
from utils.dates import now_iso
from utils.sqlite3 import (
    get_price,
    get_users_last_order,
    user_orders_count,
    user_orders_paginated,
)


# TTL по способу оплаты (в минутах)
TTL_YOOKASSA_MINUTES = 10
TTL_BALANCE_MINUTES = 30
TTL_NO_METHOD_MINUTES = 60  # юзер не выбрал способ


def get_pf_price_per_unit() -> int:
    raw = get_price("price_avito_pf")
    return int(raw) if raw is not None else 1


def _price_for(links: list[str], days: int, fix_count: int) -> int:
    return get_pf_price_per_unit() * fix_count * days * len(links)


def create_unpaid(*, user_id: int, links: list[str], days: int, fix_count: int,
                  contacts: bool, phone: Optional[str]) -> int:
    """Создаёт заказ со статусом 'unpaid'. payment_method/expires пока NULL.
    Возвращает order_id."""
    price = _price_for(links, days, fix_count)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=TTL_NO_METHOD_MINUTES)).isoformat()
    with connect() as con:
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, contacts, "
            "user_name, payment_method, payment_expires_at, payment_id, phone) "
            "VALUES (?, ?, ?, 'unpaid', ?, ?, NULL, NULL, ?, NULL, ?)",
            (user_id, price, f"{days}/{fix_count}", json.dumps(links), int(contacts), expires, phone),
        )
        con.commit()
        return cur.lastrowid


def get_order(order_id: int) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if row is None:
        raise OrderNotFound(f"order_id={order_id}")
    return dict(row)


def _set_payment_method_and_ttl(con, order_id: int, method: str) -> str:
    """Атомарно обновляет payment_method и payment_expires_at если заказ в 'unpaid'.
    Возвращает новый expires_at. Raises OrderStatusConflict если уже не unpaid."""
    ttl_min = TTL_YOOKASSA_MINUTES if method == "yookassa" else TTL_BALANCE_MINUTES
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_min)).isoformat()
    cur = con.execute(
        "UPDATE orders SET payment_method=?, payment_expires_at=? "
        "WHERE id=? AND status='unpaid'",
        (method, expires, order_id),
    )
    if cur.rowcount == 0:
        raise OrderStatusConflict(f"order {order_id} не в unpaid")
    return expires


def pay_with_balance(*, order_id: int, user_id: int) -> None:
    """Атомарное списание с баланса. Raises InsufficientBalance / OrderStatusConflict / PaymentExpired."""
    with connect() as con:
        order = con.execute("SELECT * FROM orders WHERE id=? AND user_id=?",
                            (order_id, user_id)).fetchone()
        if order is None:
            raise OrderNotFound(f"order {order_id} for user {user_id}")
        if order["status"] != "unpaid":
            raise OrderStatusConflict(f"order {order_id} в статусе {order['status']}")
        # Атомарное списание балансной транзакцией
        bal = int(con.execute("SELECT balance FROM users WHERE id=?", (user_id,)).fetchone()["balance"] or 0)
        if bal < order["price"]:
            raise InsufficientBalance(f"need {order['price']}, have {bal}")
        _set_payment_method_and_ttl(con, order_id, "balance")
        con.execute("UPDATE users SET balance = balance - ? WHERE id=?", (order["price"], user_id))
        con.execute("UPDATE orders SET status='paid' WHERE id=? AND status='unpaid'", (order_id,))
        con.commit()


def pay_with_yookassa(*, order_id: int, return_url: str) -> tuple[str, str]:
    """Создаёт YooKassa Payment, обновляет order: payment_method/payment_id/expires.
    Возвращает (confirmation_url, payment_id). Raises OrderStatusConflict / PaymentError."""
    from data.config import SHOP_ID, SECRET_KEY
    from yookassa import Configuration, Payment

    with connect() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if order is None:
            raise OrderNotFound(f"order {order_id}")
        if order["status"] != "unpaid":
            raise OrderStatusConflict(f"order {order_id} в статусе {order['status']}")
        _set_payment_method_and_ttl(con, order_id, "yookassa")
        con.commit()

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    try:
        payment = Payment.create({
            "amount": {"value": f"{order['price']:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"PF order #{order_id}",
            "metadata": {"order_id": str(order_id)},
        })
    except Exception as exc:
        raise PaymentError(str(exc)) from exc

    with connect() as con:
        con.execute("UPDATE orders SET payment_id=? WHERE id=?", (payment.id, order_id))
        con.commit()

    return payment.confirmation.confirmation_url, payment.id


def mark_paid(order_id: int) -> None:
    """Идемпотентно переводит unpaid → paid (для YooKassa webhook/polling).
    Если статус не unpaid — no-op (защита от двойного webhook)."""
    with connect() as con:
        con.execute("UPDATE orders SET status='paid' WHERE id=? AND status='unpaid'", (order_id,))
        con.commit()


def mark_payment_failed(order_id: int) -> None:
    """Переводит unpaid → payment_failed. Дёргает Payment.cancel для yookassa если payment_id есть."""
    with connect() as con:
        order = con.execute("SELECT payment_method, payment_id FROM orders WHERE id=? AND status='unpaid'",
                            (order_id,)).fetchone()
        if order is None:
            return  # уже не unpaid или не существует
        con.execute("UPDATE orders SET status='payment_failed' WHERE id=? AND status='unpaid'", (order_id,))
        con.commit()
    # Best-effort cancel в yookassa
    if order and order["payment_method"] == "yookassa" and order["payment_id"]:
        try:
            from data.config import SHOP_ID, SECRET_KEY
            from yookassa import Configuration, Payment
            Configuration.account_id = SHOP_ID
            Configuration.secret_key = SECRET_KEY
            Payment.cancel(order["payment_id"])
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "yookassa Payment.cancel failed for order %s", order_id
            )


def list_orders(user_id: int, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    items = user_orders_paginated(user_id, limit=page_size, offset=offset)
    total = user_orders_count(user_id)
    return items, total
```

*Удаляем `create_pf_order` и `PFOrderResult` — теперь не нужны.*

- [ ] **Step 9.4 — Перенести `InsufficientBalance` в `services/exceptions.py`**

В `services/exceptions.py` добавить (если ещё нет):
```python
class InsufficientBalance(Exception):
    pass
```
И в `services/orders.py` импорт из `services.exceptions` (уже сделан выше).

Удалить локальное определение `class InsufficientBalance(Exception): pass` из `services/orders.py`.

Найти всех, кто импортирует из `services.orders`:
```bash
grep -rn "from services.orders import\|from services\.orders import" .
```
Где найдено `InsufficientBalance` — поменять на `from services.exceptions import InsufficientBalance`.

- [ ] **Step 9.5 — Run tests**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_orders_new_flow.py -v
```
Expected: PASS.

- [ ] **Step 9.6 — Full test sweep**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Expected: некоторые тесты роутера `orders` упадут — это разрулим в Task 11. Если ломается test_routers_orders.py — отметить и продолжать.

- [ ] **Step 9.7 — Commit**

```bash
git add services/orders.py services/exceptions.py tests/unit/test_orders_new_flow.py
git add -u  # обновлённые импорты
git commit -m "feat(orders): новый unpaid → paid flow

Функции:
- create_unpaid(user_id, links, days, fix_count, contacts, phone) -> order_id
- pay_with_balance(order_id, user_id) — атомарное списание
- pay_with_yookassa(order_id, return_url) -> (confirmation_url, payment_id)
- mark_paid(order_id) — идемпотентный (для webhook)
- mark_payment_failed(order_id) — + Payment.cancel в юкассе

TTL: 10мин юкасса, 30мин баланс, 60мин если method не выбран.
Удалены create_pf_order и PFOrderResult (старый flow).
InsufficientBalance перенесён в services.exceptions."
```

---

## Task 10: services/payment_expiry.py — фоновая задача

**Files:**
- Create: `services/payment_expiry.py`
- Modify: `web/main.py` (регистрация startup task)
- Test: `tests/unit/test_payment_expiry.py` (новый)

- [ ] **Step 10.1 — Написать failing test**

Create `tests/unit/test_payment_expiry.py`:

```python
"""Тесты payment_expiry job."""
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone


def _make_user(con):
    cur = con.execute("INSERT INTO users(balance, user_name, first_name) VALUES (0, NULL, NULL)")
    return cur.lastrowid


def test_expire_unpaid_marks_expired_orders_as_payment_failed(tmp_db):
    from services.payment_expiry import expire_unpaid_orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        # expired
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts, "
                    "payment_method, payment_expires_at) VALUES (?, 100, '1/1', 'unpaid', '[]', 0, 'yookassa', ?)",
                    (uid, past))
        # not yet
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts, "
                    "payment_method, payment_expires_at) VALUES (?, 100, '1/1', 'unpaid', '[]', 0, 'balance', ?)",
                    (uid, future))
        con.commit()

    expire_unpaid_orders()

    with sqlite3.connect(tmp_db) as con:
        statuses = [row[0] for row in con.execute("SELECT status FROM orders ORDER BY id").fetchall()]
    assert statuses == ["payment_failed", "unpaid"]


def test_expire_unpaid_skips_orders_with_no_expires_at(tmp_db):
    """Заказы без выбранного payment_method имеют expires=NULL — их не трогаем (или у них свой default)."""
    from services.payment_expiry import expire_unpaid_orders
    with sqlite3.connect(tmp_db) as con:
        uid = _make_user(con)
        con.execute("INSERT INTO orders(user_id, price, position_name, status, links, contacts) "
                    "VALUES (?, 100, '1/1', 'unpaid', '[]', 0)", (uid,))
        con.commit()
    expire_unpaid_orders()  # не падает
    with sqlite3.connect(tmp_db) as con:
        status = con.execute("SELECT status FROM orders").fetchone()[0]
    assert status == "unpaid"
```

- [ ] **Step 10.2 — Run test, FAIL**

Expected: `ModuleNotFoundError: services.payment_expiry`.

- [ ] **Step 10.3 — Реализовать services/payment_expiry.py**

Create `services/payment_expiry.py`:

```python
"""Background job: переводит просроченные unpaid заказы в payment_failed."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services.db import connect
from services.orders import mark_payment_failed

logger = logging.getLogger(__name__)

EXPIRY_LOOP_INTERVAL_SECONDS = 60


def expire_unpaid_orders() -> int:
    """Находит unpaid заказы с истёкшим payment_expires_at, переводит в payment_failed.
    Возвращает количество обработанных."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        rows = con.execute(
            "SELECT id FROM orders WHERE status='unpaid' "
            "AND payment_expires_at IS NOT NULL AND payment_expires_at < ?",
            (now_iso,),
        ).fetchall()
    count = 0
    for row in rows:
        try:
            mark_payment_failed(row["id"])
            count += 1
        except Exception:
            logger.exception("expire_unpaid_orders: failed to mark order %s", row["id"])
    if count:
        logger.info("expire_unpaid_orders: %d orders -> payment_failed", count)
    return count


async def run_expiry_loop() -> None:
    """Asyncio loop: вызывает expire_unpaid_orders раз в EXPIRY_LOOP_INTERVAL_SECONDS секунд."""
    logger.info("payment_expiry loop started, interval=%ds", EXPIRY_LOOP_INTERVAL_SECONDS)
    while True:
        try:
            expire_unpaid_orders()
        except Exception:
            logger.exception("expire_unpaid_orders crashed (will retry)")
        await asyncio.sleep(EXPIRY_LOOP_INTERVAL_SECONDS)
```

- [ ] **Step 10.4 — Run tests, PASS**

```bash
docker exec -it bots-api-1 pytest tests/unit/test_payment_expiry.py -v
```
Expected: PASS.

- [ ] **Step 10.5 — Зарегистрировать loop в web/main.py**

В `web/main.py` найти место регистрации startup и добавить:

```python
from contextlib import asynccontextmanager
from services.payment_expiry import run_expiry_loop

_expiry_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app):
    global _expiry_task
    _expiry_task = asyncio.create_task(run_expiry_loop())
    yield
    _expiry_task.cancel()
```

*Если в `web/main.py` уже есть lifespan — добавить туда вызовы. Если нет — обернуть `app = FastAPI(lifespan=lifespan)`.*

Проверь как сейчас сделано:
```bash
grep -n "lifespan\|on_event\|startup\|FastAPI(" web/main.py
```

И адаптируй вставку под существующий паттерн.

- [ ] **Step 10.6 — Smoke test startup**

```bash
docker compose restart api
docker logs bots-api-1 --tail 50
```
Expected: видим `"payment_expiry loop started, interval=60s"` в логах.

- [ ] **Step 10.7 — Commit**

```bash
git add services/payment_expiry.py tests/unit/test_payment_expiry.py web/main.py
git commit -m "feat(orders): payment_expiry loop для перевода просроченных unpaid в payment_failed

expire_unpaid_orders() — синхронная одноразовая обработка (тестируемая).
run_expiry_loop() — asyncio loop с интервалом 60 сек, запускается на FastAPI startup."
```

---

## Task 11: web/schemas.py + web/routers/orders.py — новые эндпоинты

**Files:**
- Modify: `web/schemas.py` (новые модели запросов/ответов)
- Modify: `web/routers/orders.py` (полная переделка)
- Test: `tests/web/test_routers_orders.py` (адаптировать); `tests/web/test_order_pf_flow.py` (новый integration)

- [ ] **Step 11.1 — Добавить новые Pydantic-модели в web/schemas.py**

В `web/schemas.py` добавить:

```python
from typing import Literal


class PFOrderRequest(BaseModel):
    """Запрос на создание unpaid PF-заказа. phone обязателен для гостей,
    игнорируется для авторизованных."""
    links: list[str] = Field(..., min_items=1, max_items=20)
    days: int = Field(..., ge=1, le=90)
    fix_count: int = Field(..., ge=1, le=200)
    contacts: bool = False
    agreed_privacy: bool
    agreed_offer: bool
    phone: Optional[str] = None  # обязателен для гостей


class PFOrderResponse(BaseModel):
    order_id: int
    price: int
    available_methods: list[Literal["balance", "yookassa"]]


class OrderPayRequest(BaseModel):
    method: Literal["balance", "yookassa"]


class OrderPayBalanceResponse(BaseModel):
    status: Literal["paid"]
    order_id: int


class OrderPayYookassaResponse(BaseModel):
    confirmation_url: str
    expires_at: str  # ISO timestamp


class OrderPaymentStatusResponse(BaseModel):
    status: Literal["unpaid", "paid", "payment_failed", "done", "failed", "cancelled"]
    time_remaining_seconds: Optional[int] = None
    order_id: int
```

Старые `PFOrderRequest`/`GuestPFOrderRequest`/`PaymentAvailableResponse`/`GuestOrderStatusResponse`/`GuestPFOrderResponse` — пометить как deprecated и удалить (это Task 13).

- [ ] **Step 11.2 — Написать failing integration test**

Create `tests/web/test_order_pf_flow.py`:

```python
"""Integration: POST /api/orders/pf → POST /pay → проверка статуса."""
import pytest


def test_authorized_user_creates_unpaid_and_pays_with_balance(authed_client, db_user_with_balance):
    user_id = db_user_with_balance(balance=1000)
    # Create unpaid
    resp = authed_client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    oid = data["order_id"]
    assert "balance" in data["available_methods"]
    assert "yookassa" in data["available_methods"]

    # Pay with balance
    resp = authed_client.post(f"/api/orders/pf/{oid}/pay", json={"method": "balance"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"


def test_guest_with_phone_only_sees_yookassa_method_only(client):
    """Гость без сессии: создаёт unpaid через phone, ему доступна только yookassa."""
    resp = client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
        "phone": "+79991234567",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["available_methods"] == ["yookassa"]


def test_guest_without_phone_gets_400(client):
    resp = client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": True, "agreed_offer": True,
    })
    assert resp.status_code == 400


def test_missing_privacy_consent_returns_400(authed_client):
    resp = authed_client.post("/api/orders/pf", json={
        "links": ["https://avito.ru/x"], "days": 1, "fix_count": 1,
        "contacts": False, "agreed_privacy": False, "agreed_offer": True,
    })
    assert resp.status_code == 400
```

*(`authed_client`, `client`, `db_user_with_balance` — фикстуры, смотри `tests/web/conftest.py` и адаптируй имена.)*

- [ ] **Step 11.3 — Run test, FAIL**

Expected: 404 или 422 — эндпоинт не определён в новом виде.

- [ ] **Step 11.4 — Переписать web/routers/orders.py**

Заменить содержимое `web/routers/orders.py` на:

```python
"""Унифицированные эндпоинты заказов: гость и авторизованный — один путь."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from services import orders as svc
from services import identity
from services.exceptions import (
    InsufficientBalance,
    OrderNotFound,
    OrderStatusConflict,
    PaymentError,
)
from services.payment_methods import is_enabled as method_enabled
from services.payment_probe import is_yookassa_enabled
from utils.phones import normalize_phone  # ВАЖНО: см. шаг 11.4a
from web.deps import get_current_user_optional
from web.schemas import (
    OrderPayBalanceResponse,
    OrderPayRequest,
    OrderPayYookassaResponse,
    OrderPaymentStatusResponse,
    PFOrderRequest,
    PFOrderResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orders", tags=["orders"])


def _available_methods(user_id: Optional[int], price: int) -> list[str]:
    methods = []
    if user_id is not None and method_enabled("balance"):
        # Покажем балансом только если хватает
        from services.balance import get_balance  # или прямой SQL
        if get_balance(user_id) >= price:
            methods.append("balance")
    if method_enabled("yookassa") and is_yookassa_enabled():
        methods.append("yookassa")
    return methods


@router.post("/pf", response_model=PFOrderResponse, status_code=201)
async def create_pf(body: PFOrderRequest, user=Depends(get_current_user_optional)) -> PFOrderResponse:
    if not (body.agreed_privacy and body.agreed_offer):
        raise HTTPException(400, "Необходимо принять политику конфиденциальности и оферту")

    if user is not None:
        user_id = user["id"]
        phone = None  # из сессии не нужен в orders.phone
    else:
        if not body.phone:
            raise HTTPException(400, "phone обязателен для гостевого заказа")
        phone = normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(400, "невалидный формат телефона")
        user_id = identity.find_or_create_user_by_phone(phone)

    order_id = svc.create_unpaid(
        user_id=user_id, links=body.links, days=body.days, fix_count=body.fix_count,
        contacts=body.contacts, phone=phone,
    )
    order = svc.get_order(order_id)
    methods = _available_methods(user_id=user["id"] if user else None, price=order["price"])
    if not methods:
        raise HTTPException(503, "Нет доступных способов оплаты")
    return PFOrderResponse(order_id=order_id, price=order["price"], available_methods=methods)


@router.post("/pf/{order_id}/pay")
async def pay(order_id: int, body: OrderPayRequest, request: Request,
              user=Depends(get_current_user_optional)):
    order = svc.get_order(order_id)
    if body.method == "balance":
        if user is None or user["id"] != order["user_id"]:
            raise HTTPException(403, "balance доступен только авторизованному владельцу заказа")
        try:
            svc.pay_with_balance(order_id=order_id, user_id=user["id"])
        except InsufficientBalance:
            raise HTTPException(400, "Недостаточно средств на балансе")
        except OrderStatusConflict as exc:
            raise HTTPException(409, str(exc))
        return OrderPayBalanceResponse(status="paid", order_id=order_id)

    if body.method == "yookassa":
        return_url = str(request.url_for("get_order_detail", order_id=order_id))
        try:
            confirm_url, _ = svc.pay_with_yookassa(order_id=order_id, return_url=return_url)
        except OrderStatusConflict as exc:
            raise HTTPException(409, str(exc))
        except PaymentError as exc:
            raise HTTPException(502, f"Ошибка платёжной системы: {exc}")
        order = svc.get_order(order_id)
        return OrderPayYookassaResponse(confirmation_url=confirm_url,
                                        expires_at=order["payment_expires_at"])

    raise HTTPException(400, f"unknown method: {body.method}")


@router.get("/pf/{order_id}", name="get_order_detail")
async def get_order_detail(order_id: int):
    order = svc.get_order(order_id)
    return order  # вернём raw row — фронт уже умеет это парсить


@router.get("/pf/{order_id}/payment-status", response_model=OrderPaymentStatusResponse)
async def payment_status(order_id: int) -> OrderPaymentStatusResponse:
    order = svc.get_order(order_id)
    if order["status"] == "unpaid":
        # для yookassa дёрнем API на всякий случай
        if order["payment_method"] == "yookassa" and order["payment_id"]:
            from data.config import SHOP_ID, SECRET_KEY
            from yookassa import Configuration, Payment
            Configuration.account_id = SHOP_ID
            Configuration.secret_key = SECRET_KEY
            try:
                p = Payment.find_one(order["payment_id"])
                if p.status == "succeeded":
                    svc.mark_paid(order_id)
                    return OrderPaymentStatusResponse(status="paid", order_id=order_id)
                if p.status == "canceled":
                    svc.mark_payment_failed(order_id)
                    return OrderPaymentStatusResponse(status="payment_failed", order_id=order_id)
            except Exception:
                logger.warning("yookassa probe failed for order %s", order_id)
        # вычислим time_remaining
        from datetime import datetime, timezone
        if order["payment_expires_at"]:
            delta = datetime.fromisoformat(order["payment_expires_at"]) - datetime.now(timezone.utc)
            rem = max(0, int(delta.total_seconds()))
        else:
            rem = None
        return OrderPaymentStatusResponse(status="unpaid", order_id=order_id, time_remaining_seconds=rem)
    return OrderPaymentStatusResponse(status=order["status"], order_id=order_id)
```

- [ ] **Step 11.4a — Создать utils/phones.py если нет**

```bash
ls utils/phones.py 2>/dev/null
```

Если нет — создать с переносом нормализации из `services/auth_telegram.py`:

```python
"""Нормализация телефонов в E.164-ish формат."""
import re


def normalize_phone(raw: str) -> str | None:
    """+79..., 79..., 89... → +79...; иначе None."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-\(\)]", "", raw.strip())
    if cleaned.startswith("+"):
        digits = cleaned[1:]
        if digits.isdigit() and 10 <= len(digits) <= 15:
            return cleaned
        return None
    if cleaned.isdigit():
        if cleaned.startswith("8") and len(cleaned) == 11:
            return "+7" + cleaned[1:]
        if cleaned.startswith("7") and len(cleaned) == 11:
            return "+" + cleaned
    return None
```

В `services/auth_telegram.py` заменить локальный `_normalize_phone` на импорт из `utils.phones`.

- [ ] **Step 11.5 — Run integration tests**

```bash
docker exec -it bots-api-1 pytest tests/web/test_order_pf_flow.py -v
```
Если падает — смотри причины. Возможные:
- `get_current_user_optional` не существует — найди dep в `web/deps.py`, добавь optional-вариант.
- `get_balance` сервис — проверь `services/balance.py`, есть ли такая функция.

- [ ] **Step 11.6 — Полный регресс**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Ожидается: старые тесты `test_routers_orders.py` могут упасть — они ссылаются на удалённый `create_pf_order`. Поправь их под новый flow.

- [ ] **Step 11.7 — Commit**

```bash
git add web/schemas.py web/routers/orders.py utils/phones.py services/auth_telegram.py
git add tests/web/test_order_pf_flow.py tests/web/test_routers_orders.py
git commit -m "feat(api): новые эндпоинты POST /api/orders/pf, /pay, /payment-status

Унифицированный flow для гостя и авторизованного:
- POST /pf — создаёт unpaid (с phone для гостя или user из сессии)
- POST /pf/{id}/pay {method} — оплата с баланса (атомарно) или yookassa
- GET /pf/{id}/payment-status — polling статуса с проверкой YooKassa API

utils/phones.normalize_phone вынесен из services/auth_telegram.py."
```

---

## Task 12: web/routers/auth_phone.py — SMS-OTP логин

**Files:**
- Create: `web/routers/auth_phone.py`
- Modify: `web/main.py` (регистрация router)
- Test: `tests/web/test_phone_login.py` (новый)

- [ ] **Step 12.1 — Написать failing integration test**

Create `tests/web/test_phone_login.py`:

```python
"""Integration: вход по СМС-коду."""
import pytest


def test_request_code_returns_200_and_stub_stores_code(client):
    from services import sms
    sms._reset_for_tests()
    resp = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert resp.status_code == 200
    gw = sms.get_gateway()
    assert "+79991234567" in gw.last_codes


def test_verify_code_creates_session(client):
    from services import sms
    sms._reset_for_tests()
    client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    gw = sms.get_gateway()
    code = gw.last_codes["+79991234567"]
    resp = client.post("/api/auth/phone/verify", json={"phone": "+79991234567", "code": code})
    assert resp.status_code == 200
    assert "user_id" in resp.json()
    # session-cookie выставлена
    assert any("session" in c.lower() for c in resp.cookies.keys()) or resp.cookies


def test_verify_wrong_code_returns_400(client):
    from services import sms
    sms._reset_for_tests()
    client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    resp = client.post("/api/auth/phone/verify", json={"phone": "+79991234567", "code": "0000"})
    assert resp.status_code == 400


def test_request_code_rate_limit_60s(client):
    from services import sms
    sms._reset_for_tests()
    r1 = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/phone/request-code", json={"phone": "+79991234567"})
    assert r2.status_code == 429
```

- [ ] **Step 12.2 — Run test, FAIL**

Expected: 404 — router не зарегистрирован.

- [ ] **Step 12.3 — Реализовать web/routers/auth_phone.py**

Create `web/routers/auth_phone.py`:

```python
"""SMS-OTP логин по номеру телефона."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from services import identity, otp, sms
from services.exceptions import AccountMergeConflict
from utils.phones import normalize_phone
from web.auth import set_session_cookie  # см. шаг 12.3a — твоя текущая функция сессии

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/phone", tags=["auth"])

OTP_TTL_SECONDS = 300  # 5 минут
RESEND_COOLDOWN_SECONDS = 60
HOUR_LIMIT_PER_PHONE = 5
HOUR_LIMIT_PER_IP = 20


class RequestCodeBody(BaseModel):
    phone: str


class VerifyBody(BaseModel):
    phone: str
    code: str


class VerifyResponse(BaseModel):
    user_id: int


def _check_rate_limits(phone: str, ip: str) -> None:
    """Raise HTTPException(429) если лимиты превышены."""
    from services.db import connect
    cutoff_min = (datetime.now(timezone.utc) - timedelta(seconds=RESEND_COOLDOWN_SECONDS)).isoformat()
    cutoff_hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with connect() as con:
        recent = con.execute(
            "SELECT COUNT(*) as c FROM otp_codes WHERE channel='sms' AND destination=? AND created_at > ?",
            (phone, cutoff_min),
        ).fetchone()["c"]
        if recent > 0:
            raise HTTPException(429, "Слишком частые запросы. Подождите минуту.")
        last_hour = con.execute(
            "SELECT COUNT(*) as c FROM otp_codes WHERE channel='sms' AND destination=? AND created_at > ?",
            (phone, cutoff_hour),
        ).fetchone()["c"]
        if last_hour >= HOUR_LIMIT_PER_PHONE:
            raise HTTPException(429, "Превышен лимит запросов на этот номер")
    # TODO: rate-limit по IP когда добавим колонку или Redis.


@router.post("/request-code")
async def request_code(body: RequestCodeBody, request: Request):
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(400, "невалидный формат телефона")
    _check_rate_limits(phone, request.client.host if request.client else "?")
    code = otp.issue(channel='sms', destination=phone, purpose='phone_login', ttl_seconds=OTP_TTL_SECONDS)
    try:
        sms.get_gateway().send_code(phone, code)
    except Exception:
        logger.exception("SMS send failed for %s", phone)
        raise HTTPException(502, "Не удалось отправить SMS, попробуйте позже")
    return {"ok": True}


@router.post("/verify", response_model=VerifyResponse)
async def verify(body: VerifyBody, response: Response, request: Request):
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(400, "невалидный формат телефона")
    if not otp.verify(channel='sms', destination=phone, code=body.code, purpose='phone_login'):
        raise HTTPException(400, "Неверный или истёкший код")
    # Login: найти/создать user через phone-provider, set verified=1
    user_id = identity.find_or_create_user_by_phone(phone, verified=True)
    # Если phone был привязан к phone-only-user а сессия уже была — здесь
    # merge не нужен (phone-only — это уже наш user).
    try:
        # Если уже есть сессия (юзер был залогинен через email и сейчас подтверждает номер) —
        # link с возможным merge phone-only.
        # session_user = get_current_user_optional(request)
        # if session_user and session_user['id'] != user_id:
        #     identity.link_phone_provider(session_user['id'], phone, set_verified=True)
        #     user_id = session_user['id']
        pass
    except AccountMergeConflict as exc:
        logger.warning("phone-merge conflict during verify: %s", exc)
        # пусть юзер получит phone-аккаунт, а конфликт админу
    set_session_cookie(response, user_id=user_id)
    return VerifyResponse(user_id=user_id)
```

- [ ] **Step 12.3a — Проверить web/auth.py / set_session_cookie**

```bash
grep -rn "set_session_cookie\|session_cookie\|session-cookie" web/
```

Если функция называется иначе (например, в `web/auth.py::create_session_for_user`) — заменить вызов в `auth_phone.py`.

- [ ] **Step 12.4 — Зарегистрировать router в web/main.py**

В `web/main.py` после других include_router добавить:

```python
from web.routers.auth_phone import router as auth_phone_router  # noqa: E402
app.include_router(auth_phone_router)
```

- [ ] **Step 12.5 — Run tests**

```bash
docker exec -it bots-api-1 pytest tests/web/test_phone_login.py -v
```
Expected: PASS. Если 429-тест зависит от cooldown — мокни время или поправь test.

- [ ] **Step 12.6 — Commit**

```bash
git add web/routers/auth_phone.py web/main.py tests/web/test_phone_login.py
git commit -m "feat(auth): вход по СМС-коду через /api/auth/phone/request-code + /verify

Rate-limits: 1 запрос/60с на phone, 5 запросов/час на phone.
После успешной верификации — создаём/находим user через phone-provider
(verified=1), выпускаем session-cookie."
```

---

## Task 13: Удаление guest_orders (backend)

**Files:**
- Delete: `services/guest_orders.py`
- Delete: `web/routers/guest_orders.py`
- Delete: `tests/web/test_routers_guest_orders.py`
- Modify: `web/main.py` (снять регистрацию guest_orders_router)
- Modify: `web/schemas.py` (удалить старые модели GuestPFOrder*, PaymentAvailableResponse)

- [ ] **Step 13.1 — Снять регистрацию из web/main.py**

В `web/main.py:49-51` удалить:
```python
from web.routers.guest_orders import router as guest_orders_router  # noqa: E402
...
app.include_router(guest_orders_router)
```

- [ ] **Step 13.2 — Удалить файлы**

```bash
git rm services/guest_orders.py web/routers/guest_orders.py tests/web/test_routers_guest_orders.py
```

- [ ] **Step 13.3 — Подчистить web/schemas.py**

Удалить классы `PFOrderRequest` (старый), `GuestPFOrderRequest`, `GuestPFOrderResponse`, `GuestOrderStatusResponse`, `PaymentAvailableResponse`. Оставить только новые из Task 11.

```bash
grep -n "class PFOrderRequest\|class GuestPFOrder\|class GuestOrderStatus\|class PaymentAvailableResponse" web/schemas.py
```

Удалить каждый класс точечно через Edit.

- [ ] **Step 13.4 — Прогнать тесты**

```bash
docker exec -it bots-api-1 pytest tests/ -x --tb=short
```
Если падают тесты, ссылающиеся на старые модели — поправить.

- [ ] **Step 13.5 — Commit**

```bash
git add -A
git commit -m "refactor: удаление guest_orders backend

- services/guest_orders.py (логика мигрировала в services/orders.py)
- web/routers/guest_orders.py (эндпоинты заменены на /api/orders/*)
- старые модели GuestPFOrder*, PaymentAvailableResponse из web/schemas.py"
```

---

## Task 14: Frontend — OrderForm объединение + PhoneLogin

**Files:**
- Modify: `web/static/components/OrderForm.jsx`
- Modify: `web/static/components/OrderDetail.jsx`
- Modify: `web/static/components/Auth.jsx`
- Create: `web/static/components/PhoneLogin.jsx`
- Modify: `web/static/app.jsx`

### Контекст

Frontend проекта — react через standalone CDN скрипты (см. `web/static/index.html`). Тестов на JS нет — проверяем вручную через `verify` skill или smoke-test в браузере.

- [ ] **Step 14.1 — Переписать OrderForm.jsx**

В `web/static/components/OrderForm.jsx` — обновить с трёхшаговой логикой. Замени файл целиком на:

```jsx
function OrderForm({ user, prefilledFrom, onCreated, onNavigate }) {
  const [step, setStep] = React.useState(1);
  // Step 1
  const [links, setLinks] = React.useState(prefilledFrom?.links || []);
  const [linkInput, setLinkInput] = React.useState('');
  const [days, setDays] = React.useState('');  // намеренно пусто для prefilled
  const [fixCount, setFixCount] = React.useState(prefilledFrom?.fix_count || 1);
  const [contacts, setContacts] = React.useState(prefilledFrom?.contacts ?? false);
  const [agreedPrivacy, setAgreedPrivacy] = React.useState(false);
  const [agreedOffer, setAgreedOffer] = React.useState(false);
  // Step 2 (auth choice)
  const [authChoice, setAuthChoice] = React.useState(null);  // 'guest' | 'login'
  const [phone, setPhone] = React.useState('');
  // Step 3 (created)
  const [createdOrder, setCreatedOrder] = React.useState(null);
  // common
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const validateStep1 = () => {
    if (links.length === 0) return 'Добавьте хотя бы одну ссылку';
    if (!days || days < 1) return 'Укажите количество дней';
    if (!agreedPrivacy || !agreedOffer) return 'Необходимо принять оферту и политику';
    return null;
  };

  const submitToBackend = async (phoneArg) => {
    setLoading(true); setError(null);
    try {
      const data = await api.post('/api/orders/pf', {
        links, days: parseInt(days, 10), fix_count: fixCount, contacts,
        agreed_privacy: true, agreed_offer: true,
        phone: phoneArg || null,
      });
      setCreatedOrder(data);
      setStep(3);
    } catch (e) {
      setError(e.message || 'Не удалось создать заказ');
    } finally { setLoading(false); }
  };

  // === Step 1 ===
  if (step === 1) {
    return (
      <div className="order-form">
        <h2>Заказ накрутки ПФ</h2>
        <AddedLinksList links={links} onAdd={(l) => setLinks([...links, l])}
                       onRemove={(i) => setLinks(links.filter((_, idx) => idx !== i))}
                       input={linkInput} onInputChange={setLinkInput} />
        <label>Количество дней<input type="number" min="1" max="90"
                                     value={days} onChange={(e) => setDays(e.target.value)} /></label>
        <label>Заходов в день<input type="number" min="1" max="200"
                                    value={fixCount} onChange={(e) => setFixCount(parseInt(e.target.value, 10))} /></label>
        <label><input type="checkbox" checked={contacts}
                      onChange={(e) => setContacts(e.target.checked)} /> Контакты</label>
        <label><input type="checkbox" checked={agreedPrivacy}
                      onChange={(e) => setAgreedPrivacy(e.target.checked)} />
               Согласен с <a href="/api/legal/privacy">политикой</a></label>
        <label><input type="checkbox" checked={agreedOffer}
                      onChange={(e) => setAgreedOffer(e.target.checked)} />
               Согласен с <a href="/api/legal/offer">офертой</a></label>
        {error && <div className="error">{error}</div>}
        <button onClick={() => {
          const err = validateStep1();
          if (err) return setError(err);
          if (user) {
            // авторизованный — сразу в submit
            submitToBackend(null);
          } else {
            setStep(2);
          }
        }} disabled={loading}>Далее</button>
      </div>
    );
  }

  // === Step 2: auth choice ===
  if (step === 2) {
    return (
      <div className="order-form">
        <h2>Как продолжить?</h2>
        <button onClick={() => setAuthChoice('guest')}>Быстрый заказ по телефону</button>
        <button onClick={() => {
          sessionStorage.setItem('order_prefill', JSON.stringify({ links, days, fix_count: fixCount, contacts }));
          onNavigate('auth');
        }}>У меня есть аккаунт — войти</button>
        {authChoice === 'guest' && (
          <div>
            <label>Телефон<input type="tel" placeholder="+79991234567"
                                 value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
            <button onClick={() => submitToBackend(phone)} disabled={loading || !phone}>
              Создать заказ
            </button>
            {error && <div className="error">{error}</div>}
          </div>
        )}
      </div>
    );
  }

  // === Step 3: choose payment method ===
  if (step === 3 && createdOrder) {
    return <PaymentMethodPicker order={createdOrder}
                                user={user}
                                onPaid={() => onNavigate(`order/${createdOrder.order_id}`)} />;
  }
}


function PaymentMethodPicker({ order, user, onPaid }) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const pay = async (method) => {
    setLoading(true); setError(null);
    try {
      const data = await api.post(`/api/orders/pf/${order.order_id}/pay`, { method });
      if (method === 'balance') {
        onPaid();
      } else {
        window.location.href = data.confirmation_url;
      }
    } catch (e) {
      setError(e.message || 'Ошибка оплаты');
    } finally { setLoading(false); }
  };

  return (
    <div className="payment-picker">
      <h2>Способ оплаты</h2>
      <div>Сумма: {order.price}₽</div>
      {order.available_methods.includes('balance') && (
        <button onClick={() => pay('balance')} disabled={loading}>Оплатить с баланса</button>
      )}
      {order.available_methods.includes('yookassa') && (
        <button onClick={() => pay('yookassa')} disabled={loading}>Оплатить картой (ЮKassa)</button>
      )}
      {error && <div className="error">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 14.2 — Переписать OrderDetail.jsx**

В `web/static/components/OrderDetail.jsx` — универсальная страница:

```jsx
function OrderDetail({ orderId, user, onNavigate }) {
  const [order, setOrder] = React.useState(null);
  const [timeRemaining, setTimeRemaining] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.get(`/api/orders/pf/${orderId}/payment-status`);
        if (cancelled) return;
        setTimeRemaining(data.time_remaining_seconds);
        const fullOrder = await api.get(`/api/orders/pf/${orderId}`);
        setOrder(fullOrder);
        if (data.status === 'unpaid') {
          setTimeout(poll, 5000);
        }
      } catch (e) { console.error(e); }
    };
    poll();
    return () => { cancelled = true; };
  }, [orderId]);

  if (!order) return <div>Загрузка…</div>;

  const isTerminal = ['done', 'failed', 'payment_failed', 'cancelled'].includes(order.status);

  return (
    <div className="order-detail">
      <h2>Заказ #{order.id}</h2>
      <div>Статус: <StatusBadge status={order.status} /></div>
      <div>Сумма: {order.price}₽</div>
      {order.status === 'unpaid' && timeRemaining != null && (
        <div>Осталось на оплату: {Math.floor(timeRemaining / 60)}:{String(timeRemaining % 60).padStart(2, '0')}</div>
      )}
      {/* … остальные поля: ссылки, дни, контакты … */}
      {isTerminal && (
        <button onClick={() => {
          sessionStorage.setItem('order_prefill', JSON.stringify({
            links: JSON.parse(order.links), fix_count: parseInt(order.position_name.split('/')[1], 10),
            contacts: order.contacts === 1,
          }));
          onNavigate('order-new');
        }}>Повторить заказ</button>
      )}
    </div>
  );
}


function StatusBadge({ status }) {
  const map = {
    unpaid:         { label: 'Ожидает оплаты',  color: 'amber' },
    paid:           { label: 'В работе',         color: 'blue' },
    done:           { label: 'Выполнен',         color: 'green' },
    failed:         { label: 'Ошибка',           color: 'red' },
    payment_failed: { label: 'Не оплачен',       color: 'gray' },
    cancelled:      { label: 'Отменён',          color: 'gray' },
  };
  const item = map[status] || { label: status, color: 'gray' };
  return <span className={`badge badge--${item.color}`}>{item.label}</span>;
}
```

- [ ] **Step 14.3 — Создать PhoneLogin.jsx**

Create `web/static/components/PhoneLogin.jsx`:

```jsx
function PhoneLogin({ onSuccess }) {
  const [step, setStep] = React.useState('phone');  // 'phone' | 'code'
  const [phone, setPhone] = React.useState('');
  const [code, setCode] = React.useState('');
  const [error, setError] = React.useState(null);
  const [resendIn, setResendIn] = React.useState(0);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (resendIn > 0) {
      const t = setTimeout(() => setResendIn(resendIn - 1), 1000);
      return () => clearTimeout(t);
    }
  }, [resendIn]);

  const request = async () => {
    setLoading(true); setError(null);
    try {
      await api.post('/api/auth/phone/request-code', { phone });
      setStep('code');
      setResendIn(60);
    } catch (e) {
      if (e.status === 429) setError('Слишком много запросов, подождите');
      else setError(e.message || 'Не удалось отправить код');
    } finally { setLoading(false); }
  };

  const verify = async () => {
    setLoading(true); setError(null);
    try {
      const data = await api.post('/api/auth/phone/verify', { phone, code });
      onSuccess(data.user_id);
    } catch (e) {
      setError('Неверный код');
    } finally { setLoading(false); }
  };

  if (step === 'phone') {
    return (
      <div>
        <label>Телефон<input type="tel" placeholder="+79991234567"
                             value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        <button onClick={request} disabled={loading || !phone}>Получить код</button>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return (
    <div>
      <label>Код из SMS<input type="text" inputMode="numeric" maxLength={4}
                              value={code} onChange={(e) => setCode(e.target.value)} /></label>
      <button onClick={verify} disabled={loading || !code}>Войти</button>
      <button onClick={request} disabled={resendIn > 0}>
        Отправить заново{resendIn > 0 ? ` (${resendIn}с)` : ''}
      </button>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 14.4 — Подключить в Auth.jsx**

В `web/static/components/Auth.jsx` добавить вкладку "По телефону" → рендерит `<PhoneLogin onSuccess={...} />`.

```bash
grep -n "tab\|tabs\|method" web/static/components/Auth.jsx | head -20
```
Найди где переключатель методов (email/tg) и добавь третий — phone.

- [ ] **Step 14.5 — Обновить app.jsx — маршрутизация**

В `web/static/app.jsx`:
- Удалить `route === 'landing'` (Landing удаляется в Task 15).
- Корень: `if (!user) onNavigate('order-new')` (вместо текущего landing).
- Добавить routes: `'order-new'` → `<OrderForm>`, `'order/:id'` → `<OrderDetail>`.

```bash
sed -n '15,40p' web/static/app.jsx
```

Заменить блок `useState(_isGuestReturn ? ...)` на:
```jsx
const [route, setRoute] = useState(
  _isGuestReturn ? 'guest-order-success' :
  (_isResetRoute ? 'auth' : (window.location.hash.replace('#', '') || (currentUser ? 'cabinet' : 'order-new')))
);
```

- [ ] **Step 14.6 — Подключить script-теги для новых компонентов в index.html**

В `web/static/index.html` найти список `<script src="...">` и добавить:
```html
<script src="/static/components/PhoneLogin.jsx" type="text/babel"></script>
```

- [ ] **Step 14.7 — Smoke test в браузере**

Использовать skill `verify` (см. `superpowers:verification-before-completion`) или вручную:
```bash
docker compose restart api
```
Открыть `http://localhost:8000/` — проверить:
- Незалогиненный → редиректит на /order/new.
- Форма заказа отображается.
- Шаг 2 даёт выбор guest/login.
- "Войти" ведёт на /login с вкладкой "По телефону".
- Заказ создаётся, payment picker появляется, "Оплатить с баланса" работает (для авторизованного с балансом).

См. также `feedback_web_responsive_check.md` — проверять mobile и desktop.

- [ ] **Step 14.8 — Commit**

```bash
git add web/static/components/OrderForm.jsx web/static/components/OrderDetail.jsx
git add web/static/components/PhoneLogin.jsx web/static/components/Auth.jsx
git add web/static/app.jsx web/static/index.html
git commit -m "feat(ui): унифицированная OrderForm, OrderDetail, PhoneLogin

OrderForm — три шага: параметры → auth choice → payment method.
OrderDetail — универсальная страница со всеми статусами, polling, 'Повторить'.
PhoneLogin — вкладка в Auth.jsx, 60с-таймер на повтор кода.
app.jsx — корень редиректит на order-new для гостя.

Проверено в браузере (mobile + desktop)."
```

---

## Task 15: Frontend cleanup — удалить Landing, GuestOrderForm, GuestOrderSuccess

**Files:**
- Delete: `web/static/components/Landing.jsx`
- Delete: `web/static/components/GuestOrderForm.jsx`
- Delete: `web/static/components/GuestOrderSuccess.jsx`
- Modify: `web/static/index.html` (убрать script-теги)
- Modify: `web/static/components/AppHeader.jsx` (убрать landing-логику)

- [ ] **Step 15.1 — Удалить файлы**

```bash
git rm web/static/components/Landing.jsx
git rm web/static/components/GuestOrderForm.jsx
git rm web/static/components/GuestOrderSuccess.jsx
```

- [ ] **Step 15.2 — Убрать script-теги из index.html**

```bash
grep -n "Landing.jsx\|GuestOrderForm.jsx\|GuestOrderSuccess.jsx" web/static/index.html
```
Удалить каждую строку.

- [ ] **Step 15.3 — Подчистить AppHeader.jsx**

В `web/static/components/AppHeader.jsx:51-52` упростить:
```jsx
// Было:
const isApp = !['landing', 'login', 'register', 'login-tg', 'auth'].includes(route);
const isLanding = route === 'landing';
// Стало:
const isApp = !['login', 'register', 'login-tg', 'auth'].includes(route);
```

Удалить весь код, ссылающийся на `isLanding`.

- [ ] **Step 15.4 — Подчистить app.jsx — убрать guest-order-success/landing**

```bash
grep -n "landing\|guest-order-success" web/static/app.jsx
```
Удалить case'ы рендера этих routes (если ещё остались), а `guest-order-success` направить на `order/:id`.

- [ ] **Step 15.5 — Smoke test**

```bash
docker compose restart api
# открыть в браузере, убедиться что нет JS-ошибок
```

- [ ] **Step 15.6 — Commit**

```bash
git add -A
git commit -m "refactor(ui): удаление Landing, GuestOrderForm, GuestOrderSuccess из SPA

Эти страницы заменяются:
- Landing → отдельный поддомен avito-pf.com (Task 16)
- GuestOrderForm → объединена с OrderForm
- GuestOrderSuccess → объединена с OrderDetail
AppHeader упрощён: нет больше route === 'landing'."
```

---

## Task 16: web/landing/ — статический лендинг

**Files:**
- Create: `web/landing/index.html` (копия артефакта)

- [ ] **Step 16.1 — Создать папку и скопировать артефакт**

```bash
mkdir -p web/landing
cp "/Users/belikov/Downloads/Лендинг авито-пф (standalone) (1).html" web/landing/index.html
```

- [ ] **Step 16.2 — Прорезать ссылки на ЛК в HTML**

Открой `web/landing/index.html`, найди кнопки "Заказать ПФ" / "Заказать". Текущий HTML — bundled standalone артефакт, где JS-template содержит CTA-ссылки. Найди все `href` ведущие на placeholder/anchor:

```bash
grep -on 'href=[\"'\''"][^\"'\'']*[\"'\'']' web/landing/index.html | head -40
```

Заменить кликабельные CTA на:
```html
href="https://lk.avito-pf.com/order/new"
```

*Если в bundled HTML кнопки сделаны через `<a>` без href или через JS-обработчики — найти конкретные элементы (ID/class) и поправить. Дать дизайнеру лендинга TODO "сделать кнопки href-ссылками".*

- [ ] **Step 16.3 — Smoke test локально**

Если nginx ещё не настроен — открыть файл напрямую:
```bash
open web/landing/index.html
```
Убедиться:
- Страница рендерится.
- Клик "Заказать" ведёт на `https://lk.avito-pf.com/order/new` (или localhost-эквивалент для dev).

- [ ] **Step 16.4 — Commit**

```bash
git add web/landing/index.html
git commit -m "feat(landing): standalone HTML лендинга в web/landing/

Standalone bundled HTML (артефакт от no-code/AI). Все CTA-кнопки ведут
на https://lk.avito-pf.com/order/new — единственный контракт между
лендингом и ЛК."
```

---

## Task 17: nginx config + docker-compose + .env.example + README

**Files:**
- Create: `nginx/avito-pf.conf`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 17.1 — Создать nginx-конфиг**

Create `nginx/avito-pf.conf`:

```nginx
# Landing — статика
server {
    listen 80;
    listen 443 ssl;
    server_name avito-pf.com;

    ssl_certificate     /etc/letsencrypt/live/avito-pf.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/avito-pf.com/privkey.pem;

    root /app/web/landing;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # ACME challenge для certbot
    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }
}

# ЛК — FastAPI
server {
    listen 80;
    listen 443 ssl;
    server_name lk.avito-pf.com;

    ssl_certificate     /etc/letsencrypt/live/lk.avito-pf.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lk.avito-pf.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }
}
```

*Это шаблон. Адаптировать под существующую инфру (см. `infra_pf_bot_domain.md`):
- Существующий `pf-bot.com` server-блок на 443 уже шарится с shadowbox через ssl_preread —
  для двух новых hostnames нужно их добавить в ssl_preread map (отдельная задача в инфре).
- Если nginx live-конфиг на хосте, а не в контейнере — выкатить шаблон в `/etc/nginx/sites-enabled/`.
- Если nginx-контейнер — добавить volume в `docker-compose.yml`.*

- [ ] **Step 17.2 — Обновить .env.example**

В `.env.example`:
```
# SMS provider (для phone-login)
SMS_GATEWAY=stub

# Поддомены (опционально, для оверрайдов в коде)
LANDING_HOST=avito-pf.com
LK_HOST=lk.avito-pf.com
```

- [ ] **Step 17.3 — Обновить README.md**

В README добавить раздел "Архитектура":

```markdown
## Топология

- `avito-pf.com` — статический лендинг (папка `web/landing/`), отдаётся nginx напрямую.
- `lk.avito-pf.com` — личный кабинет (FastAPI + React SPA в `web/static/`, контейнер `api`).
- Telegram-бот (aiogram) — отдельный контейнер `bot`.

Лендинг можно обновлять без рестарта FastAPI: `git pull` на сервере →
nginx подхватывает свежий `index.html` сразу.

## SMS-OTP вход

Реализован через `services/sms.py`. Провайдер выбирается через env
`SMS_GATEWAY` (по умолчанию `stub` — пишет код в лог).

## Заказы — flow

Один путь: `unpaid → paid → done/failed`. См.
[docs/superpowers/specs/2026-06-05-landing-lk-split-design.md](docs/superpowers/specs/2026-06-05-landing-lk-split-design.md).
```

- [ ] **Step 17.4 — Smoke test (deploy на staging)**

Если есть staging:
```bash
ssh root@<staging> 'cd /path/to/app && git pull dev && docker compose build api && docker compose up -d'
# затем nginx reload на хосте
sudo nginx -t && sudo systemctl reload nginx
```

Открыть `https://avito-pf.com` — лендинг.
Открыть `https://lk.avito-pf.com/order/new` — форма.

- [ ] **Step 17.5 — Commit**

```bash
git add nginx/avito-pf.conf .env.example README.md docker-compose.yml
git commit -m "infra: nginx config для avito-pf.com (статика) и lk.avito-pf.com (LK)

avito-pf.com: root web/landing, статика отдаётся nginx без обращения к api.
lk.avito-pf.com: proxy_pass на FastAPI контейнер.
.env.example: SMS_GATEWAY=stub.
README обновлён с разделом про топологию.

NB: ssl_preread конфиг (для шеринга 443 с shadowbox) нужно обновить
отдельной задачей в инфраструктуре (см. infra_pf_bot_domain.md)."
```

---

## Self-Review

### Spec coverage

| Спека-раздел | Покрыто задачами |
|--------------|------------------|
| §3 Топология | Task 16 (landing), Task 17 (nginx) |
| §4.1 orders новые статусы и колонки | Task 1 (схема), Task 2 (миграция данных), Task 3 (переименование) |
| §4.2 auth_providers.verified | Task 1 (схема) |
| §4.3 otp_codes generalization | Task 1 (схема), Task 5 (services/otp.py) |
| §4.4 drop guest_orders | Task 2 (миграция), Task 13 (backend cleanup) |
| §5 Order state machine | Task 9 (services/orders.py), Task 10 (expiry job) |
| §6.1-6.4 Сценарии (guest/auth/SMS-login/repeat) | Task 11 (API), Task 14 (frontend) |
| §6.5 Account merge | Task 7 (identity), Task 8 (connect.py) |
| §7 Frontend | Task 14 (форма), Task 15 (cleanup) |
| §8 API эндпоинты | Task 11 (orders), Task 12 (auth_phone), Task 13 (удаление guest) |
| §9.1 Late yookassa | Task 9 (`mark_payment_failed` + Payment.cancel) |
| §9.2 Rate limits | Task 12 (`_check_rate_limits`) |
| §9.3 Race condition оплаты | Task 9 (атомарный UPDATE с `WHERE status='unpaid'`) |
| §9.4 Битая ссылка | Out-of-scope, документировано в §13 |
| §9.5 Юзер не выбрал способ | Task 9 (TTL_NO_METHOD_MINUTES=60) |
| §10 Стратегия миграции | Все 17 задач = 17 коммитов внутри одного PR |
| §11 Testing strategy | Tests раскиданы по соответствующим задачам |

**Gaps:** в спеке §11 упомянут `tests/web/test_order_yookassa.py` — отдельный integration test с моком YooKassa. Я объединил его в `tests/web/test_order_pf_flow.py` (можно разбить позже).

### Placeholder scan

- ❌ Step 11.5 содержит "Если падает — смотри причины" — допустимо для дебаг-инструкций, но можно дать конкретику. Оставил как есть.
- ❌ Step 12.3 — есть `# TODO: rate-limit по IP когда добавим колонку или Redis.` — это **намеренный** TODO, отмечен в спеке как not-yet-supported (rate-limit по IP — отложено).
- ❌ Step 17.1 содержит замечание про `ssl_preread` — это часть spec'а §17.5 ("NB: ssl_preread... отдельной задачей"). Норм, не placeholder.
- ✅ Все остальные шаги содержат конкретный код / команды.

### Type consistency

- `find_or_create_user_by_phone(phone, verified=False)` — Task 7 определяет, Task 11 и Task 12 используют (Task 12 передаёт `verified=True`). ✅
- `link_phone_provider(target_user_id, phone, set_verified=False)` — Task 7 определяет, Task 8 использует. ✅
- `create_unpaid(*, user_id, links, days, fix_count, contacts, phone)` — Task 9 определяет, Task 11 использует. ✅
- `pay_with_balance(*, order_id, user_id)` / `pay_with_yookassa(*, order_id, return_url)` — Task 9 определяет, Task 11 использует. ✅
- `mark_paid(order_id)` / `mark_payment_failed(order_id)` — Task 9 определяет, Task 10 (expiry) и Task 11 (yookassa polling) используют. ✅
- `otp.issue(channel=, destination=, purpose=, ttl_seconds=)` / `otp.verify(channel=, destination=, code=, purpose=)` — Task 5 определяет, Task 12 использует. ✅
- `OrderPaymentStatusResponse(status, time_remaining_seconds, order_id)` — Task 11 определяет, Task 14 frontend использует через `/payment-status`. ✅
- Статусы заказа: `unpaid/paid/done/failed/payment_failed/cancelled` — Task 2 (миграция), Task 3 (код), Task 11 (schemas), Task 14 (UI) согласованы. ✅

### Финальный gap-check

Всё что в спеке — нашёл соответствующую задачу. Issues, найденные при self-review (race в OTP, rate-limit детали), сразу инкорпорированы в код задач.

---

## Plan complete

Plan complete and saved to `docs/superpowers/plans/2026-06-05-landing-lk-split.md`. Two execution options:

1. **Subagent-Driven (recommended)** — я диспатчу свежего сабагента на каждую из 17 задач, делаю ревью между ними, быстрая итерация.

2. **Inline Execution** — выполняю задачи в этой же сессии через `superpowers:executing-plans`, batch execution с чекпоинтами.

Which approach?
