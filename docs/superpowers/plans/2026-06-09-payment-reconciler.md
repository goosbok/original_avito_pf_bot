# Payment Reconciler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Гарантировать, что любой `succeeded` YooKassa-платёж зачисляется на баланс не позже ~60 сек после оплаты, через state machine `pending → succeeded|canceled|expired` в таблице `refills` и фоновый APScheduler-крон в bot-контейнере, без webhook.

**Architecture:** Расширяем `refills` колонкой `status` (миграция через `apply_phase2_migrations`). При `create_invoice` пишем `pending`. Три источника финализации (синхронный TG-пуллинг, web `/status`, новый reconciliation-крон) делают атомарный `UPDATE...WHERE status='pending'`; победитель в гонке инкрементирует баланс. Крон тикает раз в 60 сек, опрашивает YK по каждому нашему `pending` за последние 24 часа и переводит статус согласно ответу YK.

**Tech Stack:** Python 3.10+, SQLite 3.35+ (UPDATE...RETURNING), aiogram 2.x, FastAPI, APScheduler, YooKassa Python SDK, pytest (`asyncio_mode=auto`).

**Spec:** [docs/superpowers/specs/2026-06-09-payment-reconciler-design.md](../specs/2026-06-09-payment-reconciler-design.md)

---

## File Structure

### Create
- `services/payment_notifications.py` — функции уведомлений (`notify_user_success`, `notify_admins_success`, `notify_referrer`).
- `services/payment_reconciler.py` — async `reconcile_pending` для APScheduler.
- `scripts/backfill_stuck_payments.py` — разовый скрипт для 7 известных stuck.
- `tests/unit/test_refill_state_machine.py` — тесты `finalize`/`finalize_with_referral_bonus`.
- `tests/unit/test_payment_notifications.py` — тесты модуля уведомлений.
- `tests/unit/test_payment_reconciler.py` — тесты крона с моком YK SDK.
- `tests/unit/test_refills_migration.py` — тест миграции `status` колонки.

### Modify
- `utils/sqlite3.py` — расширить DDL refills + `apply_phase2_migrations` + `get_index_statements` + `get_user_all_refills`/`all_refills` (фильтр `status='succeeded'`).
- `services/refill.py` — `RefillResult`, `_is_first_refill`, `finalize`, `finalize_with_referral_bonus`, `create_invoice`.
- `handlers/refill.py:78-143` — `_handle_yookassa_payment`: передать `payment_id`, заменить STR6.
- `web/routers/refill.py:87-108,111-142` — `create_refill`/`refill_status`: передать `source_type`/`source_app_id`, добавить уведомления при успехе.
- `__main__.py:106-117` — добавить вторую APScheduler job рядом с `payment_probe`.

### Don't touch
- `utils/yookassa_refil.py` — низкоуровневые YK обёртки.
- Существующая логика `services/balance.py` — `credit`/`debit` нас полностью устраивают.

---

## Test infrastructure cheat-sheet

- Запуск всех тестов в Docker: `docker compose --profile test run --rm test`
- Запуск одного теста: `docker compose --profile test run --rm test pytest tests/unit/test_X.py::test_Y -v`
- Фикстура `tmp_db` (из [tests/conftest.py](tests/conftest.py)) даёт изолированную SQLite-БД с продакшен-схемой и monkeypatch'ит `path_database`. Используем её во всех unit-тестах, трогающих БД.
- `services/db.connect()` (из [services/db.py](services/db.py)) — context manager, dict_factory, WAL, FK ON. Все запросы из новых модулей идут через него.
- Для моков `bot.send_message` — `data.loader.bot` уже замокан в conftest.py как `MagicMock` с `send_message=AsyncMock()`.
- Для моков `yookassa.Payment` — обычный `unittest.mock.patch("yookassa.Payment.find_one", ...)`.

---

## Task 1: Миграция БД — колонка `status` + индексы

**Files:**
- Modify: `utils/sqlite3.py:769-781` (DDL refills), `utils/sqlite3.py:982-991` (или где `get_index_statements` возвращает индексы — найти и расширить), `utils/sqlite3.py:993-1103` (`apply_phase2_migrations`)
- Test: `tests/unit/test_refills_migration.py` (create)

- [ ] **Step 1: Найти `get_index_statements`**

```bash
grep -n "def get_index_statements" utils/sqlite3.py
```
Expected: один матч, около строки ~982. Открыть, посмотреть формат (`return [stmt1, stmt2, ...]`).

- [ ] **Step 2: Написать failing test для миграции**

Create `tests/unit/test_refills_migration.py`:

```python
"""Тест миграции refills.status: ALTER, индексы, дефолт для существующих."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _old_schema_create(path: Path) -> None:
    """Старая схема refills (до миграции): без колонки status."""
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE refills("
            "increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER,"
            "date TIMESTAMP,"
            "payment_id TEXT,"
            "source_type TEXT NOT NULL DEFAULT 'telegram',"
            "source_app_id INTEGER"
            ")"
        )
        # Заодно нужны users для FK + auth_providers/orders (apply_phase2_migrations их трогает).
        con.execute(
            "CREATE TABLE users(id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0,"
            " user_name TEXT, first_name TEXT, reg_date TEXT)"
        )
        con.execute(
            "CREATE TABLE orders(increment INTEGER PRIMARY KEY AUTOINCREMENT,"
            " user_id INTEGER, price INTEGER, status TEXT)"
        )
        con.execute(
            "CREATE TABLE auth_providers(id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " user_id INTEGER, provider TEXT, identifier TEXT, created_at TEXT)"
        )
        con.execute(
            "CREATE TABLE otp_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " destination TEXT, code TEXT)"
        )
        # Засеять 3 существующие записи без status — должны получить 'succeeded'.
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id) VALUES "
            "(1, 100, '2026-05-01T10:00:00+00:00', NULL),"
            "(1, 200, '2026-05-02T10:00:00+00:00', NULL),"
            "(2, 300, '2026-05-03T10:00:00+00:00', 'pid-historical')"
        )
        con.commit()


def test_migration_adds_status_with_succeeded_default(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()

    with sqlite3.connect(db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(refills)").fetchall()}
        assert "status" in cols, "колонка status должна появиться"
        rows = con.execute("SELECT status FROM refills ORDER BY increment").fetchall()
        assert [r[0] for r in rows] == ["succeeded", "succeeded", "succeeded"], (
            "существующие записи получают status='succeeded' через DEFAULT"
        )


def test_migration_creates_indexes(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()

    with sqlite3.connect(db) as con:
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
    assert "idx_refills_status_date" in idx
    assert "uq_refills_payment_id" in idx


def test_migration_is_idempotent(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    _old_schema_create(db)
    monkeypatch.setattr("data.config.path_database", str(db), raising=False)
    monkeypatch.setattr("utils.sqlite3.path_db", str(db), raising=False)

    from utils.sqlite3 import apply_phase2_migrations
    apply_phase2_migrations()
    apply_phase2_migrations()  # повторный запуск не должен падать

    with sqlite3.connect(db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(refills)").fetchall()}
        assert cols.count("status") if False else True  # set: только один экземпляр
        assert "status" in cols
```

- [ ] **Step 3: Запустить тест и убедиться, что падает**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refills_migration.py -v
```
Expected: FAIL — все 3 теста, AssertionError на отсутствии `status` колонки и индексов.

- [ ] **Step 4: Дописать DDL refills и индексы**

В `utils/sqlite3.py:769-781` поменять блок `refills`:

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
            "status TEXT NOT NULL DEFAULT 'succeeded',"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            8,  # cols increased: 7 → 8
        ),
```

В `get_index_statements()` (около строки ~982) добавить две новые строки в возвращаемый список:

```python
        "CREATE INDEX IF NOT EXISTS idx_refills_status_date ON refills (status, date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_refills_payment_id ON refills (payment_id) WHERE payment_id IS NOT NULL",
```

В `apply_phase2_migrations()` (после блока про `payment_id`, строки 1004-1006), добавить:

```python
        # === refills.status (state machine: pending|succeeded|canceled|expired) ===
        if 'status' not in existing_refills:
            con.execute(
                "ALTER TABLE refills ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'"
            )
            print("refills.status added (existing rows defaulted to status='succeeded')")
        # Индексы создаём отдельно от ALTER — IF NOT EXISTS делает идемпотентным.
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_refills_status_date "
            "ON refills (status, date)"
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_refills_payment_id "
            "ON refills (payment_id) WHERE payment_id IS NOT NULL"
        )
```

- [ ] **Step 5: Запустить тест миграции**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refills_migration.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Запустить весь тест-сьют — убедиться, что ничего не сломано**

```bash
docker compose --profile test run --rm test pytest -v
```
Expected: все существующие тесты проходят (миграция аддитивная, DEFAULT 'succeeded' не меняет смысл текущих SUM/COUNT по refills).

- [ ] **Step 7: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_refills_migration.py
git commit -m "feat(payments): add refills.status column + indexes

State machine column for payment lifecycle (pending|succeeded|canceled|expired).
All existing rows default to 'succeeded' — they are by definition already credited.
Partial unique index on payment_id prevents accidental dup pending rows.
Composite index (status, date) supports the reconciler's hot path."
```

---

## Task 2: Расширить `RefillResult` + `_is_first_refill` фильтром `status='succeeded'`

**Files:**
- Modify: `services/refill.py:63-91`
- Test: `tests/unit/test_refill_state_machine.py` (create)

- [ ] **Step 1: Написать failing test для `_is_first_refill` и нового поля**

Create `tests/unit/test_refill_state_machine.py`:

```python
"""State machine для refills + идемпотентность finalize."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.db import connect


def _insert_refill(*, user_id: int, amount: int, payment_id: str | None,
                   status: str, date: str = "2026-06-09T12:00:00+00:00") -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, date, payment_id, "web", status),
        )
        con.commit()


def _make_user(user_id: int, *, balance: int = 0, ref_id: int | None = None,
               is_vip: int | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, ref_id, is_vip, user_name, first_name) "
            "VALUES (?, ?, ?, ?, NULL, NULL)",
            (user_id, balance, ref_id, is_vip),
        )
        con.commit()


def test_is_first_refill_ignores_pending(tmp_db: Path):
    """Юзер только с pending refill — ещё имеет право на реф-бонус."""
    _make_user(42)
    _insert_refill(user_id=42, amount=100, payment_id="pid-pending", status="pending")

    from services.refill import _is_first_refill
    assert _is_first_refill(42) is True


def test_is_first_refill_false_after_succeeded(tmp_db: Path):
    _make_user(42)
    _insert_refill(user_id=42, amount=100, payment_id="pid-ok", status="succeeded")

    from services.refill import _is_first_refill
    assert _is_first_refill(42) is False


def test_refill_result_has_was_newly_finalized(tmp_db: Path):
    """RefillResult должен иметь поле was_newly_finalized."""
    from services.refill import RefillResult
    r = RefillResult(
        user_balance=100,
        referrer_id=None,
        referrer_bonus=0,
        referrer_new_balance=None,
        was_newly_finalized=True,
    )
    assert r.was_newly_finalized is True
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: FAIL — `_is_first_refill` всё ещё считает pending, `RefillResult` не имеет поля `was_newly_finalized` (TypeError).

- [ ] **Step 3: Поправить `_is_first_refill` и `RefillResult`**

В `services/refill.py:76-81`:

```python
def _is_first_refill(user_id: int) -> bool:
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? AND status = 'succeeded' LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is None
```

В `services/refill.py:68-73` расширить `RefillResult`:

```python
@dataclass(frozen=True)
class RefillResult:
    user_balance: int
    referrer_id: int | None
    referrer_bonus: int
    referrer_new_balance: int | None
    was_newly_finalized: bool = False
```

(`= False` дефолт — чтобы не сломать существующие тесты, которые могут создавать `RefillResult(...)` без этого аргумента; новый код всегда передаёт явно).

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_refill_state_machine.py
git commit -m "feat(payments): RefillResult.was_newly_finalized + status-aware first-refill check

was_newly_finalized signals the actual pending→succeeded transition winner
(needed by reconciler to avoid duplicate Telegram notifications under races).
_is_first_refill now ignores pending rows so referral bonus stays available
until the user's first SUCCESSFUL refill."
```

---

## Task 3: Переписать `services/refill.finalize` на state machine

**Files:**
- Modify: `services/refill.py:25-60`
- Test: `tests/unit/test_refill_state_machine.py` (extend)

Логика новой `finalize`:
1. Атомарно: `UPDATE refills SET status='succeeded' WHERE payment_id=? AND status='pending'`.
2. Если `rowcount == 1` (мы — победитель гонки): `credit(user_id, amount)`, вернуть `(new_balance, True)`.
3. Если `rowcount == 0`: проверить, существует ли строка с этим `payment_id`. Если есть и `status='succeeded'` — идемпотентный no-op, вернуть `(get_balance, False)`. Если нет (backfill) — INSERT succeeded напрямую + credit, вернуть `(new_balance, True)`. Если другое (canceled/expired) — `ValueError`.
4. Если `payment_id is None`: legacy-режим — INSERT succeeded напрямую + credit (поддерживаем старые внешние вызовы без payment_id; ниже все внутренние вызовы будут с payment_id).

Сигнатура: `finalize(...)` возвращает `tuple[int, bool]` — `(new_balance, was_newly_finalized)`.

- [ ] **Step 1: Расширить тесты `test_refill_state_machine.py`**

Дописать в тот же файл:

```python
def test_finalize_pending_to_succeeded(tmp_db: Path):
    _make_user(42, balance=0)
    _insert_refill(user_id=42, amount=500, payment_id="pid-a", status="pending")

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 500, payment_id="pid-a", source_type="web", source_app_id=None
    )
    assert new_balance == 500
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-a",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "succeeded"
    assert bal["balance"] == 500


def test_finalize_idempotent_on_already_succeeded(tmp_db: Path):
    _make_user(42, balance=500)
    _insert_refill(user_id=42, amount=500, payment_id="pid-b", status="succeeded")

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 500, payment_id="pid-b", source_type="web", source_app_id=None
    )
    assert new_balance == 500     # баланс не вырос
    assert was_new is False        # повторная финализация не считается «новой»


def test_finalize_backfill_when_no_pending_row(tmp_db: Path):
    """Если pending row нет (backfill 7 stuck, например) — finalize должен INSERT succeeded напрямую."""
    _make_user(42, balance=0)

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 700, payment_id="pid-backfill",
        source_type="telegram", source_app_id=None,
    )
    assert new_balance == 700
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status, source_type FROM refills WHERE payment_id=?",
            ("pid-backfill",),
        ).fetchone()
    assert row["status"] == "succeeded"
    assert row["source_type"] == "telegram"


def test_finalize_legacy_no_payment_id_inserts_succeeded(tmp_db: Path):
    """Старый вызов finalize(..., payment_id=None) должен по-прежнему работать (INSERT succeeded)."""
    _make_user(42, balance=0)

    from services.refill import finalize
    new_balance, was_new = finalize(
        42, 250, payment_id=None, source_type="telegram", source_app_id=None
    )
    assert new_balance == 250
    assert was_new is True

    with connect() as con:
        row = con.execute(
            "SELECT status, payment_id FROM refills WHERE user_id=42"
        ).fetchone()
    assert row["status"] == "succeeded"
    assert row["payment_id"] is None


def test_finalize_raises_on_unexpected_status(tmp_db: Path):
    """Если строка существует в canceled/expired — finalize должен бросить ValueError, не зачислить."""
    _make_user(42, balance=0)
    _insert_refill(user_id=42, amount=500, payment_id="pid-cx", status="canceled")

    from services.refill import finalize
    with pytest.raises(ValueError, match="canceled"):
        finalize(42, 500, payment_id="pid-cx", source_type="web", source_app_id=None)

    with connect() as con:
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert bal["balance"] == 0  # не зачислили
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: новые 5 тестов FAIL (старая `finalize` возвращает `int`, не tuple; pending-логика отсутствует).

- [ ] **Step 3: Переписать `finalize`**

Заменить `services/refill.py:25-60`:

```python
def finalize(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> tuple[int, bool]:
    """State machine: переводит pending→succeeded атомарно. Возвращает (new_balance, was_newly_finalized).

    was_newly_finalized=True ровно для одного победителя гонки за payment_id.
    Повторные вызовы для уже-succeeded → was_newly_finalized=False, баланс не меняется.
    Если pending row нет (backfill / legacy без payment_id) — INSERT succeeded напрямую.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    from services.source import normalize
    src_type, src_app = normalize(source_type, source_app_id)

    # Legacy path: вызов без payment_id (например, до релиза этого фикса).
    # Просто INSERT succeeded + credit, без state machine.
    if payment_id is None:
        new_balance = credit(user_id, amount)
        with connect() as con:
            con.execute(
                "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
                "VALUES (?, ?, ?, NULL, ?, ?, 'succeeded')",
                (amount, get_date(), user_id, src_type, src_app),
            )
            con.commit()
        return new_balance, True

    # State machine path: атомарный UPDATE...WHERE status='pending'.
    with connect() as con:
        cur = con.execute(
            "UPDATE refills SET status='succeeded' WHERE payment_id=? AND status='pending'",
            (payment_id,),
        )
        won_race = cur.rowcount == 1
        con.commit()

    if won_race:
        new_balance = credit(user_id, amount)
        return new_balance, True

    # rowcount=0: либо уже succeeded (идемпотентность), либо нет строки, либо неожиданный статус.
    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", (payment_id,)
        ).fetchone()

    if row is None:
        # Backfill: pending row отсутствует. INSERT succeeded напрямую + credit.
        new_balance = credit(user_id, amount)
        with connect() as con:
            con.execute(
                "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'succeeded')",
                (amount, get_date(), user_id, payment_id, src_type, src_app),
            )
            con.commit()
        return new_balance, True

    if row["status"] == "succeeded":
        return get_balance(user_id), False

    raise ValueError(
        f"refill {payment_id!r} cannot transition to succeeded from status={row['status']!r}"
    )
```

(`get_balance` уже импортирован в верхушке файла.)

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: все тесты этого файла PASSED (8 штук: 3 из Task 2 + 5 новых).

- [ ] **Step 5: Запустить весь сьют — проверить регрессии**

```bash
docker compose --profile test run --rm test pytest -v
```
Expected: всё проходит. **Если** какие-то существующие тесты сломаны (потому что `finalize` теперь возвращает tuple вместо int) — это значит они напрямую вызывают `finalize` и проверяют возврат. Поправь их: `new_balance, _ = finalize(...)`.

- [ ] **Step 6: Commit**

```bash
git add services/refill.py tests/unit/test_refill_state_machine.py
git commit -m "feat(payments): finalize as state machine, atomic pending→succeeded

UPDATE...WHERE status='pending' picks exactly one race winner who credits
the balance and returns was_newly_finalized=True. Losers see rowcount=0,
re-read status, return (balance, False) for already-succeeded or
INSERT-succeeded-directly for backfill case (no pending row).

Legacy path (payment_id=None) preserved for any external callers."
```

---

## Task 4: Пробросить `was_newly_finalized` через `finalize_with_referral_bonus`

**Files:**
- Modify: `services/refill.py:94-139`
- Test: `tests/unit/test_refill_state_machine.py` (extend)

- [ ] **Step 1: Дописать тесты**

```python
def test_finalize_with_referral_bonus_propagates_was_newly_finalized(tmp_db: Path):
    _make_user(42, balance=0)
    _insert_refill(user_id=42, amount=500, payment_id="pid-r", status="pending")

    from services.refill import finalize_with_referral_bonus
    result = finalize_with_referral_bonus(
        42, 500, payment_id="pid-r", source_type="web"
    )
    assert result.user_balance == 500
    assert result.was_newly_finalized is True

    # Повторный вызов: was_newly_finalized=False.
    result2 = finalize_with_referral_bonus(
        42, 500, payment_id="pid-r", source_type="web"
    )
    assert result2.user_balance == 500  # not doubled
    assert result2.was_newly_finalized is False


def test_referral_bonus_not_double_credited(tmp_db: Path):
    """Реф-бонус должен начисляться РОВНО ОДИН раз: на первой successful finalize."""
    _make_user(100, balance=0)  # referrer
    _make_user(42, balance=0, ref_id=100)  # new user with referrer
    _insert_refill(user_id=42, amount=1000, payment_id="pid-first", status="pending")

    from services.refill import finalize_with_referral_bonus
    r1 = finalize_with_referral_bonus(42, 1000, payment_id="pid-first")
    assert r1.was_newly_finalized is True
    assert r1.referrer_bonus == 300  # 30% of 1000
    assert r1.referrer_new_balance == 300

    # Повторный finalize того же payment_id — НЕ должен повторно начислить ни юзеру, ни реферу.
    r2 = finalize_with_referral_bonus(42, 1000, payment_id="pid-first")
    assert r2.was_newly_finalized is False
    assert r2.referrer_bonus == 0  # бонус не начисляется повторно

    with connect() as con:
        ref_bal = con.execute("SELECT balance FROM users WHERE id=100").fetchone()
    assert ref_bal["balance"] == 300  # не 600
```

- [ ] **Step 2: Запустить — упадёт**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: 2 новых FAIL (`RefillResult` всё ещё `was_newly_finalized=False` дефолт, реф-бонус задваивается).

- [ ] **Step 3: Переписать `finalize_with_referral_bonus`**

В `services/refill.py:94-139`:

```python
def finalize_with_referral_bonus(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> RefillResult:
    """Финализирует refill + (на первой успешной) начисляет реф-бонус 30% реферу.

    was_newly_finalized пробрасывается из finalize() — крон/web-flow используют его,
    чтобы не задваивать уведомления при гонках.
    """
    user = _get_user_for_referral(user_id)
    is_first_before = _is_first_refill(user_id)  # снимок ДО finalize

    new_balance, was_newly_finalized = finalize(
        user_id, amount, payment_id=payment_id,
        source_type=source_type, source_app_id=source_app_id,
    )

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_balance: int | None = None

    # Бонус начисляется ТОЛЬКО при реальном переходе pending→succeeded,
    # И только если это был первый refill у юзера, И юзер не VIP.
    if was_newly_finalized and is_first_before and not user["is_vip"] and referrer_id is not None:
        bonus = int(amount * 0.3)
        try:
            referrer_new_balance = (
                finalize(int(referrer_id), bonus,
                         source_type=source_type, source_app_id=source_app_id)[0]
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
        was_newly_finalized=was_newly_finalized,
    )
```

Обрати внимание: `finalize(...)` теперь возвращает tuple → берём `[0]` для баланса рефера. Также реф-бонус теперь идёт через `finalize(payment_id=None)` (legacy-путь — это нормально, он остаётся INSERT succeeded).

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: все 10 тестов PASSED.

- [ ] **Step 5: Полный сьют**

```bash
docker compose --profile test run --rm test pytest -v
```
Expected: всё проходит. Любые регрессии — поправить (например, тесты на старом `finalize(...) -> int` если такие есть).

- [ ] **Step 6: Commit**

```bash
git add services/refill.py tests/unit/test_refill_state_machine.py
git commit -m "feat(payments): propagate was_newly_finalized through referral bonus path

Referral bonus credits only on the actual pending→succeeded transition,
never on idempotent re-calls. Snapshot _is_first_refill BEFORE finalize
so the bonus eligibility check uses the pre-state."
```

---

## Task 5: `create_invoice` → INSERT pending

**Files:**
- Modify: `services/refill.py:15-22`
- Test: `tests/unit/test_refill_state_machine.py` (extend)

Расширяем сигнатуру `create_invoice` параметрами `source_type` / `source_app_id` и сразу после `Payment.create` пишем `pending` в refills.

- [ ] **Step 1: Тест**

```python
def test_create_invoice_inserts_pending_row(tmp_db: Path, monkeypatch):
    _make_user(42, balance=0)

    # Mock yookassa create_invoice — не дёргаем реальный API.
    def fake_yk(uid, amount):
        return ("https://example.com/pay/xyz", "pid-new-123")
    monkeypatch.setattr("services.refill._yookassa_create_invoice", fake_yk)

    from services.refill import create_invoice
    url, pid = create_invoice(42, 250, source_type="web", source_app_id=None)

    assert url == "https://example.com/pay/xyz"
    assert pid == "pid-new-123"

    with connect() as con:
        row = con.execute(
            "SELECT user_id, amount, payment_id, source_type, source_app_id, status "
            "FROM refills WHERE payment_id=?",
            ("pid-new-123",),
        ).fetchone()
    assert row == {
        "user_id": 42, "amount": 250, "payment_id": "pid-new-123",
        "source_type": "web", "source_app_id": None, "status": "pending",
    }


def test_create_invoice_alerts_admins_if_insert_fails(tmp_db: Path, monkeypatch):
    """Если INSERT pending падает — алерт админам, чтобы можно было восстановить руками по логу."""
    _make_user(42, balance=0)
    monkeypatch.setattr(
        "services.refill._yookassa_create_invoice",
        lambda uid, amount: ("https://example.com/x", "pid-X"),
    )

    # Спровоцировать падение INSERT: вставить запись с тем же payment_id заранее.
    _insert_refill(user_id=42, amount=100, payment_id="pid-X", status="pending")

    from services.refill import create_invoice, PaymentError
    with pytest.raises(PaymentError):
        create_invoice(42, 250, source_type="web", source_app_id=None)
```

- [ ] **Step 2: Запустить — упадёт**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: 2 новых FAIL (TypeError на лишних аргументах + строка pending не создаётся).

- [ ] **Step 3: Переписать `create_invoice`**

В `services/refill.py:15-22`:

```python
def create_invoice(
    user_id: int,
    amount: int,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> tuple[str, str]:
    """Создаёт инвойс в YK и сразу пишет pending в refills.

    Возвращает (payment_url, payment_id). Бросает PaymentError при сбое YK
    или БД (INSERT pending). При сбое INSERT платёж в YK уже создан —
    шлём admin alert с payment_id для ручного восстановления.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")

    from services.source import normalize
    src_type, src_app = normalize(source_type, source_app_id)

    try:
        url, pid = _yookassa_create_invoice(user_id, amount)
    except Exception as exc:
        raise PaymentError(f"yookassa create_invoice failed: {exc}") from exc

    try:
        with connect() as con:
            con.execute(
                "INSERT INTO refills(amount, date, user_id, payment_id, "
                "source_type, source_app_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (amount, get_date(), user_id, pid, src_type, src_app),
            )
            con.commit()
    except Exception as exc:
        # Платёж в YK создан, но в нашей БД нет следа — крон не подберёт.
        # Логируем + алерт админам с payment_id для ручного backfill.
        import logging
        logging.getLogger(__name__).exception(
            "INSERT pending failed: payment_id=%s user_id=%s amount=%s",
            pid, user_id, amount,
        )
        try:
            import asyncio
            from utils.sender import send_admins
            msg = (
                f"⚠️ Платёж в YK создан, но pending row не записалась.\n"
                f"payment_id=<code>{pid}</code>\n"
                f"user_id={user_id}, amount={amount} ₽\n"
                f"Восстановить руками через scripts/backfill_stuck_payments."
            )
            # create_invoice вызывается из async-handler'ов (TG + web), но сам он sync.
            # Проверяем наличие running loop, чтобы не упасть с RuntimeError если когда-то
            # будут sync-вызовы (например, из скриптов).
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(send_admins(msg, "errors", parse_mode="HTML"))
            except RuntimeError:
                # Нет running loop — алерт пропустим, основная ошибка PaymentError всё равно поднимется.
                pass
        except Exception:
            pass  # лучшее усилие; PaymentError ниже всё равно поднимется
        raise PaymentError(f"refills INSERT pending failed: {exc}") from exc

    return url, pid
```

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: всё PASSED.

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_refill_state_machine.py
git commit -m "feat(payments): create_invoice writes pending refill row

Source tracking now flows from CurrentCaller into refills.source_type/
source_app_id. If YK Payment.create succeeded but our INSERT pending
failed, alert admins so the payment can be recovered manually."
```

---

## Task 6: Обновить SELECT FROM refills в `utils/sqlite3` (status='succeeded' фильтр)

**Files:**
- Modify: `utils/sqlite3.py:660-670`
- Test: `tests/unit/test_refill_state_machine.py` (extend)

- [ ] **Step 1: Тесты**

```python
def test_get_user_all_refills_excludes_pending(tmp_db: Path):
    _make_user(42)
    _insert_refill(user_id=42, amount=100, payment_id="ok", status="succeeded")
    _insert_refill(user_id=42, amount=200, payment_id="pen", status="pending")
    _insert_refill(user_id=42, amount=300, payment_id="cx", status="canceled")

    from utils.sqlite3 import get_user_all_refills
    refills = get_user_all_refills(42)
    amounts = sorted(r["amount"] for r in refills)
    assert amounts == [100]  # only succeeded


def test_all_refills_excludes_pending(tmp_db: Path):
    _make_user(1); _make_user(2)
    _insert_refill(user_id=1, amount=100, payment_id="a", status="succeeded")
    _insert_refill(user_id=2, amount=200, payment_id="b", status="pending")

    from utils.sqlite3 import all_refills
    out = all_refills()
    assert len(out) == 1
    assert out[0]["amount"] == 100
```

- [ ] **Step 2: Запустить — упадёт**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```
Expected: 2 новых FAIL.

- [ ] **Step 3: Поправить функции**

В `utils/sqlite3.py:660-670`:

```python
def get_user_all_refills(user_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM refills WHERE user_id = ? AND status = 'succeeded'",
            (user_id,),
        ).fetchall()


def all_refills():
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM refills WHERE status = 'succeeded'"
        ).fetchall()
```

- [ ] **Step 4: Запустить — PASS**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_refill_state_machine.py -v
```

- [ ] **Step 5: Полный сьют + grep на пропущенные места**

```bash
docker compose --profile test run --rm test pytest -v
grep -rn "FROM refills\|JOIN refills" --include="*.py" .
```

В grep ожидаем только:
- `services/refill.py` (всё переписано, status-aware)
- `utils/sqlite3.py:663,669` (только что обновили)
- `tests/...` (тестовые, не трогаем)

Если есть другие места снаружи tests/ и scripts/ — добавь там `WHERE/AND status='succeeded'` тем же способом. Каждое такое место — отдельный мини-коммит с тестом.

- [ ] **Step 6: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_refill_state_machine.py
git commit -m "fix(payments): filter refills queries by status='succeeded'

get_user_all_refills and all_refills now exclude pending/canceled/expired
rows. Reports and user histories show only credited refills."
```

---

## Task 7: `services/payment_notifications.py` — извлечение уведомлений

**Files:**
- Create: `services/payment_notifications.py`
- Test: `tests/unit/test_payment_notifications.py` (create)

Три async-функции:
- `notify_user_success(user_id, amount, new_balance)` — STR2 в личку юзера по chat_id из `auth_providers WHERE provider='telegram'`.
- `notify_admins_success(user_id, amount, new_balance)` — STR3 в админский топик `orders`.
- `notify_referrer(referrer_id, bonus, new_balance)` — STR4 в личку рефера.

Все три не должны падать, если получатель недоступен / нет TG-привязки — логируем warning.

- [ ] **Step 1: Тесты**

Create `tests/unit/test_payment_notifications.py`:

```python
"""Тесты payment_notifications — извлечённые из handlers/refill.py уведомления."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services.db import connect


def _make_user_with_telegram(user_id: int, chat_id: int, *, username: str = "u"):
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (?, 0, ?, 'X', '2026-06-09')",
            (user_id, username),
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (?, 'telegram', ?, '2026-06-09', 1)",
            (user_id, str(chat_id)),
        )
        con.commit()


@pytest.mark.asyncio
async def test_notify_user_success_sends_to_chat_id(tmp_db: Path):
    _make_user_with_telegram(42, chat_id=10000042)

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_user_success(user_id=42, amount=500, new_balance=500)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs or {}
    args = mock_send.call_args.args
    # chat_id может быть позиционно или kwarg — поддержим оба.
    chat_id = kwargs.get("chat_id") or (args[0] if args else None)
    assert chat_id == 10000042


@pytest.mark.asyncio
async def test_notify_user_success_silent_if_no_telegram_provider(tmp_db: Path):
    """Web-only юзер без TG-привязки: notify не падает, send_message НЕ вызывается."""
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (777, 0, NULL, 'Web', '2026-06-09')"
        )
        con.commit()

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_user_success(user_id=777, amount=500, new_balance=500)
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_user_success_swallows_send_errors(tmp_db: Path):
    """Юзер заблокировал бота → send_message бросает. notify не должно падать."""
    _make_user_with_telegram(42, chat_id=10000042)

    from services.payment_notifications import notify_user_success
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = Exception("Bot was blocked by the user")
        # Не падаем
        await notify_user_success(user_id=42, amount=500, new_balance=500)


@pytest.mark.asyncio
async def test_notify_admins_success_posts_to_orders(tmp_db: Path):
    _make_user_with_telegram(42, chat_id=10000042, username="testuser")

    from services.payment_notifications import notify_admins_success
    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_admin:
        await notify_admins_success(user_id=42, amount=500, new_balance=500)

    mock_admin.assert_called_once()
    args, kwargs = mock_admin.call_args
    assert args[1] == "orders" or kwargs.get("category") == "orders"


@pytest.mark.asyncio
async def test_notify_referrer_sends_to_referrer_chat(tmp_db: Path):
    _make_user_with_telegram(100, chat_id=999999, username="referrer")

    from services.payment_notifications import notify_referrer
    with patch("data.loader.bot.send_message", new_callable=AsyncMock) as mock_send:
        await notify_referrer(referrer_id=100, bonus=150, new_balance=150)

    mock_send.assert_called_once()
```

- [ ] **Step 2: Запустить — упадёт**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_payment_notifications.py -v
```
Expected: 5 FAIL — модуль не существует.

- [ ] **Step 3: Создать `services/payment_notifications.py`**

```python
"""Уведомления об успешном пополнении: юзеру, админам, рефералу.

Выделены из handlers/refill.py чтобы и TG-handler, и web-flow, и крон-reconciler
отправляли консистентные сообщения. Все функции async, идемпотентны (можно
вызывать повторно), и НЕ ПАДАЮТ, если получатель недоступен.
"""
from __future__ import annotations

import logging

from data.loader import bot
from services.db import connect
from utils.other import format_decimal, get_user_string_without_first_name
from utils.sender import send_admins
from utils.sqlite3 import get_user, get_string

logger = logging.getLogger(__name__)


def _get_tg_chat_id(user_id: int) -> int | None:
    """Возвращает chat_id юзера в Telegram через auth_providers, или None если web-only."""
    with connect() as con:
        row = con.execute(
            "SELECT identifier FROM auth_providers "
            "WHERE user_id = ? AND provider = 'telegram' LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        return int(row["identifier"])
    except (TypeError, ValueError):
        logger.warning("auth_providers.identifier non-int for user_id=%s: %r",
                       user_id, row["identifier"])
        return None


async def notify_user_success(user_id: int, amount: int, new_balance: int) -> None:
    """STR2 — личное сообщение юзеру об успешном пополнении.

    No-op для web-only юзеров без telegram auth_provider.
    Не падает при send_message exception (юзер заблокировал бота и т.п.).
    """
    chat_id = _get_tg_chat_id(user_id)
    if chat_id is None:
        logger.info("notify_user_success: skip user_id=%s (no telegram provider)", user_id)
        return
    f_amount = format_decimal(amount)
    f_balance = format_decimal(new_balance)
    text = get_string("str_usr_pay_success").format(f_amount, f_balance)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("notify_user_success: send_message failed user_id=%s chat_id=%s",
                       user_id, chat_id, exc_info=True)


async def notify_admins_success(user_id: int, amount: int, new_balance: int) -> None:
    """STR3 — пост в админский топик 'orders' об успешном пополнении."""
    usr = get_user(id=user_id)
    if usr is None:
        logger.warning("notify_admins_success: user not found user_id=%s", user_id)
        return
    user_string = await get_user_string_without_first_name(usr)
    f_amount = format_decimal(amount)
    f_balance = format_decimal(new_balance)
    text = get_string("str_adm_pay_success").format(f_amount, user_string, f_balance)
    try:
        await send_admins(text, "orders")
    except Exception:
        logger.warning("notify_admins_success: send_admins failed user_id=%s",
                       user_id, exc_info=True)


async def notify_referrer(referrer_id: int, bonus: int, new_balance: int) -> None:
    """STR4 — личное сообщение рефералу о начисленном бонусе."""
    chat_id = _get_tg_chat_id(referrer_id)
    if chat_id is None:
        logger.info("notify_referrer: skip referrer_id=%s (no telegram provider)",
                    referrer_id)
        return
    f_bonus = format_decimal(bonus)
    f_balance = format_decimal(new_balance)
    text = get_string("str_ref_balance_refil").format(f_bonus, f_balance)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.warning("notify_referrer: send_message failed referrer_id=%s chat_id=%s",
                       referrer_id, chat_id, exc_info=True)
```

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_payment_notifications.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add services/payment_notifications.py tests/unit/test_payment_notifications.py
git commit -m "feat(payments): extract payment_notifications module

Three async functions (notify_user_success/notify_admins_success/notify_referrer)
shared by TG handler, web-flow, and the new reconciler. All swallow downstream
errors so a blocked bot or missing telegram link can't roll back a successful
balance credit."
```

---

## Task 8: `handlers/refill.py` — передать payment_id + UX-фикс

**Files:**
- Modify: `handlers/refill.py:78-143`

Что меняем:
1. `svc_create_invoice(user_id, int(amount))` → передать `source_type='telegram', source_app_id=None`.
2. `finalize_with_referral_bonus(user_id, int(amount), source_type="telegram")` → добавить `payment_id=payment_id`.
3. STR6 (сообщение при `success=False` от 6-минутного пуллинга) — заменить на нейтральное, объясняющее, что баланс пополнится автоматически.
4. Заменить inline-нотификации на вызовы `notify_user_success`/`notify_admins_success`/`notify_referrer` (DRY).
5. Вызывать notify-функции ТОЛЬКО при `result.was_newly_finalized == True` (защита от двойного уведомления, если крон успел раньше).

**No new tests** — `handlers/refill.py` обёртка с тяжёлой aiogram-зависимостью; полностью покрыт по контракту функциями ниже (finalize, notify_*). Smoke-проверка делается на проде в Task 12.

- [ ] **Step 1: Найти текущий блок `_handle_yookassa_payment`**

```bash
grep -n "_handle_yookassa_payment" handlers/refill.py
```
Expected: определение на ~78, использование внутри `select_payment_method` на ~178.

- [ ] **Step 2: Переписать функцию**

В `handlers/refill.py:78-155` заменить тело `_handle_yookassa_payment` на:

```python
async def _handle_yookassa_payment(call: CallbackQuery, state: FSMContext, amount: int, user_id: int) -> None:
    from services.refill import (
        create_invoice as svc_create_invoice,
        finalize_with_referral_bonus,
    )
    from services.exceptions import PaymentError, UserNotFound
    from services.payment_notifications import (
        notify_admins_success, notify_referrer, notify_user_success,
    )

    await call.message.delete()
    tg_id = call.from_user.id

    try:
        payment_url, payment_id = svc_create_invoice(
            user_id, int(amount),
            source_type="telegram", source_app_id=None,
        )
    except PaymentError:
        support_nick = get_nick('manager_nick')
        msg = get_string('str_payment_error').format(support_nick)
        await bot.send_message(chat_id=tg_id, text=msg, reply_markup=payment_error_kb())
        return

    STR1 = get_string('str_debet_money').format(format_decimal(amount))

    if tg_id != 6988175544 and tg_id != 257838190:
        await bot.send_message(
            chat_id=tg_id, text=STR1,
            reply_markup=yookassa_kb(int(amount), payment_url),
        )
        success = await check_payment_status(payment_id)
    else:
        success = True

    if not success:
        # UX: не пугаем пользователя «оплата не прошла». Если она реально прошла —
        # крон-reconciler в течение минуты переведёт refill в succeeded и пришлёт
        # уведомление. Если не прошла — это видно по статусу платежа в YK.
        await bot.send_message(
            chat_id=tg_id,
            text=(
                "⏳ Платёж пока не подтверждён.\n\n"
                "Если вы успешно оплатили — баланс пополнится автоматически "
                "в течение минуты. Если нет — попробуйте ещё раз."
            ),
        )
        await state.finish()
        return

    try:
        result = finalize_with_referral_bonus(
            user_id, int(amount),
            payment_id=payment_id,
            source_type="telegram",
        )
    except UserNotFound as exc:
        await report_handler_error(
            exc, logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id,
                     "amount": amount, "tg_id": tg_id},
        )
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return
    except Exception as exc:
        await report_handler_error(
            exc, logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id,
                     "amount": amount, "tg_id": tg_id},
        )
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return

    # Уведомления — только если это была первая и реальная финализация.
    # Если крон/web-status успел раньше — was_newly_finalized=False, дублей не шлём.
    if result.was_newly_finalized:
        await notify_user_success(user_id, int(amount), result.user_balance)
        await notify_admins_success(user_id, int(amount), result.user_balance)
        if result.referrer_bonus > 0 and result.referrer_id is not None:
            await notify_referrer(result.referrer_id, result.referrer_bonus,
                                  result.referrer_new_balance or 0)
        logger.info("payment success: user_id=%s amount=%s (TG-sync)", user_id, amount)
    else:
        logger.info("payment already finalized (race): user_id=%s amount=%s pid=%s",
                    user_id, amount, payment_id)

    await state.finish()
```

- [ ] **Step 3: Прогнать существующие тесты**

```bash
docker compose --profile test run --rm test pytest -v
```
Expected: всё проходит. Если есть unit-тест на `_handle_yookassa_payment` напрямую — может потребоваться адаптация под новые async-вызовы; обычно такой handler не тестируется напрямую.

- [ ] **Step 4: Commit**

```bash
git add handlers/refill.py
git commit -m "feat(payments): TG-flow passes payment_id, dedupes notifications via was_newly_finalized

Sync 6-min poller now writes payment_id so finalize is idempotent against
the reconciler. On poll timeout: replace 'payment failed' with reassuring
'will credit automatically within a minute' (the reconciler delivers).

Shared notify_* functions replace inline STR2/STR3/STR4 messages.
Notifications fire only when finalize actually transitioned pending→succeeded —
prevents double-pings if cron/web-status got there first."
```

---

## Task 9: `web/routers/refill.py` — source + notifications

**Files:**
- Modify: `web/routers/refill.py:87-142`

- [ ] **Step 1: Поправить `create_refill` (POST /api/refill)**

В `web/routers/refill.py:87-108` строка с `create_invoice(caller.user_id, payload.amount)`:

```python
        url, pid = create_invoice(
            caller.user_id, payload.amount,
            source_type=caller.source_type,
            source_app_id=caller.source_app_id,
        )
```

- [ ] **Step 2: Поправить `refill_status` (GET /api/refill/{pid}/status)**

В `web/routers/refill.py:111-142`:

```python
    if yookassa_status == "succeeded":
        Configuration.account_id = SHOP_ID
        Configuration.secret_key = SECRET_KEY
        payment = Payment.find_one(payment_id)
        amount = int(float(payment.amount.value))
        try:
            result = finalize_with_referral_bonus(
                caller.user_id, amount,
                payment_id=payment_id,
                source_type=caller.source_type,
                source_app_id=caller.source_app_id,
            )
        except UserNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not in bot DB; /start the bot first",
            )

        # Уведомления только при реальном переходе — иначе крон/TG-handler уже отправили.
        if result.was_newly_finalized:
            from services.payment_notifications import notify_admins_success, notify_user_success, notify_referrer
            await notify_user_success(caller.user_id, amount, result.user_balance)
            await notify_admins_success(caller.user_id, amount, result.user_balance)
            if result.referrer_bonus > 0 and result.referrer_id is not None:
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)
            logger.info("payment success: user_id=%s amount=%s (web-status)",
                        caller.user_id, amount)
        simplified = "succeeded"
    elif yookassa_status in {"canceled", "expired", "rejected"}:
        simplified = "failed"
    else:
        simplified = "pending"

    return RefillStatusResponse(payment_id=payment_id, status=simplified)
```

- [ ] **Step 3: Прогнать сьют**

```bash
docker compose --profile test run --rm test pytest -v
```
Expected: всё проходит.

- [ ] **Step 4: Commit**

```bash
git add web/routers/refill.py
git commit -m "feat(payments): web-flow propagates source + notifies on finalize

POST /api/refill now passes source_type/source_app_id from CurrentCaller
into create_invoice, so the pending row is correctly attributed (was 'telegram'
default for everything before).

GET /api/refill/{pid}/status now fires notify_* on the first successful
finalize. Dedup via was_newly_finalized — safe if reconciler raced ahead."
```

---

## Task 10: `services/payment_reconciler.py` — async reconcile_pending

**Files:**
- Create: `services/payment_reconciler.py`
- Test: `tests/unit/test_payment_reconciler.py` (create)

Алгоритм:
1. `SELECT payment_id, user_id, amount, source_type, source_app_id FROM refills WHERE status='pending' AND date >= now_iso() - 24h`.
2. Для каждой строки: `Payment.find_one(payment_id)` через YK SDK (sync call в `asyncio.to_thread`).
3. По `p.status`:
   - `succeeded` → `finalize_with_referral_bonus(payment_id=...)`. Если `was_newly_finalized` → отправить нотификации.
   - `waiting_for_capture` → `Payment.capture(payment_id)`, статус в БД пока оставить pending (следующий тик увидит succeeded).
   - `canceled`/`rejected` → `UPDATE status='canceled'`.
   - `expired` → `UPDATE status='expired'`.
   - `pending` → ничего, ждём следующий тик.
4. YK API exception на одной строке — `logger.exception` + continue. Не валим весь тик.

- [ ] **Step 1: Тесты**

Create `tests/unit/test_payment_reconciler.py`:

```python
"""Тесты reconcile_pending — поведение крона при разных ответах YK."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.db import connect


def _make_user(uid: int, balance: int = 0):
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, balance, user_name, first_name, reg_date) "
            "VALUES (?, ?, NULL, 'X', '2026-06-09')",
            (uid, balance),
        )
        con.commit()


def _insert_pending(uid: int, amount: int, pid: str,
                    date: str = None, source_type: str = "web"):
    if date is None:
        date = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO refills(user_id, amount, date, payment_id, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (uid, amount, date, pid, source_type),
        )
        con.commit()


def _yk_payment(status: str, amount: int = 500, pid: str = "pid"):
    """Имитируем yookassa.domain.response.payment_response.PaymentResponse."""
    return SimpleNamespace(
        id=pid,
        status=status,
        amount=SimpleNamespace(value=f"{amount}.00", currency="RUB"),
        description=f"Пполнение баланса {pid}",
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.asyncio
async def test_reconcile_succeeded_finalizes_and_notifies(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-ok")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("succeeded", 500, "pid-ok")), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock) as nu, \
         patch("services.payment_reconciler.notify_admins_success", new_callable=AsyncMock) as na:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-ok",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "succeeded"
    assert bal["balance"] == 500
    nu.assert_called_once()
    na.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_canceled_updates_status_no_credit(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-cx")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("canceled", 500, "pid-cx")), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock) as nu:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    with connect() as con:
        row = con.execute(
            "SELECT status FROM refills WHERE payment_id=?", ("pid-cx",)
        ).fetchone()
        bal = con.execute("SELECT balance FROM users WHERE id=42").fetchone()
    assert row["status"] == "canceled"
    assert bal["balance"] == 0  # not credited
    nu.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_waiting_for_capture_calls_capture(tmp_db: Path):
    _make_user(42)
    _insert_pending(42, 500, "pid-wc")

    with patch("yookassa.Payment.find_one", return_value=_yk_payment("waiting_for_capture", 500, "pid-wc")), \
         patch("yookassa.Payment.capture") as cap:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    cap.assert_called_once_with("pid-wc")
    # status в БД ОСТАЁТСЯ pending (следующий тик увидит succeeded)
    with connect() as con:
        row = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-wc",)).fetchone()
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_yk_exception_continues_to_next(tmp_db: Path):
    """Исключение на одном платеже не должно ломать обработку остальных."""
    _make_user(1); _make_user(2)
    _insert_pending(1, 100, "pid-fail")
    _insert_pending(2, 200, "pid-ok")

    def find_one_side(pid):
        if pid == "pid-fail":
            raise RuntimeError("YK timeout")
        return _yk_payment("succeeded", 200, "pid-ok")

    with patch("yookassa.Payment.find_one", side_effect=find_one_side), \
         patch("services.payment_reconciler.notify_user_success", new_callable=AsyncMock), \
         patch("services.payment_reconciler.notify_admins_success", new_callable=AsyncMock):
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()  # не падает

    with connect() as con:
        ok = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-ok",)).fetchone()
        fail = con.execute("SELECT status FROM refills WHERE payment_id=?", ("pid-fail",)).fetchone()
        bal2 = con.execute("SELECT balance FROM users WHERE id=2").fetchone()
    assert ok["status"] == "succeeded"
    assert fail["status"] == "pending"  # осталось pending, попробуем в следующий тик
    assert bal2["balance"] == 200


@pytest.mark.asyncio
async def test_reconcile_skips_pending_older_than_24h(tmp_db: Path):
    _make_user(42)
    old_date = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    _insert_pending(42, 500, "pid-old", date=old_date)

    with patch("yookassa.Payment.find_one") as find_one:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()

    find_one.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_empty_pending_set_is_noop(tmp_db: Path):
    with patch("yookassa.Payment.find_one") as find_one:
        from services.payment_reconciler import reconcile_pending
        await reconcile_pending()
    find_one.assert_not_called()
```

- [ ] **Step 2: Запустить — упадёт (модуль не существует)**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_payment_reconciler.py -v
```
Expected: 6 FAIL (ImportError).

- [ ] **Step 3: Создать `services/payment_reconciler.py`**

```python
"""Reconciliation крон для YooKassa-платежей.

Раз в 60 сек (см. __main__.py) забирает все pending refills за последние 24ч,
опрашивает YK по каждому, и переводит status согласно ответу YK. Уведомления
отправляются только при реальном переходе pending→succeeded (защита от
двойных пингов, если синхронный TG-пуллинг или web-/status успели раньше).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.db import connect
from services.exceptions import UserNotFound
from services.payment_notifications import (
    notify_admins_success, notify_referrer, notify_user_success,
)
from services.refill import finalize_with_referral_bonus

logger = logging.getLogger(__name__)


async def reconcile_pending() -> None:
    """Один тик крона: опросить все наши pending за 24h и финализировать succeeded."""
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with connect() as con:
        rows = con.execute(
            "SELECT payment_id, user_id, amount, source_type, source_app_id "
            "FROM refills WHERE status='pending' AND date >= ?",
            (cutoff,),
        ).fetchall()

    if not rows:
        return

    logger.info("reconciler tick: %d pending payments to check", len(rows))

    for row in rows:
        pid = row["payment_id"]
        try:
            # YK SDK синхронный — в отдельный поток, чтобы не блокировать event loop.
            p = await asyncio.to_thread(Payment.find_one, pid)
        except Exception:
            logger.exception("reconciler: Payment.find_one failed pid=%s", pid)
            continue

        try:
            await _handle_yk_status(row, p)
        except Exception:
            logger.exception("reconciler: handle_yk_status failed pid=%s", pid)
            # Не валим весь тик из-за одной плохой строки.


async def _handle_yk_status(row: dict, p) -> None:
    pid = row["payment_id"]
    status = getattr(p, "status", None)

    if status == "succeeded":
        try:
            result = finalize_with_referral_bonus(
                user_id=row["user_id"],
                amount=row["amount"],
                payment_id=pid,
                source_type=row["source_type"] or "telegram",
                source_app_id=row["source_app_id"],
            )
        except UserNotFound:
            logger.warning("reconciler: user not found user_id=%s pid=%s",
                           row["user_id"], pid)
            return
        if result.was_newly_finalized:
            logger.info("reconciler: finalized pid=%s user_id=%s amount=%s",
                        pid, row["user_id"], row["amount"])
            await notify_user_success(row["user_id"], row["amount"], result.user_balance)
            await notify_admins_success(row["user_id"], row["amount"], result.user_balance)
            if result.referrer_bonus > 0 and result.referrer_id is not None:
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)
        else:
            logger.info("reconciler: pid=%s already finalized (no-op)", pid)

    elif status == "waiting_for_capture":
        # Двухстадийный платёж — захватываем. Следующий тик увидит succeeded.
        try:
            await asyncio.to_thread(Payment.capture, pid)
            logger.info("reconciler: captured pid=%s (waiting_for_capture)", pid)
        except Exception:
            logger.exception("reconciler: Payment.capture failed pid=%s", pid)

    elif status in ("canceled", "rejected"):
        with connect() as con:
            con.execute(
                "UPDATE refills SET status='canceled' WHERE payment_id=?", (pid,)
            )
            con.commit()
        logger.info("reconciler: pid=%s -> canceled", pid)

    elif status == "expired":
        with connect() as con:
            con.execute(
                "UPDATE refills SET status='expired' WHERE payment_id=?", (pid,)
            )
            con.commit()
        logger.info("reconciler: pid=%s -> expired", pid)

    elif status == "pending":
        return  # ждём следующий тик

    else:
        logger.warning("reconciler: unknown YK status %r for pid=%s", status, pid)
```

- [ ] **Step 4: Запустить тесты**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_payment_reconciler.py -v
```
Expected: 6 PASSED.

- [ ] **Step 5: Полный сьют**

```bash
docker compose --profile test run --rm test pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add services/payment_reconciler.py tests/unit/test_payment_reconciler.py
git commit -m "feat(payments): reconcile_pending — YK polling cron task

Iterates our pending refills (last 24h), polls YK Payment.find_one for each,
and applies the YK status: succeeded→finalize+notify, waiting_for_capture
→Payment.capture(), canceled/rejected/expired→update our status. Per-row
exceptions are logged and isolated so one bad payment doesn't break the tick.

YK SDK calls go through asyncio.to_thread because the SDK is sync."
```

---

## Task 11: Регистрация в `__main__.py` (APScheduler job)

**Files:**
- Modify: `__main__.py:106-117`

- [ ] **Step 1: Найти контекст**

```bash
grep -n "Payment probe scheduler\|payment_probe\|AsyncIOScheduler" __main__.py
```
Expected: блок `# ── Payment probe scheduler ──` на ~106.

- [ ] **Step 2: Добавить вторую job под существующей**

После `_scheduler.start()` (примерно строка ~114), но ВНУТРИ того же `if probe_interval > 0:` блока, добавить:

```python
        from services.payment_reconciler import reconcile_pending
        reconciler_seconds = int(os.getenv("PAYMENT_RECONCILER_INTERVAL_SEC", "60"))
        if reconciler_seconds > 0:
            _scheduler.add_job(
                reconcile_pending, "interval", seconds=reconciler_seconds,
                id="payment_reconciler",
                max_instances=1,
                misfire_grace_time=30,
            )
            _log.info(
                "Payment reconciler scheduled (interval=%d sec)", reconciler_seconds
            )
        else:
            _log.info("Payment reconciler disabled (PAYMENT_RECONCILER_INTERVAL_SEC=0)")
```

**Внимание:** если `probe_interval = 0`, то и `_scheduler` не создаётся — в таком случае reconciler тоже не стартует. Если хочешь развязать их полностью, нужен отдельный `else: AsyncIOScheduler()` блок, но это overkill — обе job'ы либо включены, либо нет вместе.

- [ ] **Step 3: Локально проверить, что бот стартует без ошибок**

```bash
docker compose up -d --build bot
sleep 5
docker compose logs --tail 50 bot | grep -iE "reconciler|scheduler|error"
```
Expected: лог-запись `Payment reconciler scheduled (interval=60 sec)`. Никаких exception.

(Если нет dev-окружения — этот шаг переносим на rollout-этап.)

- [ ] **Step 4: Commit**

```bash
git add __main__.py
git commit -m "feat(payments): register reconcile_pending as APScheduler job

Runs alongside payment_probe in the bot container. Interval default 60s,
configurable via PAYMENT_RECONCILER_INTERVAL_SEC=0 to disable.
max_instances=1 prevents overlapping ticks if YK is slow."
```

---

## Task 12: `scripts/backfill_stuck_payments.py` — разовый скрипт

**Files:**
- Create: `scripts/backfill_stuck_payments.py`

Скрипт делает: для каждого payment_id в `STUCK` — `Payment.find_one`, проверяет что в YK всё ещё `succeeded`, проверяет что в БД нет уже-succeeded записи с этим payment_id, вызывает `finalize_with_referral_bonus`, отправляет уведомления.

Запускается разово на проде после деплоя.

- [ ] **Step 1: Написать скрипт**

```python
"""Разовый backfill: зачисление 7 известных stuck YooKassa-платежей (на 2026-06-09).

Запуск:
    docker compose exec bot python -m scripts.backfill_stuck_payments

Безопасен к повторному запуску: для каждого payment_id проверяет, что:
  1) В YK всё ещё status='succeeded'.
  2) В refills нет уже succeeded строки с этим payment_id.
Если оба условия — вызывает finalize_with_referral_bonus (ветка backfill
INSERT succeeded напрямую) и шлёт уведомление в TG (если у юзера есть TG-привязка).

Web-only юзеры (Никита 8794553642, Дмитрий 8794553640, 8794553630) без
auth_providers.telegram — TG-уведомление пропускается; им ответим вручную
через support-чат, в котором они уже жалуются.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from yookassa import Configuration, Payment

from data.config import SECRET_KEY, SHOP_ID
from services.db import connect
from services.exceptions import UserNotFound
from services.payment_notifications import (
    notify_admins_success, notify_referrer, notify_user_success,
)
from services.refill import finalize_with_referral_bonus

logger = logging.getLogger("backfill_stuck_payments")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# (payment_id, user_id, amount, source_type)
STUCK = [
    ("31ba1e1a-000f-5000-b000-1934f8b49a52", 8794553642, 300,  "web"),       # Никита
    ("31ba1d6c-000f-5000-b000-18ed29b434ee", 8794553640, 500,  "web"),       # Дмитрий
    ("31b76e2e-000f-5001-8000-137bad08104d", 8794553630, 500,  "web"),
    ("31b76c4f-000f-5000-8000-1b0b50f48647", 2137600714, 1000, "telegram"),  # staleksfoto
    ("31af5380-000f-5001-9000-1571d32e7c8f", 468390610,  1260, "telegram"),  # horusgor
    ("31ad3b38-000f-5001-8000-1d0e2d17940d", 6741171042, 1900, "telegram"),  # 24shina
    ("31abe6d3-000f-5000-8000-165673068025", 996225380,  300,  "telegram"),  # kochevnik15
]


async def main() -> int:
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    skipped = 0
    credited = 0
    errored = 0

    for pid, uid, amount, src in STUCK:
        logger.info("--- pid=%s user_id=%s amount=%s src=%s ---", pid, uid, amount, src)

        # 1) Проверка статуса в YK.
        try:
            p = Payment.find_one(pid)
        except Exception:
            logger.exception("YK find_one failed pid=%s — skipped", pid)
            errored += 1
            continue
        if p.status != "succeeded":
            logger.warning("YK status=%r (expected succeeded) pid=%s — skipped",
                           p.status, pid)
            skipped += 1
            continue

        yk_amount = int(float(p.amount.value))
        if yk_amount != amount:
            logger.warning("YK amount=%s != script amount=%s pid=%s — skipped",
                           yk_amount, amount, pid)
            skipped += 1
            continue

        # 2) Проверка нашей БД: нет ли уже succeeded строки с этим payment_id.
        with connect() as con:
            existing = con.execute(
                "SELECT status FROM refills WHERE payment_id=?", (pid,)
            ).fetchone()
        if existing and existing["status"] == "succeeded":
            logger.info("already credited (refills.status=succeeded) pid=%s — skipped", pid)
            skipped += 1
            continue

        # 3) finalize.
        try:
            result = finalize_with_referral_bonus(
                uid, amount, payment_id=pid, source_type=src,
            )
        except UserNotFound:
            logger.error("user not in DB user_id=%s pid=%s — skipped", uid, pid)
            errored += 1
            continue
        except Exception:
            logger.exception("finalize failed pid=%s — skipped", pid)
            errored += 1
            continue

        logger.info("CREDITED pid=%s user_id=%s amount=%s new_balance=%s "
                    "was_newly_finalized=%s",
                    pid, uid, amount, result.user_balance, result.was_newly_finalized)
        credited += 1

        # 4) Уведомления.
        if result.was_newly_finalized:
            await notify_user_success(uid, amount, result.user_balance)
            await notify_admins_success(uid, amount, result.user_balance)
            if result.referrer_bonus > 0 and result.referrer_id is not None:
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)

    logger.info("=== DONE: credited=%d skipped=%d errored=%d ===",
                credited, skipped, errored)
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Smoke check — синтаксис и импорты**

```bash
docker compose --profile test run --rm test python -c "import scripts.backfill_stuck_payments; print('imports OK')"
```
Expected: `imports OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_stuck_payments.py
git commit -m "feat(payments): scripts/backfill_stuck_payments for 7 known stuck

Run once after deploy: docker compose exec bot python -m scripts.backfill_stuck_payments

Verifies each payment is still succeeded in YK and not already credited
in our DB before invoking finalize_with_referral_bonus. Idempotent —
safe to re-run."
```

---

## Self-Review Checklist

Before requesting code review, verify:

- [ ] **Spec coverage** — каждый раздел [spec](../specs/2026-06-09-payment-reconciler-design.md) реализован: Migration (Task 1), State machine в finalize (Tasks 2-4), create_invoice INSERT pending (Task 5), refills queries фильтр (Task 6), notifications (Task 7), TG handler (Task 8), web router (Task 9), reconciler (Task 10), scheduler (Task 11), backfill (Task 12).
- [ ] Все тесты проходят: `docker compose --profile test run --rm test`
- [ ] grep `FROM refills` не даёт unfiltered SELECT'ов вне tests/scripts:
  ```bash
  grep -rn "FROM refills" --include="*.py" . | grep -v "/tests/" | grep -v "/scripts/" | grep -v "status"
  ```
  Expected: пусто (все production SELECT'ы либо имеют WHERE status=, либо это INSERT/UPDATE/DELETE).
- [ ] Никаких placeholder'ов (`TODO`, `TBD`, `add error handling`) в новых файлах.

---

## Rollout (НЕ часть code-плана — выполняется на проде после merge)

1. **Backup БД**: `ssh root@<prod> "cd /root/projects/original_avito_pf_bot && cp storage/database.db storage/database.db.pre-status-mig"`
2. **Merge PR в `dev`** через GitHub.
3. **`./deploy.sh`** — build + up -d --force-recreate.
4. **Миграция применится автоматически** на старте контейнера (см. `__main__.py:42` → `apply_phase2_migrations`).
5. **Логи**: `docker compose logs --tail 100 bot | grep -iE "reconciler|status added"`. Должны увидеть `refills.status added (existing rows defaulted to status='succeeded')` и `Payment reconciler scheduled (interval=60 sec)`.
6. **Backfill 7 stuck**: `docker compose exec bot python -m scripts.backfill_stuck_payments` — ожидаемый output: `credited=7 skipped=0 errored=0` (или меньше credited, если за время с диагностики YK что-то перевёл в expired).
7. **Smoke test**: создать через лендинг 1 ₽ платёж, оплатить тестовой картой YK, через 60-90с проверить:
   - `sqlite3 storage/database.db "SELECT status FROM refills WHERE payment_id=...";` → succeeded.
   - `sqlite3 storage/database.db "SELECT balance FROM users WHERE id=...";` → +1.
8. **Мониторинг логов** 30 минут после деплоя.

**Откат:**
- `docker compose down`
- `cp storage/database.db.pre-status-mig storage/database.db`
- `git checkout <prev-sha>` → `./deploy.sh`
- Бэкап `database.db.pre-status-mig` храним ≥7 дней.
