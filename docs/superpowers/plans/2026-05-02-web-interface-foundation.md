# Web Interface Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Извлечь refill-flow в чистый сервисный слой с тестами и поднять минимальный веб-интерфейс (FastAPI) с авторизацией через Telegram Login Widget и эндпоинтом для пополнения баланса. После этого этапа бот и веб работают с одной БД через единые сервисы.

**Architecture:** Сервисы — чистый Python+SQLite в пакете `services/`. Бот (aiogram 2.25, polling) и FastAPI (`web/`) импортируют сервисы напрямую и работают в одном Python-процессе через `asyncio.create_task` в `on_startup` aiogram. Авторизация в вебе — проверка HMAC от bot-token поверх данных Telegram Login Widget, выдача JWT. SQLite сохраняем как есть; миграция на Postgres — отдельный план.

**Tech Stack:** Python 3.12+, aiogram 2.25 (already), FastAPI, uvicorn, pytest + pytest-asyncio, httpx (TestClient), PyJWT, существующий `yookassa` SDK.

**Out of scope (для следующих планов):**
- Перенос orders / promocodes / reviews / SEO в сервисы
- Веб-формы для всех остальных бизнес-операций
- Миграция на Postgres
- Telegram Mini App (берём более простой Login Widget)
- Очередь фоновых задач (yookassa-polling сейчас живёт в том же loop через `asyncio.sleep`, в Phase 1 не трогаем)

**File Structure (создаётся в этом плане):**

```
services/
  __init__.py
  exceptions.py        # ServiceError, InsufficientBalance, UserNotFound, PaymentError
  db.py                # Контекст-менеджер соединений с dict_factory + извлечённая schema
  balance.py           # BalanceService — атомарные credit/debit/get_balance
  refill.py            # RefillService — yookassa + finalize с реф.бонусом
web/
  __init__.py
  config.py            # JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS, BOT_TOKEN, WEB_HOST, WEB_PORT
  main.py              # FastAPI app + /api/health
  auth.py              # verify_telegram_auth, create_jwt, decode_jwt
  deps.py              # get_current_user_id (FastAPI Depends)
  schemas.py           # Pydantic-модели (AuthRequest, AuthResponse, Profile, RefillRequest, ...)
  routers/
    __init__.py
    auth.py            # POST /api/auth/telegram, GET /api/me
    refill.py          # POST /api/refill, GET /api/refill/{payment_id}/status
  static/
    index.html         # Главная с Telegram Login Widget
    cabinet.html       # Личный кабинет: баланс + форма пополнения
tests/
  __init__.py
  conftest.py          # tmp_db fixture, monkeypatch path_database
  unit/
    __init__.py
    test_db.py
    test_balance.py
    test_refill.py
  web/
    __init__.py
    test_auth.py
    test_routers_auth.py
    test_routers_refill.py
pyproject.toml         # pytest config + tool config
docs/superpowers/plans/2026-05-02-web-interface-foundation.md  # этот файл
```

**Файлы, которые модифицируются:**
- `requirements.txt` — добавить fastapi/uvicorn/pytest/httpx/pyjwt
- `data/example.config.py` — добавить JWT_SECRET, WEB_HOST, WEB_PORT
- `__main__.py` — запуск uvicorn рядом с polling через `on_startup`
- `handlers/user_functions.py:672-753` — refill-handler делегирует в `RefillService`
- `utils/sqlite3.py` — извлечь SQL-схему в отдельную функцию `get_schema_statements()`, чтобы переиспользовать в тестах

---

## Task 1: Настроить зависимости и pytest

**Files:**
- Modify: `requirements.txt`
- Create: `pyproject.toml`

- [ ] **Step 1: Добавить новые зависимости в requirements.txt**

Открыть `requirements.txt` и добавить в конец (сохранив алфавитный порядок там, где он есть):

```
fastapi==0.115.0
uvicorn==0.30.6
PyJWT==2.9.0
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
itsdangerous==2.2.0
```

Примечание: `httpx` нужен для `fastapi.testclient.TestClient`. `itsdangerous` нужен для FastAPI middleware (на будущее, не строго обязателен сейчас, но удобен).

- [ ] **Step 2: Создать pyproject.toml с pytest-конфигом**

Создать файл `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
filterwarnings = [
    "ignore::DeprecationWarning:aiogram.*",
]
addopts = "-ra -q"

[tool.pytest.ini_options.markers]
slow = "marks tests as slow"
```

- [ ] **Step 3: Установить зависимости в активном venv**

Run:
```bash
pip install -r requirements.txt
```
Expected: установка всех новых пакетов без ошибок. Если venv активен и Python 3.12+, всё проходит.

- [ ] **Step 4: Проверить что pytest запускается (без тестов)**

Run:
```bash
pytest --collect-only
```
Expected: `no tests ran` или похожее, без ошибок конфигурации.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "chore: add fastapi/pytest deps and pytest config"
```

---

## Task 2: Извлечь SQL-схему БД для переиспользования в тестах

**Files:**
- Modify: `utils/sqlite3.py:688-779` (функция `create_db`)
- Test: `tests/unit/test_db.py` (создаётся в Task 3)

Функция `create_db()` сейчас inline создаёт схему. Чтобы переиспользовать схему в тестовых фикстурах, вынесем CREATE TABLE statements в отдельную функцию.

- [ ] **Step 1: Прочитать текущий код**

Run:
```bash
sed -n '688,779p' utils/sqlite3.py
```
Expected: видим текущую функцию `create_db` с шестью таблицами: users, refills, orders, promocodes, reviews, delreviews.

- [ ] **Step 2: Заменить тело create_db на вызов общей функции**

Открыть `utils/sqlite3.py` и заменить функцию `create_db` (строки 688–779) на:

```python
def get_schema_statements() -> list[tuple[str, str, int]]:
    """Возвращает список (table_name, create_sql, expected_column_count).

    Используется create_db() для бутстрапа продовой БД и tests.conftest для tmp-БД.
    """
    return [
        (
            "users",
            "CREATE TABLE users("
            "id INTEGER PRIMARY KEY,"
            "user_name TEXT,"
            "first_name TEXT,"
            "balance INTEGER DEFAULT 0,"
            "reg_date TIMESTAMP,"
            "ref_user_name TEXT,"
            "ref_id INTEGER,"
            "is_vip BOOLEN,"
            "magic TEXT,"
            "referals TEXT)",
            10,
        ),
        (
            "refills",
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            4,
        ),
        (
            "orders",
            "CREATE TABLE orders("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "price INTEGER,"
            "position_name TEXT,"
            "status TEXT,"
            "links TEXT,"
            "date TIMESTAMP,"
            "contacts BOOLEN DEFAULT False,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            9,
        ),
        (
            "promocodes",
            "CREATE TABLE promocodes("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "code TEXT NOT NULL,"
            "price INTEGER,"
            "isactivated BOOL DEFAULT FALSE,"
            "prom_users TEXT)",
            5,
        ),
        (
            "reviews",
            "CREATE TABLE reviews ("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "price INTEGER, "
            "service TEXT, "
            "status TEXT, "
            "date TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            6,
        ),
        (
            "delreviews",
            "CREATE TABLE delreviews ("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "price INTEGER, "
            "service TEXT, "
            "link TEXT, "
            "status TEXT, "
            "date TIMESTAMP, "
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            7,
        ),
        (
            "settings",
            "CREATE TABLE IF NOT EXISTS settings("
            "parametr TEXT PRIMARY KEY,"
            "description TEXT,"
            "value TEXT)",
            3,
        ),
        (
            "strings",
            "CREATE TABLE IF NOT EXISTS strings("
            "parametr TEXT PRIMARY KEY,"
            "description TEXT,"
            "value TEXT)",
            3,
        ),
    ]


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
```

Примечание: добавлены таблицы `settings` и `strings` (`CREATE TABLE IF NOT EXISTS`) — они в проде создаются вне `create_db` (см. `add_setting_to_base`/`add_string_to_base`, у которых INSERT может упасть если таблицы нет). Для tmp-БД мы хотим, чтобы они тоже создавались. Прод-поведение не меняется — `IF NOT EXISTS` no-op.

- [ ] **Step 3: Запустить бот руками для регресса**

Run:
```bash
python -c "from utils.sqlite3 import create_db; create_db()"
```
Expected: для существующей БД печатает `database was found (table | i/N)` для каждой таблицы; новые `settings`/`strings` — печатает found или creating; никаких трейсбэков.

- [ ] **Step 4: Commit**

```bash
git add utils/sqlite3.py
git commit -m "refactor: extract schema statements from create_db for reuse in tests"
```

---

## Task 3: Тестовая инфраструктура — фикстура tmp_db

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_db.py`

- [ ] **Step 1: Создать пустые init-файлы**

```bash
mkdir -p tests/unit tests/web
touch tests/__init__.py tests/unit/__init__.py tests/web/__init__.py
```

- [ ] **Step 2: Написать conftest с tmp_db фикстурой**

Создать `tests/conftest.py`:

```python
"""Тестовые фикстуры. Каждый тест получает изолированную SQLite-БД во временной папке.

Мы не используем in-memory БД, потому что код продакшена открывает соединение через
sqlite3.connect(path_db) на каждый запрос (см. utils/sqlite3.py), и in-memory БД у разных
соединений — разные. Файловая БД во временной папке — самый прямой путь.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from utils.sqlite3 import get_schema_statements


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Создаёт пустую БД с продакшен-схемой и подменяет path_database во всех модулях."""
    db_path = tmp_path / "test.db"

    # Создаём схему
    with sqlite3.connect(db_path) as con:
        for _table, ddl, _cols in get_schema_statements():
            con.execute(ddl)
        con.commit()

    # Подменяем путь к БД во всех уже импортированных модулях, которые его читают
    monkeypatch.setattr("data.config.path_database", str(db_path), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db_path), raising=False)

    yield db_path
```

- [ ] **Step 3: Написать smoke-тест для tmp_db**

Создать `tests/unit/test_db.py`:

```python
"""Smoke-тесты на тестовую инфраструктуру."""
import sqlite3
from pathlib import Path


def test_tmp_db_has_users_table(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("PRAGMA table_info(users)").fetchall()
    assert len(rows) == 10


def test_tmp_db_can_insert_user(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 0, "2026-05-02"),
        )
        con.commit()
        row = con.execute("SELECT id, balance FROM users WHERE id = 42").fetchone()
    assert row == (42, 0)


def test_tmp_db_isolated_per_test_a(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, "a", "A", 100, "2026-05-02"),
        )
        con.commit()


def test_tmp_db_isolated_per_test_b(tmp_db: Path) -> None:
    """Если первая фикстура утекла — тут будет 1 строка вместо 0."""
    with sqlite3.connect(tmp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 0
```

- [ ] **Step 4: Запустить тесты — должны проходить**

Run:
```bash
pytest tests/unit/test_db.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add tmp_db fixture and smoke tests for test infra"
```

---

## Task 4: services/exceptions.py — общие исключения

**Files:**
- Create: `services/__init__.py`
- Create: `services/exceptions.py`

- [ ] **Step 1: Создать пакет**

```bash
mkdir -p services
touch services/__init__.py
```

- [ ] **Step 2: Написать exceptions.py**

Создать `services/exceptions.py`:

```python
"""Общие исключения сервисного слоя.

Сервисы бросают эти исключения, а вызывающий код (бот / FastAPI) превращает их
в человеко-читаемые сообщения / HTTP-ответы.
"""


class ServiceError(Exception):
    """Базовое исключение сервисного слоя."""


class UserNotFound(ServiceError):
    """Пользователя с переданным id нет в БД."""


class InsufficientBalance(ServiceError):
    """Баланс пользователя меньше требуемой суммы."""

    def __init__(self, user_id: int, available: int, required: int) -> None:
        super().__init__(
            f"User {user_id}: balance {available} < required {required}"
        )
        self.user_id = user_id
        self.available = available
        self.required = required


class PaymentError(ServiceError):
    """Ошибка при работе с провайдером платежей (yookassa)."""
```

- [ ] **Step 3: Smoke-проверка импорта**

Run:
```bash
python -c "from services.exceptions import ServiceError, UserNotFound, InsufficientBalance, PaymentError; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add services/
git commit -m "feat(services): add common exception types"
```

---

## Task 5: services/db.py — общий слой соединений

**Files:**
- Create: `services/db.py`
- Test: `tests/unit/test_services_db.py`

Сейчас каждое CRUD в `utils/sqlite3.py` открывает соединение через `with sqlite3.connect(path_db)`. Сервисный слой будет использовать тот же подход через общий контекст-менеджер, чтобы:
1. путь к БД читался лениво (через функцию, а не на момент import) — это нужно, чтобы `monkeypatch` в тестах работал;
2. везде применялся `dict_factory`.

- [ ] **Step 1: Написать тест на connect()**

Создать `tests/unit/test_services_db.py`:

```python
from pathlib import Path

from services.db import connect


def test_connect_returns_dict_rows(tmp_db: Path) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (7, "x", "X", 50, "2026-05-02"),
        )
        con.commit()
        row = con.execute("SELECT id, balance FROM users WHERE id = 7").fetchone()
    assert row == {"id": 7, "balance": 50}


def test_connect_uses_current_path_db(tmp_db: Path) -> None:
    """Если monkeypatch path_db меняет путь — connect должен его подхватить."""
    with connect() as con:
        # Если бы connect() кэшировал путь на import, БД была бы где-то ещё
        rows = con.execute("PRAGMA table_info(orders)").fetchall()
    # 9 колонок согласно schema
    assert len(rows) == 9
```

- [ ] **Step 2: Запустить тест — должен упасть (модуль не найден)**

Run:
```bash
pytest tests/unit/test_services_db.py -v
```
Expected: `ModuleNotFoundError: No module named 'services.db'` (или ImportError).

- [ ] **Step 3: Написать services/db.py**

Создать `services/db.py`:

```python
"""Общий слой работы с SQLite для сервисов.

Сюда добавляются только утилиты, которые не подходят к конкретному домену
(connect/dict_factory). Доменные репозитории — рядом с сервисами.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Открыть SQLite-соединение с dict_factory.

    Путь к БД читается из data.config.path_database на каждый вызов, чтобы
    pytest monkeypatch мог подменять его в фикстурах.
    """
    from data import config  # noqa: PLC0415 — ленивый импорт ради monkeypatch

    con = sqlite3.connect(config.path_database)
    con.row_factory = _dict_factory
    try:
        yield con
    finally:
        con.close()
```

- [ ] **Step 4: Запустить тест — должен пройти**

Run:
```bash
pytest tests/unit/test_services_db.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/db.py tests/unit/test_services_db.py
git commit -m "feat(services): add db.connect() with dict_factory"
```

---

## Task 6: services/balance.py — атомарные операции с балансом

**Files:**
- Create: `services/balance.py`
- Test: `tests/unit/test_balance.py`

Текущий код (см. `handlers/user_functions.py:707-708`):
```python
update_user(id=user_id, balance=usr['balance'] + int(amount))
```
Это **read-modify-write race condition**: между чтением `usr['balance']` и записью могут произойти другие операции, и баланс затрётся. Атомарный путь — `UPDATE users SET balance = balance + ? WHERE id = ? RETURNING balance` (SQLite >= 3.35, доступен в Python 3.10+).

- [ ] **Step 1: Написать тесты**

Создать `tests/unit/test_balance.py`:

```python
import sqlite3
import threading
from pathlib import Path

import pytest

from services.balance import credit, debit, get_balance
from services.exceptions import InsufficientBalance, UserNotFound


def _make_user(tmp_db: Path, user_id: int = 1, balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, "u", "U", balance, "2026-05-02"),
        )
        con.commit()


def test_get_balance_returns_balance(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=100)
    assert get_balance(1) == 100


def test_get_balance_unknown_user_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        get_balance(999)


def test_credit_increments_and_returns_new_balance(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    new_balance = credit(1, 50)
    assert new_balance == 60
    assert get_balance(1) == 60


def test_credit_negative_amount_raises(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    with pytest.raises(ValueError):
        credit(1, -5)


def test_credit_zero_is_noop(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    assert credit(1, 0) == 10


def test_debit_decrements(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=100)
    new_balance = debit(1, 30)
    assert new_balance == 70


def test_debit_below_zero_raises(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    with pytest.raises(InsufficientBalance) as exc_info:
        debit(1, 50)
    assert exc_info.value.available == 10
    assert exc_info.value.required == 50
    # Баланс не должен измениться
    assert get_balance(1) == 10


def test_credit_concurrent_threads_sum_correctly(tmp_db: Path) -> None:
    """50 потоков по +1 руб должны дать +50, а не меньше из-за гонок."""
    _make_user(tmp_db, balance=0)

    def _credit_one() -> None:
        credit(1, 1)

    threads = [threading.Thread(target=_credit_one) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert get_balance(1) == 50
```

- [ ] **Step 2: Запустить тесты — должны упасть**

Run:
```bash
pytest tests/unit/test_balance.py -v
```
Expected: `ModuleNotFoundError: No module named 'services.balance'`.

- [ ] **Step 3: Реализовать services/balance.py**

Создать `services/balance.py`:

```python
"""Сервис для работы с балансом пользователя.

Все операции атомарны на уровне SQLite через UPDATE ... RETURNING.
Не делайте read-modify-write поверх get_balance() — используйте credit/debit.
"""
from __future__ import annotations

import sqlite3

from services.db import connect
from services.exceptions import InsufficientBalance, UserNotFound


def get_balance(user_id: int) -> int:
    with connect() as con:
        row = con.execute(
            "SELECT balance FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return int(row["balance"] or 0)


def credit(user_id: int, amount: int) -> int:
    """Атомарно увеличить баланс. Возвращает новый баланс."""
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount}")
    if amount == 0:
        return get_balance(user_id)

    with connect() as con:
        # SQLite >= 3.35 поддерживает RETURNING. Атомарно в рамках одного UPDATE.
        cur = con.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? "
            "WHERE id = ? RETURNING balance",
            (amount, user_id),
        )
        row = cur.fetchone()
        con.commit()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return int(row["balance"])


def debit(user_id: int, amount: int) -> int:
    """Атомарно списать сумму. Бросает InsufficientBalance если средств не хватает."""
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount}")
    if amount == 0:
        return get_balance(user_id)

    with connect() as con:
        # Атомарно: списываем только если хватает. Иначе RETURNING вернёт NULL rows.
        cur = con.execute(
            "UPDATE users SET balance = balance - ? "
            "WHERE id = ? AND balance >= ? RETURNING balance",
            (amount, user_id, amount),
        )
        row = cur.fetchone()
        con.commit()

    if row is None:
        # Может быть две причины: пользователь не существует или баланс < amount.
        current = _try_get_balance(user_id)
        if current is None:
            raise UserNotFound(f"user_id={user_id}")
        raise InsufficientBalance(user_id, available=current, required=amount)

    return int(row["balance"])


def _try_get_balance(user_id: int) -> int | None:
    try:
        return get_balance(user_id)
    except UserNotFound:
        return None
```

- [ ] **Step 4: Запустить тесты — должны пройти**

Run:
```bash
pytest tests/unit/test_balance.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/balance.py tests/unit/test_balance.py
git commit -m "feat(services): add atomic BalanceService (credit/debit/get_balance)"
```

---

## Task 7: services/refill.py — основа без реф.бонуса

**Files:**
- Create: `services/refill.py`
- Test: `tests/unit/test_refill.py`

Логика разделена на два метода:
1. `create_invoice(user_id, amount)` — обёртка над `utils.yookassa_refil.create_invoice`. Просто пробрасывает.
2. `finalize(user_id, amount)` — атомарно: `credit(user_id, amount)` + INSERT в `refills`. Реферальный бонус — отдельным шагом в Task 8.

`check_status(payment_id)` — обёртка над существующим `check_payment_status`. В этом плане **не меняем** механику опроса (12 попыток × 30 сек) — это поведение бота, веб его использовать не будет.

- [ ] **Step 1: Написать тесты**

Создать `tests/unit/test_refill.py`:

```python
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize


def _make_user(tmp_db: Path, user_id: int = 1, balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, "u", "U", balance, "2026-05-02"),
        )
        con.commit()


def test_create_invoice_delegates_to_yookassa(tmp_db: Path) -> None:
    with patch(
        "services.refill._yookassa_create_invoice",
        return_value=("https://pay/xyz", "pay-id-1"),
    ) as mock:
        url, pid = create_invoice(user_id=1, amount=200)
    assert url == "https://pay/xyz"
    assert pid == "pay-id-1"
    mock.assert_called_once_with(1, 200)


def test_create_invoice_wraps_yookassa_errors(tmp_db: Path) -> None:
    with patch(
        "services.refill._yookassa_create_invoice",
        side_effect=RuntimeError("yookassa down"),
    ):
        with pytest.raises(PaymentError):
            create_invoice(user_id=1, amount=200)


def test_finalize_credits_balance_and_writes_refill(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    new_balance = finalize(user_id=1, amount=200)
    assert new_balance == 210
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, amount FROM refills WHERE user_id = 1"
        ).fetchall()
    assert rows == [(1, 200)]


def test_finalize_unknown_user_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        finalize(user_id=999, amount=100)


def test_finalize_amount_must_be_positive(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=-50)
```

- [ ] **Step 2: Запустить — должны упасть**

Run:
```bash
pytest tests/unit/test_refill.py -v
```
Expected: `ModuleNotFoundError: No module named 'services.refill'`.

- [ ] **Step 3: Реализовать services/refill.py**

Создать `services/refill.py`:

```python
"""Сервис пополнения баланса.

create_invoice — создаёт счёт в Yookassa.
finalize — после подтверждения оплаты атомарно зачисляет баланс и пишет в refills.
"""
from __future__ import annotations

from services.balance import credit
from services.db import connect
from services.exceptions import PaymentError
from utils.other import get_date
from utils.yookassa_refil import create_invoice as _yookassa_create_invoice


def create_invoice(user_id: int, amount: int) -> tuple[str, str]:
    """Возвращает (payment_url, payment_id)."""
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")
    try:
        return _yookassa_create_invoice(user_id, amount)
    except Exception as exc:  # yookassa может бросить разные исключения
        raise PaymentError(f"yookassa create_invoice failed: {exc}") from exc


def finalize(user_id: int, amount: int) -> int:
    """Атомарно зачислить amount на баланс и записать в refills.

    Возвращает новый баланс. Бросает UserNotFound если такого user_id нет.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    new_balance = credit(user_id, amount)
    with connect() as con:
        con.execute(
            "INSERT INTO refills(amount, date, user_id) VALUES (?, ?, ?)",
            (amount, get_date(), user_id),
        )
        con.commit()
    return new_balance
```

Примечание: операции `credit` и `INSERT INTO refills` идут в разных коннектах. Это допустимо — если INSERT упадёт, баланс уже зачислен; компенсирующего действия делать **не надо** (для пользователя важнее видеть деньги, чем строку в refills). Реф.бонус будет следить за идемпотентностью отдельно (Task 8).

- [ ] **Step 4: Запустить тесты — должны пройти**

Run:
```bash
pytest tests/unit/test_refill.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_refill.py
git commit -m "feat(services): add RefillService.create_invoice and finalize"
```

---

## Task 8: services/refill.py — реферальный бонус 30%

**Files:**
- Modify: `services/refill.py`
- Modify: `tests/unit/test_refill.py`

Текущая логика реф.бонуса (см. `handlers/user_functions.py:722-744`):
- Бонус начисляется **только при первом пополнении** пользователя (`is_refill = get_refill(user_id)` — есть ли уже хоть одна запись в `refills`).
- Бонус НЕ начисляется если пользователь VIP (`usr['is_vip']`).
- Бонус = `int(amount * 0.3)`, начисляется на баланс реферера + пишется в `refills` от его user_id.
- Если у пользователя нет реферера (`ref_id` IS NULL) — бонус не начисляется.

Мы перенесём это в `finalize_with_referral_bonus`.

- [ ] **Step 1: Расширить тесты**

Дописать в конец `tests/unit/test_refill.py`:

```python
from services.refill import finalize_with_referral_bonus


def _make_user_full(
    tmp_db: Path,
    user_id: int,
    balance: int = 0,
    ref_id: int | None = None,
    is_vip: bool = False,
) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date, ref_id, is_vip) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, f"u{user_id}", f"U{user_id}", balance, "2026-05-02",
             ref_id, 1 if is_vip else None),
        )
        con.commit()


def test_referral_bonus_first_refill_credits_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id == 1
    assert result.referrer_bonus == 300  # 30%
    assert result.referrer_new_balance == 300


def test_referral_bonus_only_first_refill(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)  # реферер +300
    result = finalize_with_referral_bonus(user_id=2, amount=2000)
    # Второе пополнение — бонуса нет
    assert result.user_balance == 3000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None  # не трогали


def test_referral_bonus_skipped_for_vip(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1, is_vip=True)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None


def test_referral_bonus_skipped_when_no_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=None)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id is None
    assert result.referrer_bonus == 0


def test_referral_bonus_referrer_does_not_exist(tmp_db: Path) -> None:
    """ref_id указывает на несуществующего пользователя — поведение: бонус не начислен, не падаем."""
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=999)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None
```

- [ ] **Step 2: Запустить — упадут (метода нет)**

Run:
```bash
pytest tests/unit/test_refill.py -v
```
Expected: ImportError на `finalize_with_referral_bonus`.

- [ ] **Step 3: Дописать в services/refill.py**

В конец `services/refill.py` добавить:

```python
from dataclasses import dataclass

from services.balance import get_balance
from services.exceptions import UserNotFound


@dataclass(frozen=True)
class RefillResult:
    user_balance: int
    referrer_id: int | None
    referrer_bonus: int
    referrer_new_balance: int | None


def _is_first_refill(user_id: int) -> bool:
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    return row is None


def _get_user_for_referral(user_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT id, ref_id, is_vip FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return row


def finalize_with_referral_bonus(user_id: int, amount: int) -> RefillResult:
    """Atomically finalize a refill and credit a referral bonus when applicable.

    Bonus rules (preserved from handlers/user_functions.py:722-744):
    - Only on the user's FIRST refill.
    - User must not be VIP (is_vip IS NULL/falsy).
    - User must have a ref_id pointing to an existing user.
    - Bonus = int(amount * 0.3), credited and recorded in refills under referrer's id.
    """
    user = _get_user_for_referral(user_id)
    is_first = _is_first_refill(user_id)

    new_balance = finalize(user_id, amount)

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    if is_first and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            referrer_new_balance = finalize(int(referrer_id), bonus) if bonus > 0 else None
        except UserNotFound:
            # Реферер удалён — поведение оригинала: молча игнорируем
            referrer_new_balance = None
            bonus = 0

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_balance=referrer_new_balance,
    )
```

- [ ] **Step 4: Запустить тесты — все 10 должны пройти**

Run:
```bash
pytest tests/unit/test_refill.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_refill.py
git commit -m "feat(services): port referral 30% bonus to RefillService"
```

---

## Task 9: Заменить refill-flow в боте на RefillService

**Files:**
- Modify: `handlers/user_functions.py:672-753`

Цель: handler становится **тонким** — парсит callback, дёргает `RefillService`, шлёт сообщения. Никаких прямых `add_balance` / `update_user(balance=...)` / `add_refill` в этом коде.

**Важно:** не меняем тексты сообщений, не меняем uplink в админский чат, не меняем условие `user_id != 6988175544 and user_id != 257838190` (это test-bypass для оплаты, оставляем как было). Сохраняем все side-effects.

- [ ] **Step 1: Прочитать текущий handler ещё раз**

Run:
```bash
sed -n '672,753p' handlers/user_functions.py
```
Expected: видим текущий код, который дальше переписывается.

- [ ] **Step 2: Переписать handler**

Открыть `handlers/user_functions.py`. Заменить функцию `refill_balance` (строки 672–753) на:

```python
@dp.callback_query_handler(text_startswith="refil:confirm", state="refill_balance")
async def refill_balance(call: CallbackQuery, state: FSMContext):
    from services.refill import (
        create_invoice as svc_create_invoice,
        finalize_with_referral_bonus,
    )
    from services.exceptions import PaymentError, UserNotFound

    await call.message.delete()
    async with state.proxy() as data:
        amount = data['price']
    user_id = call.from_user.id

    try:
        payment_url, payment_id = svc_create_invoice(user_id, int(amount))
    except PaymentError:
        support_nick = get_nick('manager_nick')
        msg = get_string('str_payment_error').format(support_nick)
        await bot.send_message(chat_id=user_id, text=msg, reply_markup=payment_error_kb())
        return

    STR1 = get_string('str_debet_money').format(format_decimal(amount))

    if user_id != 6988175544 and user_id != 257838190:
        await bot.send_message(
            chat_id=user_id, text=STR1,
            reply_markup=yookassa_kb(int(amount), payment_url),
        )
        success = await check_payment_status(payment_id)
    else:
        success = True

    if not success:
        STR6 = get_string('str_pay_error').format(get_nick('manager_nick'))
        await bot.send_message(chat_id=user_id, text=STR6)
        return

    try:
        result = finalize_with_referral_bonus(user_id, int(amount))
    except UserNotFound:
        await bot.send_message(chat_id=user_id, text=get_string('str_error'))
        return
    except Exception as ex:
        print(f'Error:\n{ex}')
        await bot.send_message(chat_id=user_id, text=get_string('str_error'))
        return

    usr = get_user(id=user_id)
    user_string = await get_user_string_without_first_name(usr)
    f_amount = format_decimal(amount)
    f_balance = format_decimal(result.user_balance)

    STR2 = get_string('str_usr_pay_success').format(f_amount, f_balance)
    await bot.send_message(chat_id=user_id, text=STR2, reply_markup=user_back_kb('user:profile'))
    STR3 = get_string('str_adm_pay_success').format(f_amount, user_string, f_balance)
    await send_admins(STR3)
    print(f"Юзер {usr['id']}: {usr['user_name']} пополнил баланс на {amount} руб.")

    if result.referrer_bonus > 0 and result.referrer_id is not None:
        ref_user = get_user(id=str(result.referrer_id))
        if ref_user:
            f_add_bal = format_decimal(result.referrer_bonus)
            f_new_bal = format_decimal(result.referrer_new_balance)
            STR4 = get_string('str_ref_balance_refil').format(f_add_bal, f_new_bal)
            await bot.send_message(chat_id=str(result.referrer_id), text=STR4)
            ref_user_str = ref_user.get('user_name') or ref_user['id']
            print(f"Юзер {ref_user_str} получил пополнение на {result.referrer_bonus} руб.")
```

- [ ] **Step 3: Проверить, что оставшиеся импорты в файле всё ещё корректны**

Run:
```bash
python -c "import handlers.user_functions"
```
Expected: import завершается без ошибок (могут быть warning'и про aiogram — игнорируем).

- [ ] **Step 4: Прогнать unit-тесты сервисов**

Run:
```bash
pytest tests/unit/ -v
```
Expected: всё что было — passed.

- [ ] **Step 5: Manual smoke-test (документация)**

Сделать руками в Telegram:

1. Отправить боту `/start` → нажать профиль → пополнить баланс → ввести сумму выше `min_amount` → подтвердить.
2. Не оплачивать (через 6 минут timeout) — должно прийти `str_pay_error`.
3. Повторить, оплатить — должно прийти `str_usr_pay_success`, баланс увеличиться, админам в чат прийти `str_adm_pay_success`.
4. Проверить, что в БД появилась строка в `refills` (`SELECT * FROM refills ORDER BY increment DESC LIMIT 1`).
5. Если у юзера выставлен `ref_id` и это его первое пополнение — рефереру пришло сообщение про 30%, в `refills` появилась вторая строка от его id.

Если что-то сломалось — править в этом же коммите. Если всё ок — commit.

- [ ] **Step 6: Commit**

```bash
git add handlers/user_functions.py
git commit -m "refactor(bot): delegate refill flow to RefillService"
```

---

## Task 10: web/config.py — настройки веба

**Files:**
- Create: `web/__init__.py`
- Create: `web/config.py`
- Modify: `data/example.config.py`

- [ ] **Step 1: Создать пакет**

```bash
mkdir -p web/routers web/static
touch web/__init__.py web/routers/__init__.py
```

- [ ] **Step 2: Написать web/config.py**

Создать `web/config.py`:

```python
"""Конфигурация веб-приложения.

Берём secrets из env (если есть) либо из data/config.py. Это даёт два режима:
- prod: переменные окружения переопределяют значения из конфига;
- dev: достаточно прописать значения в data/config.py.
"""
from __future__ import annotations

import os

from data import config as bot_config


def _env_or_default(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


# Bot token (нужен для проверки подписи Telegram Login Widget).
BOT_TOKEN: str = _env_or_default("BOT_TOKEN", bot_config.TOKEN) or ""

# JWT
JWT_SECRET: str = _env_or_default(
    "JWT_SECRET",
    getattr(bot_config, "JWT_SECRET", None),
) or ""
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_HOURS: int = int(_env_or_default("JWT_EXPIRE_HOURS", "24") or "24")

# HTTP
WEB_HOST: str = _env_or_default("WEB_HOST", "127.0.0.1") or "127.0.0.1"
WEB_PORT: int = int(_env_or_default("WEB_PORT", "8000") or "8000")

# Telegram Login: насколько свежими считаем данные виджета (секунды).
TG_AUTH_MAX_AGE_SECONDS: int = 86_400  # 24 часа, как рекомендует Telegram


def assert_configured() -> None:
    """Падать рано, если запускаем без секретов."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty — set in env or data/config.py")
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError(
            "JWT_SECRET is empty or shorter than 32 chars — set a strong secret"
        )
```

- [ ] **Step 3: Обновить data/example.config.py**

Открыть `data/example.config.py` и добавить в самый низ:

```python

#################################
### Web (FastAPI)
JWT_SECRET = "REPLACE_ME_WITH_AT_LEAST_32_CHARS_RANDOM_STRING_PLEASE"
WEB_HOST = "127.0.0.1"
WEB_PORT = 8000
```

- [ ] **Step 4: Smoke-проверка**

Run:
```bash
python -c "from web.config import BOT_TOKEN, JWT_ALGORITHM, WEB_PORT; print(JWT_ALGORITHM, WEB_PORT)"
```
Expected: `HS256 8000`. (BOT_TOKEN тут читается из реального data/config.py — ок, мы ничего не печатаем.)

- [ ] **Step 5: Commit**

```bash
git add web/__init__.py web/routers/__init__.py web/config.py data/example.config.py
git commit -m "feat(web): add config module with JWT and HTTP settings"
```

---

## Task 11: web/main.py — каркас FastAPI с /api/health

**Files:**
- Create: `web/main.py`
- Test: `tests/web/test_health.py`

- [ ] **Step 1: Написать тест**

Создать `tests/web/test_health.py`:

```python
from fastapi.testclient import TestClient

from web.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Запустить — упадёт (модуля нет)**

Run:
```bash
pytest tests/web/test_health.py -v
```
Expected: ImportError на `web.main`.

- [ ] **Step 3: Реализовать web/main.py**

Создать `web/main.py`:

```python
"""Точка входа FastAPI-приложения.

Запускается как фоновая asyncio-таска внутри aiogram-loop через __main__.py.
Routers подключаются ниже по мере добавления (в Task 14, 15).
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Avito PF Bot Web", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Запустить тест — должен пройти**

Run:
```bash
pytest tests/web/test_health.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add web/main.py tests/web/test_health.py
git commit -m "feat(web): add FastAPI app with /api/health"
```

---

## Task 12: Запуск web рядом с aiogram через on_startup

**Files:**
- Modify: `__main__.py`

Aiogram 2.25 запускает event loop через `executor.start_polling`. Уvicorn умеет работать в существующем loop через `uvicorn.Server.serve()` как корутина. Запустим её фоновой задачей в `on_startup`.

- [ ] **Step 1: Прочитать текущий __main__.py**

Run:
```bash
cat __main__.py
```
Expected: видим текущий код с `run_bot_forever()`.

- [ ] **Step 2: Изменить on_startup и добавить serve_web**

Открыть `__main__.py` и заменить функцию `on_startup` (строки 33–36) и добавить новую корутину перед ней:

```python
async def serve_web():
    import uvicorn
    from web.main import app
    from web.config import WEB_HOST, WEB_PORT, assert_configured

    assert_configured()
    config = uvicorn.Config(
        app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="info",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    await server.serve()


# Выполнение функции после запуска бота
async def on_startup(dp: Dispatcher):
    logger.info("Bot startup")
    asyncio.create_task(serve_web())
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)
```

- [ ] **Step 3: Запустить вручную и проверить /api/health**

В одном терминале:
```bash
python __main__.py
```
В другом:
```bash
curl -sS http://127.0.0.1:8000/api/health
```
Expected: `{"status":"ok"}`. Бот при этом продолжает отвечать в Telegram.

Если `assert_configured` падает — значит в `data/config.py` нет `JWT_SECRET`. Прописать там сильный секрет (>=32 символа), перезапустить.

- [ ] **Step 4: Остановить процесс (Ctrl+C)**

Expected: бот корректно завершает polling, uvicorn-task получает CancelledError и выходит, процесс завершается.

- [ ] **Step 5: Commit**

```bash
git add __main__.py
git commit -m "feat: run FastAPI alongside aiogram polling in same process"
```

---

## Task 13: web/auth.py — Telegram Login verify + JWT

**Files:**
- Create: `web/auth.py`
- Test: `tests/web/test_auth.py`

Алгоритм Telegram Login Widget (документация: <https://core.telegram.org/widgets/login#checking-authorization>):

1. Виджет шлёт на бэкенд поля `id, first_name, last_name?, username?, photo_url?, auth_date, hash`.
2. Берём все поля, кроме `hash`, сортируем по ключу, склеиваем в `data_check_string` строкой `key=value\n...`.
3. `secret_key = sha256(bot_token)` (raw bytes).
4. `expected_hash = hmac_sha256(secret_key, data_check_string).hexdigest()`.
5. Сравниваем `hash == expected_hash` (constant-time).
6. Проверяем `now - auth_date < TG_AUTH_MAX_AGE_SECONDS`.

- [ ] **Step 1: Написать тесты**

Создать `tests/web/test_auth.py`:

```python
import hashlib
import hmac
import time
from typing import Any

import jwt as pyjwt
import pytest

from web import auth as auth_module


def _make_widget_data(bot_token: str, user_id: int = 42, **extra: Any) -> dict:
    """Сгенерировать корректно подписанные данные виджета."""
    data: dict[str, Any] = {
        "id": user_id,
        "first_name": "Test",
        "auth_date": int(time.time()),
        **extra,
    }
    data_check_string = "\n".join(
        f"{k}={data[k]}" for k in sorted(data.keys())
    )
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return {**data, "hash": h}


def test_verify_telegram_auth_accepts_valid_signature() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    user_id = auth_module.verify_telegram_auth(data, bot_token=token)
    assert user_id == 42


def test_verify_telegram_auth_rejects_bad_hash() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    data["hash"] = "0" * 64
    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_verify_telegram_auth_rejects_old_auth_date() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    # Подписываем с очень старым auth_date
    data["auth_date"] = int(time.time()) - 99_999_999
    # Пересчитать hash под новый auth_date:
    fresh = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={fresh[k]}" for k in sorted(fresh.keys()))
    secret_key = hashlib.sha256(token.encode()).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_verify_telegram_auth_rejects_missing_hash() -> None:
    token = "1234:dummy"
    data = _make_widget_data(token, user_id=42)
    del data["hash"]
    with pytest.raises(auth_module.AuthError):
        auth_module.verify_telegram_auth(data, bot_token=token)


def test_create_and_decode_jwt_roundtrip() -> None:
    secret = "x" * 32
    token = auth_module.create_jwt(user_id=42, secret=secret)
    user_id = auth_module.decode_jwt(token, secret=secret)
    assert user_id == 42


def test_decode_jwt_rejects_bad_signature() -> None:
    secret = "x" * 32
    token = auth_module.create_jwt(user_id=42, secret=secret)
    with pytest.raises(auth_module.AuthError):
        auth_module.decode_jwt(token, secret="y" * 32)


def test_decode_jwt_rejects_expired_token() -> None:
    secret = "x" * 32
    # Сами создадим уже истёкший токен
    expired = pyjwt.encode(
        {"sub": "42", "exp": int(time.time()) - 10},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(auth_module.AuthError):
        auth_module.decode_jwt(expired, secret=secret)
```

- [ ] **Step 2: Запустить — упадёт**

Run:
```bash
pytest tests/web/test_auth.py -v
```
Expected: ImportError на `web.auth`.

- [ ] **Step 3: Реализовать web/auth.py**

Создать `web/auth.py`:

```python
"""Авторизация веб-клиента: Telegram Login Widget + JWT.

verify_telegram_auth — валидирует данные виджета по HMAC от bot token.
create_jwt / decode_jwt — выдают и проверяют наш собственный сессионный токен.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt

from web.config import (
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    TG_AUTH_MAX_AGE_SECONDS,
)


class AuthError(Exception):
    """Не удалось проверить подпись или токен истёк."""


def verify_telegram_auth(data: dict[str, Any], bot_token: str) -> int:
    """Проверить подпись Telegram Login Widget и вернуть user_id.

    Бросает AuthError если подпись неверна или auth_date устарел.
    """
    if "hash" not in data:
        raise AuthError("missing 'hash'")

    received_hash = data["hash"]
    payload = {k: v for k, v in data.items() if k != "hash"}

    if "auth_date" not in payload:
        raise AuthError("missing 'auth_date'")
    try:
        auth_date = int(payload["auth_date"])
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'auth_date'") from exc

    if time.time() - auth_date > TG_AUTH_MAX_AGE_SECONDS:
        raise AuthError("auth_date is too old")

    data_check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise AuthError("hash mismatch")

    if "id" not in payload:
        raise AuthError("missing 'id'")
    try:
        return int(payload["id"])
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'id'") from exc


def create_jwt(user_id: int, secret: str, expires_hours: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours or JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": exp}
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str, secret: str) -> int:
    try:
        payload = pyjwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    sub = payload.get("sub")
    if sub is None:
        raise AuthError("missing 'sub'")
    try:
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise AuthError("invalid 'sub'") from exc
```

- [ ] **Step 4: Запустить — все 7 тестов должны пройти**

Run:
```bash
pytest tests/web/test_auth.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add web/auth.py tests/web/test_auth.py
git commit -m "feat(web): add Telegram Login verify and JWT roundtrip"
```

---

## Task 14: web/deps.py + /api/auth/telegram + /api/me

**Files:**
- Create: `web/schemas.py`
- Create: `web/deps.py`
- Create: `web/routers/auth.py`
- Modify: `web/main.py`
- Test: `tests/web/test_routers_auth.py`

- [ ] **Step 1: Написать схемы**

Создать `web/schemas.py`:

```python
"""Pydantic-схемы для запросов и ответов веб-API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    """Данные, которые присылает Telegram Login Widget. Все поля опциональны
    кроме id/auth_date/hash, потому что first_name/last_name/username/photo_url
    могут отсутствовать в зависимости от настроек юзера в Telegram."""

    id: int
    auth_date: int
    hash: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None

    def to_widget_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Profile(BaseModel):
    user_id: int
    user_name: str | None
    first_name: str | None
    balance: int = Field(ge=0)


class RefillRequest(BaseModel):
    amount: int = Field(gt=0)


class RefillResponse(BaseModel):
    payment_id: str
    payment_url: str


class RefillStatusResponse(BaseModel):
    payment_id: str
    status: str  # "pending" | "succeeded" | "failed"
```

- [ ] **Step 2: Написать deps.py**

Создать `web/deps.py`:

```python
"""FastAPI-зависимости для извлечения текущего пользователя из JWT."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from web.auth import AuthError, decode_jwt
from web.config import JWT_SECRET


async def get_current_user_id(
    authorization: str | None = Header(default=None),
) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_jwt(token, secret=JWT_SECRET)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
```

- [ ] **Step 3: Написать router auth.py**

Создать `web/routers/auth.py`:

```python
"""Эндпоинты авторизации.

POST /api/auth/telegram — принимает Telegram Login data, возвращает JWT.
GET  /api/me           — возвращает профиль текущего пользователя.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.db import connect
from web.auth import AuthError, create_jwt, verify_telegram_auth
from web.config import BOT_TOKEN, JWT_SECRET
from web.deps import get_current_user_id
from web.schemas import AuthResponse, Profile, TelegramAuthRequest

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/telegram", response_model=AuthResponse)
async def telegram_login(payload: TelegramAuthRequest) -> AuthResponse:
    try:
        user_id = verify_telegram_auth(payload.to_widget_dict(), bot_token=BOT_TOKEN)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    # Если пользователя ещё нет в users — он попадёт туда при первом /start в боте.
    # Веб-авторизация без записи в users допустима: профиль увидит /api/me и вернёт 404.
    token = create_jwt(user_id=user_id, secret=JWT_SECRET)
    return AuthResponse(access_token=token)


@router.get("/me", response_model=Profile)
async def me(user_id: int = Depends(get_current_user_id)) -> Profile:
    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, first_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not registered in bot — please /start the bot first",
        )
    return Profile(
        user_id=row["id"],
        user_name=row["user_name"],
        first_name=row["first_name"],
        balance=int(row["balance"] or 0),
    )
```

- [ ] **Step 4: Подключить router в web/main.py**

Открыть `web/main.py` и добавить после строки `app = FastAPI(...)`:

```python
from web.routers import auth as auth_router  # noqa: E402

app.include_router(auth_router.router)
```

- [ ] **Step 5: Написать тесты**

Создать `tests/web/test_routers_auth.py`:

```python
import hashlib
import hmac
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("web.config.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    # Эти же значения уже импортированы в модулях — патчим и там
    monkeypatch.setattr("web.routers.auth.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.routers.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.deps.JWT_SECRET", "x" * 32)
    from web.main import app
    return TestClient(app)


def _signed_widget_data(bot_token: str, user_id: int) -> dict:
    data = {"id": user_id, "first_name": "T", "auth_date": int(time.time())}
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return data


def test_telegram_login_returns_jwt(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    response = client.post("/api/auth/telegram", json=data)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20


def test_telegram_login_rejects_bad_signature(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    data["hash"] = "0" * 64
    response = client.post("/api/auth/telegram", json=data)
    assert response.status_code == 401


def test_me_returns_404_when_user_not_in_db(client: TestClient) -> None:
    data = _signed_widget_data("1234:dummy", user_id=42)
    token = client.post("/api/auth/telegram", json=data).json()["access_token"]
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_me_returns_profile(client: TestClient, tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 1500, "2026-05-02"),
        )
        con.commit()

    data = _signed_widget_data("1234:dummy", user_id=42)
    token = client.post("/api/auth/telegram", json=data).json()["access_token"]
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": 42,
        "user_name": "tester",
        "first_name": "Test",
        "balance": 1500,
    }


def test_me_requires_auth(client: TestClient) -> None:
    response = client.get("/api/me")
    assert response.status_code == 401
```

- [ ] **Step 6: Запустить тесты — все 5 должны пройти**

Run:
```bash
pytest tests/web/test_routers_auth.py -v
```
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add web/schemas.py web/deps.py web/routers/auth.py web/main.py tests/web/test_routers_auth.py
git commit -m "feat(web): add /api/auth/telegram and /api/me with JWT"
```

---

## Task 15: web/routers/refill.py — пополнение через веб

**Files:**
- Create: `web/routers/refill.py`
- Modify: `web/main.py`
- Test: `tests/web/test_routers_refill.py`

**Важная заметка про polling статуса.** В боте `check_payment_status` блочит 6 минут (12 × 30s). Для веба так делать нельзя — фронтенд опрашивает статус сам через GET. Поэтому:
- POST `/api/refill` создаёт инвойс и возвращает `payment_id` + `payment_url`. Не дожидается оплаты.
- GET `/api/refill/{payment_id}/status` дёргает yookassa один раз, возвращает статус. Если `succeeded` — внутри атомарно вызывает `RefillService.finalize_with_referral_bonus`.
- Чтобы не зачислить дважды, перед finalize проверяем что в БД ещё нет refill с этим `payment_id`. Для этого добавим в таблицу `refills` колонку `payment_id` (миграция через `ALTER TABLE` в `create_db`).

- [ ] **Step 1: Добавить колонку payment_id в refills**

В `utils/sqlite3.py` в функции `create_db`, после цикла по `get_schema_statements()`, добавить идемпотентную миграцию:

```python
        # Миграция: payment_id для дедупликации web-пополнений (Phase 1)
        existing_cols = {row["name"] for row in con.execute("PRAGMA table_info(refills)").fetchall()}
        if "payment_id" not in existing_cols:
            con.execute("ALTER TABLE refills ADD COLUMN payment_id TEXT")
            print("migration: added refills.payment_id")
        con.commit()
```

И в `get_schema_statements()` в DDL для `refills` поменять количество колонок: `4` → `5`, и саму DDL:

```python
        (
            "refills",
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "payment_id TEXT,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            5,
        ),
```

- [ ] **Step 2: Прогнать существующие тесты**

Run:
```bash
pytest tests/unit -v
```
Expected: всё passed (новая колонка не ломает существующие SQL — мы их не меняли).

- [ ] **Step 3: Расширить services/refill.py: optional payment_id и идемпотентность**

В `services/refill.py` поменять сигнатуру `finalize` и добавить идемпотентность:

```python
def finalize(user_id: int, amount: int, payment_id: str | None = None) -> int:
    """Атомарно зачислить amount на баланс и записать в refills.

    Если передан payment_id — операция идемпотентна: повторный вызов с тем же
    payment_id не зачисляет деньги повторно, а возвращает текущий баланс.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

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
            "INSERT INTO refills(amount, date, user_id, payment_id) VALUES (?, ?, ?, ?)",
            (amount, get_date(), user_id, payment_id),
        )
        con.commit()
    return new_balance
```

И обновить `finalize_with_referral_bonus`, чтобы пробросить `payment_id`:

```python
def finalize_with_referral_bonus(
    user_id: int, amount: int, payment_id: str | None = None
) -> RefillResult:
    """См. Task 8 — добавлено пробрасывание payment_id для идемпотентности."""
    user = _get_user_for_referral(user_id)
    is_first = _is_first_refill(user_id)

    new_balance = finalize(user_id, amount, payment_id=payment_id)

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    if is_first and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            # Реф-бонус идёт без payment_id — это отдельная транзакция
            referrer_new_balance = finalize(int(referrer_id), bonus) if bonus > 0 else None
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

- [ ] **Step 4: Дописать тест на идемпотентность finalize**

В конец `tests/unit/test_refill.py` добавить:

```python
def test_finalize_is_idempotent_with_payment_id(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, payment_id="pay-A")
    # Повторный вызов с тем же payment_id — баланс не должен удвоиться
    new_balance = finalize(user_id=1, amount=100, payment_id="pay-A")
    assert new_balance == 100
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("SELECT amount FROM refills WHERE user_id = 1").fetchall()
    assert rows == [(100,)]


def test_finalize_no_payment_id_is_not_dedup(tmp_db: Path) -> None:
    """Без payment_id вызовы независимы — два пополнения = +amount × 2."""
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100)
    finalize(user_id=1, amount=100)
    assert get_balance(1) == 200
```

И добавить импорт в начало файла рядом с другими: `from services.balance import get_balance`.

- [ ] **Step 5: Прогнать unit-тесты**

Run:
```bash
pytest tests/unit -v
```
Expected: все passed (включая 2 новых).

- [ ] **Step 6: Реализовать /api/refill эндпоинты**

Создать `web/routers/refill.py`:

```python
"""Эндпоинты пополнения баланса через веб.

POST /api/refill                     — создать инвойс, вернуть URL и payment_id.
GET  /api/refill/{payment_id}/status — узнать статус и (если оплачено) зачислить.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize_with_referral_bonus
from web.deps import get_current_user_id
from web.schemas import RefillRequest, RefillResponse, RefillStatusResponse

router = APIRouter(prefix="/api/refill", tags=["refill"])


def _yookassa_status(payment_id: str) -> str:
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    try:
        payment = Payment.find_one(payment_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"yookassa error: {exc}",
        ) from exc
    return payment.status  # "pending" | "succeeded" | "canceled" | ...


@router.post("", response_model=RefillResponse)
async def create_refill(
    payload: RefillRequest,
    user_id: int = Depends(get_current_user_id),
) -> RefillResponse:
    try:
        url, pid = create_invoice(user_id, payload.amount)
    except PaymentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return RefillResponse(payment_id=pid, payment_url=url)


@router.get("/{payment_id}/status", response_model=RefillStatusResponse)
async def refill_status(
    payment_id: str,
    user_id: int = Depends(get_current_user_id),
) -> RefillStatusResponse:
    yookassa_status = _yookassa_status(payment_id)

    # Маппим в простые статусы
    if yookassa_status == "succeeded":
        # На всякий случай возьмём сумму из yookassa — клиент мог соврать
        Configuration.account_id = SHOP_ID
        Configuration.secret_key = SECRET_KEY
        payment = Payment.find_one(payment_id)
        amount = int(float(payment.amount.value))
        try:
            finalize_with_referral_bonus(user_id, amount, payment_id=payment_id)
        except UserNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not in bot DB; /start the bot first",
            )
        simplified = "succeeded"
    elif yookassa_status in {"canceled", "expired", "rejected"}:
        simplified = "failed"
    else:
        simplified = "pending"

    return RefillStatusResponse(payment_id=payment_id, status=simplified)
```

- [ ] **Step 7: Подключить router в web/main.py**

В `web/main.py` после `from web.routers import auth as auth_router` добавить:

```python
from web.routers import refill as refill_router  # noqa: E402

app.include_router(refill_router.router)
```

- [ ] **Step 8: Написать тесты на refill-эндпоинты**

Создать `tests/web/test_routers_refill.py`:

```python
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("web.config.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.routers.auth.BOT_TOKEN", "1234:dummy")
    monkeypatch.setattr("web.routers.auth.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.deps.JWT_SECRET", "x" * 32)

    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, "tester", "Test", 0, "2026-05-02"),
        )
        con.commit()

    from web.auth import create_jwt
    token = create_jwt(user_id=42, secret="x" * 32)

    from web.main import app
    client = TestClient(app)
    return SimpleNamespace(
        client=client, token=token,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_create_refill_returns_payment_url(authed) -> None:
    with patch(
        "web.routers.refill.create_invoice",
        return_value=("https://pay/aaa", "pay-1"),
    ):
        response = authed.client.post(
            "/api/refill", json={"amount": 500}, headers=authed.headers,
        )
    assert response.status_code == 200
    assert response.json() == {"payment_id": "pay-1", "payment_url": "https://pay/aaa"}


def test_create_refill_requires_positive_amount(authed) -> None:
    response = authed.client.post(
        "/api/refill", json={"amount": 0}, headers=authed.headers,
    )
    assert response.status_code == 422  # pydantic validation


def test_create_refill_requires_auth(authed) -> None:
    response = authed.client.post("/api/refill", json={"amount": 500})
    assert response.status_code == 401


def test_status_pending_does_not_credit(authed, tmp_db: Path) -> None:
    fake_payment = SimpleNamespace(status="pending", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake_payment):
        response = authed.client.get(
            "/api/refill/pay-X/status", headers=authed.headers,
        )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("SELECT * FROM refills").fetchall()
    assert rows == []


def test_status_succeeded_credits_balance_idempotent(authed, tmp_db: Path) -> None:
    fake_payment = SimpleNamespace(status="succeeded", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake_payment):
        r1 = authed.client.get("/api/refill/pay-Y/status", headers=authed.headers)
        r2 = authed.client.get("/api/refill/pay-Y/status", headers=authed.headers)

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["status"] == "succeeded"
    assert r2.json()["status"] == "succeeded"

    with sqlite3.connect(tmp_db) as con:
        balance = con.execute("SELECT balance FROM users WHERE id = 42").fetchone()[0]
        refills = con.execute("SELECT amount, payment_id FROM refills").fetchall()
    assert balance == 500
    assert refills == [(500, "pay-Y")]


def test_status_failed_for_canceled(authed) -> None:
    fake = SimpleNamespace(status="canceled", amount=SimpleNamespace(value="500.00"))
    with patch("web.routers.refill.Payment.find_one", return_value=fake):
        response = authed.client.get("/api/refill/pay-Z/status", headers=authed.headers)
    assert response.json()["status"] == "failed"
```

- [ ] **Step 9: Запустить тесты**

Run:
```bash
pytest tests/web/test_routers_refill.py -v
```
Expected: 6 passed.

- [ ] **Step 10: Прогнать всю сюиту целиком**

Run:
```bash
pytest -v
```
Expected: все тесты passed.

- [ ] **Step 11: Commit**

```bash
git add utils/sqlite3.py services/refill.py tests/unit/test_refill.py web/routers/refill.py web/main.py tests/web/test_routers_refill.py
git commit -m "feat(web): add /api/refill with idempotent finalize via payment_id"
```

---

## Task 16: Минимальные HTML-страницы

**Files:**
- Create: `web/static/index.html`
- Create: `web/static/cabinet.html`
- Modify: `web/main.py`

- [ ] **Step 1: Подключить статику в web/main.py**

В `web/main.py` добавить (после include_router'ов):

```python
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
```

Важно: mount на `/` — последним. До него уже зарегистрированы все `/api/*` роуты, FastAPI отдаст приоритет им. `html=True` означает: `GET /` → `index.html`, `GET /cabinet` → `cabinet.html`.

- [ ] **Step 2: Создать index.html с Telegram Login Widget**

Создать `web/static/index.html`. Вместо `YOUR_BOT_NAME` подставить реальное имя бота (без `@`) — для AVITOPF_bot это `AVITOPF_bot`:

```html
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Avito PF Bot — вход</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 480px; margin: 80px auto; padding: 0 16px; }
        h1 { margin-bottom: 24px; }
        .err { color: #c00; margin-top: 16px; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h1>Войти через Telegram</h1>
    <p>Чтобы продолжить, авторизуйтесь через бота.</p>

    <script async src="https://telegram.org/js/telegram-widget.js?22"
            data-telegram-login="AVITOPF_bot"
            data-size="large"
            data-onauth="onTelegramAuth(user)"
            data-request-access="write"></script>

    <div id="err" class="err"></div>

    <script>
        async function onTelegramAuth(user) {
            try {
                const resp = await fetch("/api/auth/telegram", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(user),
                });
                if (!resp.ok) {
                    const detail = await resp.text();
                    throw new Error("auth failed: " + resp.status + " " + detail);
                }
                const data = await resp.json();
                localStorage.setItem("access_token", data.access_token);
                window.location.href = "/cabinet.html";
            } catch (e) {
                document.getElementById("err").textContent = String(e);
            }
        }
    </script>
</body>
</html>
```

- [ ] **Step 3: Создать cabinet.html**

Создать `web/static/cabinet.html`:

```html
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Личный кабинет</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 560px; margin: 60px auto; padding: 0 16px; }
        .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-top: 16px; }
        button { padding: 10px 16px; font-size: 16px; cursor: pointer; }
        input { padding: 8px 10px; font-size: 16px; width: 160px; margin-right: 8px; }
        .err { color: #c00; margin-top: 16px; white-space: pre-wrap; }
        .ok  { color: #080; margin-top: 16px; }
    </style>
</head>
<body>
    <h1>Личный кабинет</h1>
    <div id="profile" class="card">Загрузка...</div>

    <div class="card">
        <h3>Пополнить баланс</h3>
        <input id="amount" type="number" min="1" placeholder="Сумма, ₽">
        <button id="refill-btn">Пополнить</button>
        <div id="refill-status"></div>
    </div>

    <p><a href="#" id="logout">Выйти</a></p>

    <script>
        const token = localStorage.getItem("access_token");
        if (!token) { window.location.href = "/index.html"; }

        const authHeaders = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        };

        async function loadProfile() {
            const r = await fetch("/api/me", {headers: authHeaders});
            const el = document.getElementById("profile");
            if (r.status === 401) { localStorage.removeItem("access_token"); window.location.href = "/index.html"; return; }
            if (r.status === 404) { el.textContent = "Сначала запустите бота /start в Telegram, потом перезагрузите страницу."; return; }
            const p = await r.json();
            el.innerHTML = `<b>${p.first_name || ""}</b> (@${p.user_name || "—"})<br>Баланс: <b>${p.balance} ₽</b>`;
        }

        async function startRefill() {
            const amount = Number(document.getElementById("amount").value);
            const status = document.getElementById("refill-status");
            status.className = ""; status.textContent = "Создаю инвойс...";
            const r = await fetch("/api/refill", {
                method: "POST", headers: authHeaders,
                body: JSON.stringify({amount}),
            });
            if (!r.ok) { status.className = "err"; status.textContent = "Ошибка: " + r.status; return; }
            const {payment_id, payment_url} = await r.json();
            window.open(payment_url, "_blank");
            status.textContent = "Ожидаю подтверждение оплаты...";
            pollStatus(payment_id, status);
        }

        async function pollStatus(payment_id, statusEl) {
            for (let i = 0; i < 60; i++) {  // ~5 минут
                await new Promise(r => setTimeout(r, 5000));
                const r = await fetch(`/api/refill/${payment_id}/status`, {headers: authHeaders});
                if (!r.ok) continue;
                const {status} = await r.json();
                if (status === "succeeded") {
                    statusEl.className = "ok"; statusEl.textContent = "Оплата прошла, баланс обновлён.";
                    loadProfile();
                    return;
                }
                if (status === "failed") {
                    statusEl.className = "err"; statusEl.textContent = "Оплата не прошла.";
                    return;
                }
            }
            statusEl.className = "err"; statusEl.textContent = "Время ожидания истекло. Если оплатили — перезагрузите страницу.";
        }

        document.getElementById("refill-btn").onclick = startRefill;
        document.getElementById("logout").onclick = (e) => {
            e.preventDefault();
            localStorage.removeItem("access_token");
            window.location.href = "/index.html";
        };

        loadProfile();
    </script>
</body>
</html>
```

- [ ] **Step 4: Smoke test FastAPI на статику**

Run (в одном терминале):
```bash
python __main__.py
```
В другом:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/cabinet.html
curl -sS http://127.0.0.1:8000/api/health
```
Expected: `200`, `200`, `{"status":"ok"}`. Остановить процесс Ctrl+C.

- [ ] **Step 5: Commit**

```bash
git add web/main.py web/static/
git commit -m "feat(web): add minimal HTML pages for Telegram Login + refill UI"
```

---

## Task 17: E2E ручной чек-лист

**Files:**
- Create: `docs/superpowers/plans/2026-05-02-web-interface-foundation-smoke.md`

Это документ-чек-лист для ручной проверки. Его прохождение — критерий приёмки Phase 1.

- [ ] **Step 1: Создать чек-лист**

Создать `docs/superpowers/plans/2026-05-02-web-interface-foundation-smoke.md`:

```markdown
# Phase 1 — E2E Smoke Checklist

Запускается на staging-инстансе бота. БД желательно тестовая (или клонированная из прода).

## Подготовка
- [ ] В `data/config.py` прописаны: `TOKEN`, `SHOP_ID`, `SECRET_KEY`, `JWT_SECRET` (>=32 символов).
- [ ] Бот публично доступен (HTTPS) или локально через ngrok — Telegram Login Widget требует HTTPS.
- [ ] Виджет в `index.html` указывает на актуального бота (`data-telegram-login`).
- [ ] У бота включён Login Widget: `@BotFather` → выбрать бота → `/setdomain` → указать домен.

## Бот
- [ ] `/start` — приветствие.
- [ ] Профиль → "Пополнить баланс" → ввести сумму → подтвердить → инвойс открылся → оплатил → пришли два сообщения (юзеру + админам), баланс увеличился.
- [ ] Если у юзера есть `ref_id` и это первое пополнение — рефереру пришло сообщение про 30%, его баланс увеличился, в `refills` есть две строки.

## Веб
- [ ] Открыть `https://<домен>/index.html` → нажать Telegram-кнопку → авторизоваться → редирект на `/cabinet.html`.
- [ ] Кабинет показывает баланс (тот же, что в боте).
- [ ] Ввести сумму, нажать "Пополнить" → открылась yookassa → оплатил → через ~5 секунд кабинет показал "Оплата прошла, баланс обновлён" + новый баланс.
- [ ] В БД появилась строка в `refills` с заполненным `payment_id`.
- [ ] Повторить запрос `GET /api/refill/<payment_id>/status` curl'ом — статус `succeeded`, баланс не изменился (идемпотентность).

## Безопасность
- [ ] Запрос `/api/me` без `Authorization: Bearer <jwt>` → 401.
- [ ] Запрос `/api/me` с подделанным JWT → 401.
- [ ] POST `/api/auth/telegram` с подменённым `hash` → 401.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-05-02-web-interface-foundation-smoke.md
git commit -m "docs: add Phase 1 E2E smoke checklist"
```

---

## Roadmap для следующих фаз (не в этом плане)

Каждая следующая фаза — отдельный план в `docs/superpowers/plans/`.

- **Phase 2 — PromocodeService + web:** Извлечь активацию промокодов из [handlers/user_functions.py:166-233](handlers/user_functions.py:166) в `services/promocode.py`. POST /api/promo/activate. Тесты на multi-use, повторную активацию, неизвестный код.
- **Phase 3 — OrdersService + web:** Извлечь создание заказов (avito_pf, reviews, delreviews, seo). Самая большая фаза — 4 продукта. POST /api/orders, GET /api/orders, GET /api/orders/{id}. Списание с баланса через `BalanceService.debit`.
- **Phase 4 — Замена остальных handlers на сервисы:** профили, рефералы, VIP, исключения из рассылки. Без новых API — просто чистка бота.
- **Phase 5 — Миграция на Postgres:** Драйвер, миграции (Alembic), переезд `services/db.py`. Решает проблему "single writer" SQLite, открывает дорогу для горизонтального масштабирования.
- **Phase 6 — Фронтенд "по-человечески":** Перенести `static/*.html` в SPA (React/Svelte) или Mini App.

---

## Self-Review (выполнено автором плана)

**1. Spec coverage:**
- "Бот и веб работают с одной БД через сервисы" → Tasks 4–9, 14–15 ✓
- "Авторизация в вебе через Telegram Login + JWT" → Tasks 13, 14 ✓
- "Пополнение баланса из веба" → Tasks 15, 16 ✓
- "Один процесс, один loop" → Task 12 ✓
- "Тесты пишутся on-extract" → каждая services/web/ задача начинается с теста ✓
- "Не Big Bang — оставить остальной бот рабочим" → Phase 1 трогает только refill-flow, всё остальное в боте не меняется ✓

**2. Placeholder scan:** проверены — placeholders отсутствуют. Реф.бонус, идемпотентность, миграция refills.payment_id, конкретные SQL — всё показано кодом.

**3. Type consistency:**
- `RefillResult` определён в Task 8, используется в Task 9 и в схемах через `RefillResponse` (отдельная DTO для веба) — ок.
- `finalize` сигнатура расширяется в Task 15 (добавляется `payment_id`) — обратно совместимо (default=None), оба места вызова обновлены в Task 15.
- `verify_telegram_auth` принимает `dict[str, Any]`, схема `TelegramAuthRequest.to_widget_dict()` возвращает совместимый dict — ок.
- Названия путей: `/api/health`, `/api/auth/telegram`, `/api/me`, `/api/refill`, `/api/refill/{payment_id}/status` — везде последовательно.

Готово.
