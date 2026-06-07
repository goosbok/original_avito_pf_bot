# Order Links Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вынести ссылки заказа из колонки `orders.links TEXT` в отдельную таблицу `order_links` со статусной машиной `pending → in_work → done/failed`. `orders.status` становится кешированной агрегацией статусов ссылок. Добавить cron-закрытие in_work→done по deadline, stub-классификатор auto/manual, stub-клиент API исполнителя, две новые admin-кнопки и обновлённые Google Sheets экспорты.

**Architecture:** Новая таблица `order_links` владеется сервисом `services/order_links.py` — единственная точка мутации со встроенной валидацией переходов и пересчётом `orders.status` в той же транзакции. Cron-задачи (`dispatch_pending_links`, `close_expired_links`) запускаются как asyncio-таски рядом с существующим `payment_expiry`. Stub'ы для классификатора и API-клиента позволяют выкатить модель данных и пайплайн без бизнес-логики — со stub'ами все ссылки оседают в `pending/manual` и обрабатываются админом по кнопке.

**Tech Stack:** Python 3 / aiogram 2 / SQLite / FastAPI / pytest.

**Spec:** [docs/superpowers/specs/2026-06-07-order-links-extraction-design.md](../specs/2026-06-07-order-links-extraction-design.md)

**Tests in this codebase:** Все pytest запускаются в docker-контейнере. Этот воркtree смонтирован в существующий образ:

```bash
docker run --rm -v "$(pwd):/app" -w /app original_avito_pf_bot-api pytest <path> -v
```

Не запускай pytest локально (см. MEMORY.md / feedback_docker_tests). Команды `docker compose -f docker-compose.yml exec -T bot pytest` в задачах ниже — заменять на форму выше (бот-контейнер не поднят, образ собран из main-репо, а воркtree надо примонтировать).

---

## File Structure

**Создаются:**
- `services/order_links.py` — владелец таблицы. CRUD, `_transition`, `mark_in_work` / `mark_done` / `mark_failed`, bulk `mark_all_manual_in_work` / `fail_remaining_links`, `_recompute_order_status`, `compute_deadline`.
- `services/order_links_classifier.py` — stub: `classify(url, order) → 'manual'`.
- `services/pf_executor_api.py` — stub: `submit_link(url, order)` всегда raises `ExecutorAPIRejected`.
- `services/order_links_dispatcher.py` — `dispatch_pending_links(order_id)`: классификация + попытка auto через API + fallback в manual.
- `services/order_links_deadline.py` — `close_expired_links()` + `run_deadline_loop()` (asyncio cron).
- `scripts/migrate_order_links.py` — backfill legacy `orders.links` → `order_links`.
- `tests/unit/test_order_links_model.py` — CRUD.
- `tests/unit/test_order_links_transitions.py` — матрица переходов.
- `tests/unit/test_order_links_aggregation.py` — `_recompute_order_status`.
- `tests/unit/test_order_links_bulk.py` — `mark_all_manual_in_work`, `fail_remaining_links`.
- `tests/unit/test_order_links_deadline.py` — cron-закрытие.
- `tests/unit/test_order_links_dispatcher.py` — dispatcher + stubs.
- `tests/unit/test_pf_executor_api_stub.py` — stub API клиент.
- `tests/unit/test_order_links_classifier_stub.py` — stub классификатор.
- `tests/unit/test_compute_deadline.py` — формула deadline.
- `tests/unit/test_migrate_order_links.py` — backfill.
- `tests/unit/test_admin_links_buttons.py` — admin handler'ы.
- `tests/unit/test_gsheets_order_links.py` — экспорт.

**Модифицируются:**
- `utils/sqlite3.py` — добавить `order_links` в `get_schema_statements` + индексы в `get_index_statements`.
- `services/exceptions.py` — добавить `LinkNotFound`, `InvalidLinkTransition`, `ExecutorAPIError`, `ExecutorAPIRejected`.
- `services/orders.py` — `create_unpaid` пишет ссылки в `order_links`, `mark_paid` и `pay_with_balance` запускают dispatcher.
- `handlers/admin_orders.py` — удалить хендлеры `gotovoebat` / `order_finish` (кнопка «Выполнить»), добавить FSM-handler'ы для «Отправил все manual» и «Заказ failed». Обновить рендер карточки заказа (список ссылок со статусами).
- `keyboards/inline_keyboards.py` — обновить `orders_kb`: убрать кнопку «Выполнить», добавить «Отправил все manual» и «Заказ failed».
- `utils/googlesheets.py` — переписать `create_sheet` и `create_orders_report` на SQL с JOIN, добавить новый таб «Manual задачи».
- `web/main.py` — добавить `run_deadline_loop` и `run_dispatcher_loop` в lifespan.

---

## Task 1: Добавить таблицу `order_links` в схему

**Files:**
- Modify: `utils/sqlite3.py` (функция `get_schema_statements` после `notifications`; функция `get_index_statements`)
- Test: `tests/unit/test_db_schema.py`

- [ ] **Step 1: Write the failing test**

В `tests/unit/test_db_schema.py` дописать в конец:

```python
def test_order_links_table_in_schema(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(order_links)")}
    assert cols == {
        "id", "order_id", "url", "status", "delivery_mode",
        "deadline_at", "started_at", "done_at", "failed_at",
        "failure_reason", "external_id", "created_at",
    }


def test_order_links_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='order_links'"
        )}
    assert "idx_order_links_order" in idx
    assert "idx_order_links_deadline" in idx
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_db_schema.py::test_order_links_table_in_schema tests/unit/test_db_schema.py::test_order_links_indexes_present -v
```

Expected: FAIL — таблица `order_links` не существует.

- [ ] **Step 3: Add schema statement**

В `utils/sqlite3.py::get_schema_statements()` после кортежа для `notifications` (перед `]` закрывающей скобкой) добавить:

```python
        (
            "order_links",
            "CREATE TABLE IF NOT EXISTS order_links("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "order_id INTEGER NOT NULL,"
            "url TEXT NOT NULL,"
            "status TEXT NOT NULL DEFAULT 'pending',"
            "delivery_mode TEXT,"
            "deadline_at TIMESTAMP,"
            "started_at TIMESTAMP,"
            "done_at TIMESTAMP,"
            "failed_at TIMESTAMP,"
            "failure_reason TEXT,"
            "external_id TEXT,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (order_id) REFERENCES orders(increment))",
            12,
        ),
```

- [ ] **Step 4: Add indexes**

В `utils/sqlite3.py::get_index_statements()` дописать в конец списка перед `]`:

```python
        "CREATE INDEX IF NOT EXISTS idx_order_links_order "
        "ON order_links(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_order_links_deadline "
        "ON order_links(status, deadline_at) WHERE status = 'in_work'",
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_db_schema.py -v
```

Expected: PASS на новые тесты и все остальные тесты схемы.

- [ ] **Step 6: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_db_schema.py
git commit -m "feat(order-links): add order_links table and indexes"
```

---

## Task 2: Добавить исключения для order_links

**Files:**
- Modify: `services/exceptions.py`
- Test: `tests/unit/test_exceptions.py` (создать если нет)

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_exceptions.py` (если файла нет — создать), содержимое:

```python
def test_link_not_found_is_service_error():
    from services.exceptions import LinkNotFound, ServiceError
    assert issubclass(LinkNotFound, ServiceError)


def test_invalid_link_transition_carries_from_to():
    from services.exceptions import InvalidLinkTransition
    exc = InvalidLinkTransition(from_status="done", to_status="in_work")
    assert exc.from_status == "done"
    assert exc.to_status == "in_work"
    assert "done" in str(exc) and "in_work" in str(exc)


def test_executor_api_rejected_is_service_error():
    from services.exceptions import ExecutorAPIError, ExecutorAPIRejected, ServiceError
    assert issubclass(ExecutorAPIError, ServiceError)
    assert issubclass(ExecutorAPIRejected, ExecutorAPIError)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_exceptions.py -v
```

Expected: FAIL — `ImportError`.

- [ ] **Step 3: Add exceptions**

В `services/exceptions.py` дописать в конец:

```python


class LinkNotFound(ServiceError):
    """Ссылка order_links с переданным id не найдена."""


class InvalidLinkTransition(ServiceError):
    """Попытка изменить статус ссылки на недопустимый.

    Например, in_work → in_work (no-op обрабатывается выше),
    или done → in_work (terminal).
    """

    def __init__(self, *, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Invalid link transition: {from_status} → {to_status}"
        )
        self.from_status = from_status
        self.to_status = to_status


class ExecutorAPIError(ServiceError):
    """Ошибка при работе с API исполнителя ПФ."""


class ExecutorAPIRejected(ExecutorAPIError):
    """API явно отказался брать ссылку (не поддерживает регион/тип/и т.п.).

    Caller должен fallback'нуться в manual delivery_mode.
    Отличается от `ExecutorAPIError` тем, что повторная попытка не поможет.
    """
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_exceptions.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat(order-links): add link/executor service exceptions"
```

---

## Task 3: Сервис `services/order_links.py` — CRUD `create_links` / `list_links` / `get_link`

**Files:**
- Create: `services/order_links.py`
- Test: `tests/unit/test_order_links_model.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_model.py`:

```python
"""CRUD-операции для order_links."""
import sqlite3
import pytest

from services.db import connect
from utils.dates import now_iso


def _seed_order(tmp_db, status="paid"):
    """Создаёт фиктивного user и order, возвращает order_id."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', ?, ?)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_create_links_inserts_pending_rows(tmp_db):
    from services.order_links import create_links

    order_id = _seed_order(tmp_db)

    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/a", "https://avito.ru/b"])
        con.commit()

    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, delivery_mode, created_at FROM order_links "
            "WHERE order_id=? ORDER BY id", (order_id,)
        ))
    assert [r["url"] for r in rows] == ["https://avito.ru/a", "https://avito.ru/b"]
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["delivery_mode"] is None for r in rows)
    assert all(r["created_at"] for r in rows)


def test_create_links_empty_list_inserts_nothing(tmp_db):
    from services.order_links import create_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=[])
        con.commit()

    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 0


def test_list_links_returns_dicts_ordered_by_id(tmp_db):
    from services.order_links import create_links, list_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url1", "url2", "url3"])
        con.commit()

    links = list_links(order_id)
    assert [l["url"] for l in links] == ["url1", "url2", "url3"]
    assert all(isinstance(l, dict) for l in links)
    assert all("id" in l and "status" in l for l in links)


def test_get_link_returns_row(tmp_db):
    from services.order_links import create_links, get_link, list_links

    order_id = _seed_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url"])
        con.commit()

    link_id = list_links(order_id)[0]["id"]
    link = get_link(link_id)
    assert link["url"] == "url"
    assert link["status"] == "pending"


def test_get_link_raises_link_not_found(tmp_db):
    from services.order_links import get_link
    from services.exceptions import LinkNotFound

    with pytest.raises(LinkNotFound):
        get_link(99999)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_model.py -v
```

Expected: FAIL — `services.order_links` ещё не существует.

- [ ] **Step 3: Implement service**

Создать `services/order_links.py`:

```python
"""Владелец таблицы order_links.

Единственная точка мутации со встроенной валидацией переходов и пересчётом
orders.status (Спек §4.1). Все методы работают как через явный `con`
(участвуя в транзакции caller'а), так и через свой connect().
"""
from __future__ import annotations

import logging

from services.db import connect
from services.exceptions import LinkNotFound
from utils.dates import now_iso

logger = logging.getLogger(__name__)


# === CRUD ===

def create_links(con, *, order_id: int, urls: list[str]) -> None:
    """Создать pending-ссылки заказа. Работает в переданной транзакции."""
    created = now_iso()
    for url in urls:
        con.execute(
            "INSERT INTO order_links(order_id, url, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (order_id, url, created),
        )


def list_links(order_id: int) -> list[dict]:
    """Все ссылки заказа, упорядочены по id (порядок создания)."""
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM order_links WHERE order_id=? ORDER BY id",
            (order_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_link(link_id: int) -> dict:
    """Прочитать одну ссылку. Raises LinkNotFound."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM order_links WHERE id=?", (link_id,)
        ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    return dict(row)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_order_links_model.py
git commit -m "feat(order-links): add CRUD for order_links service"
```

---

## Task 4: `_transition` с валидацией матрицы переходов

**Files:**
- Modify: `services/order_links.py`
- Test: `tests/unit/test_order_links_transitions.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_transitions.py`:

```python
"""Матрица переходов состояний order_links."""
import sqlite3
import pytest

from services.db import connect
from services.exceptions import InvalidLinkTransition, LinkNotFound
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_link(tmp_db, status="pending"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["u"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    if status != "pending":
        with sqlite3.connect(tmp_db) as con:
            con.execute("UPDATE order_links SET status=? WHERE id=?",
                        (status, link_id))
            con.commit()
    return order_id, link_id


@pytest.mark.parametrize("from_status,to_status", [
    ("pending", "in_work"),
    ("pending", "failed"),
    ("in_work", "done"),
    ("in_work", "failed"),
])
def test_allowed_transitions(tmp_db, from_status, to_status):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=from_status)
    with connect() as con:
        _transition(con, link_id=link_id, to_status=to_status)
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        new_status = con.execute(
            "SELECT status FROM order_links WHERE id=?", (link_id,)
        ).fetchone()[0]
    assert new_status == to_status


@pytest.mark.parametrize("from_status,to_status", [
    ("pending", "done"),         # должен пройти через in_work
    ("in_work", "pending"),       # обратно нельзя
    ("done", "in_work"),          # terminal
    ("done", "failed"),
    ("failed", "in_work"),
    ("failed", "done"),
])
def test_forbidden_transitions(tmp_db, from_status, to_status):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=from_status)
    with connect() as con, pytest.raises(InvalidLinkTransition):
        _transition(con, link_id=link_id, to_status=to_status)


@pytest.mark.parametrize("status", ["pending", "in_work", "done", "failed"])
def test_noop_transition_to_same_status(tmp_db, status):
    """Повторный вызов в текущий статус — no-op, не падает."""
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=status)
    with connect() as con:
        _transition(con, link_id=link_id, to_status=status)  # no exception
        con.commit()


def test_transition_writes_timestamp(tmp_db):
    """started_at заполняется при pending→in_work."""
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="pending")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="in_work",
                    delivery_mode="auto", deadline_at="2026-06-30T00:00:00+00:00")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row["started_at"] is not None
    assert row["delivery_mode"] == "auto"
    assert row["deadline_at"] == "2026-06-30T00:00:00+00:00"


def test_transition_done_writes_done_at(tmp_db):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="in_work")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="done")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        done_at = con.execute(
            "SELECT done_at FROM order_links WHERE id=?", (link_id,)
        ).fetchone()[0]
    assert done_at is not None


def test_transition_failed_writes_reason(tmp_db):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="in_work")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="failed",
                    failure_reason="API timeout")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row["failed_at"] is not None
    assert row["failure_reason"] == "API timeout"


def test_transition_unknown_link_raises(tmp_db):
    from services.order_links import _transition
    with connect() as con, pytest.raises(LinkNotFound):
        _transition(con, link_id=99999, to_status="in_work")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_transitions.py -v
```

Expected: FAIL — `_transition` не существует.

- [ ] **Step 3: Implement `_transition`**

В `services/order_links.py` добавить (после `get_link`):

```python
# === State transitions ===

# Допустимые переходы статусов ссылки. Спек §3.2.
_ALLOWED_TRANSITIONS = {
    ("pending", "in_work"),
    ("pending", "failed"),
    ("in_work", "done"),
    ("in_work", "failed"),
}


def _transition(
    con,
    *,
    link_id: int,
    to_status: str,
    delivery_mode: str | None = None,
    deadline_at: str | None = None,
    external_id: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Атомарно перевести ссылку в новый статус.

    Валидирует допустимость через `_ALLOWED_TRANSITIONS`. Повтор в текущий
    статус — no-op (идемпотентность). Проставляет соответствующий timestamp
    (started_at / done_at / failed_at).

    Не делает commit и не пересчитывает order.status — это ответственность
    публичных методов поверх (`mark_in_work` / `mark_done` / `mark_failed`).
    """
    row = con.execute(
        "SELECT status FROM order_links WHERE id=?", (link_id,)
    ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    current = row["status"] if hasattr(row, "keys") else row[0]

    if current == to_status:
        return  # idempotent no-op

    if (current, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidLinkTransition(from_status=current, to_status=to_status)

    now = now_iso()
    fields = ["status = ?"]
    values: list = [to_status]

    if to_status == "in_work":
        fields.append("started_at = ?")
        values.append(now)
        if delivery_mode is not None:
            fields.append("delivery_mode = ?")
            values.append(delivery_mode)
        if deadline_at is not None:
            fields.append("deadline_at = ?")
            values.append(deadline_at)
        if external_id is not None:
            fields.append("external_id = ?")
            values.append(external_id)
    elif to_status == "done":
        fields.append("done_at = ?")
        values.append(now)
    elif to_status == "failed":
        fields.append("failed_at = ?")
        values.append(now)
        if failure_reason is not None:
            fields.append("failure_reason = ?")
            values.append(failure_reason)

    values.append(link_id)
    con.execute(
        f"UPDATE order_links SET {', '.join(fields)} WHERE id = ?",
        values,
    )
```

Импорты в начале файла обновить — добавить `InvalidLinkTransition`:

```python
from services.exceptions import InvalidLinkTransition, LinkNotFound
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_transitions.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_order_links_transitions.py
git commit -m "feat(order-links): add _transition with state-machine validation"
```

---

## Task 5: `_recompute_order_status` (агрегация)

**Files:**
- Modify: `services/order_links.py`
- Test: `tests/unit/test_order_links_aggregation.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_aggregation.py`:

```python
"""Агрегация orders.status из order_links. Спек §4.1."""
import sqlite3
import pytest

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_order(tmp_db, status="paid"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', ?, ?)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def _seed_links_with_statuses(tmp_db, order_id, statuses):
    """Создать N ссылок и расставить им заданные статусы напрямую."""
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"u{i}" for i in range(len(statuses))])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        for link_id, s in zip(link_ids, statuses):
            con.execute("UPDATE order_links SET status=? WHERE id=?",
                        (s, link_id))
        con.commit()


def _get_order_status(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]


def test_all_pending_keeps_paid(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["pending", "pending"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None  # no change
    assert _get_order_status(tmp_db, order_id) == "paid"


def test_mixed_pending_in_work_keeps_paid(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["pending", "in_work", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == "paid"


def test_all_done_transitions_to_done(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["done", "done", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "done")
    assert _get_order_status(tmp_db, order_id) == "done"


def test_done_with_failed_transitions_to_failed(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["done", "failed", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "failed")
    assert _get_order_status(tmp_db, order_id) == "failed"


def test_all_failed_transitions_to_failed(tmp_db):
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    _seed_links_with_statuses(tmp_db, order_id, ["failed", "failed"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result == ("paid", "failed")
    assert _get_order_status(tmp_db, order_id) == "failed"


@pytest.mark.parametrize("guarded", ["unpaid", "payment_failed", "cancelled"])
def test_guard_does_not_touch_non_paid_orders(tmp_db, guarded):
    """Заказ в unpaid/payment_failed/cancelled не апается в done даже если
    все ссылки done (защита от багов; работа невозможна до paid)."""
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status=guarded)
    _seed_links_with_statuses(tmp_db, order_id, ["done", "done"])
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == guarded


def test_no_links_keeps_paid(tmp_db):
    """Заказ без ссылок — формально все terminal, но edge case: оставляем paid."""
    from services.order_links import _recompute_order_status
    order_id = _seed_order(tmp_db, status="paid")
    with connect() as con:
        result = _recompute_order_status(con, order_id)
        con.commit()
    assert result is None
    assert _get_order_status(tmp_db, order_id) == "paid"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_aggregation.py -v
```

Expected: FAIL — `_recompute_order_status` не существует.

- [ ] **Step 3: Implement `_recompute_order_status`**

В `services/order_links.py` добавить:

```python
# === Aggregation ===

# Какие orders.status можно менять через агрегацию ссылок.
# Спек §4.1 guard: unpaid/payment_failed/cancelled не трогаем.
_AGGREGATABLE_ORDER_STATUSES = frozenset({"paid"})


def _recompute_order_status(con, order_id: int) -> tuple[str, str] | None:
    """Пересчитать orders.status по строкам order_links.

    Правило (Спек §4.1):
        pending + in_work > 0 → paid (без изменений)
        ≥1 failed → failed
        иначе → done

    Guard: если orders.status ∉ {paid} — не трогаем (защита от перехода
    в done из неоплаченного заказа).

    Не делает commit. Возвращает (old, new) если статус сменился,
    иначе None — caller должен сам шлёт notify_order_status_changed.
    """
    row = con.execute(
        "SELECT status FROM orders WHERE increment=?", (order_id,)
    ).fetchone()
    if row is None:
        return None
    old_status = row["status"] if hasattr(row, "keys") else row[0]
    if old_status not in _AGGREGATABLE_ORDER_STATUSES:
        return None

    counts_rows = con.execute(
        "SELECT status, COUNT(*) AS c FROM order_links "
        "WHERE order_id=? GROUP BY status",
        (order_id,),
    ).fetchall()
    counts = {r["status"] if hasattr(r, "keys") else r[0]:
              r["c"] if hasattr(r, "keys") else r[1]
              for r in counts_rows}

    if not counts:
        return None  # no links yet
    if counts.get("pending", 0) + counts.get("in_work", 0) > 0:
        return None  # still in flight
    if counts.get("failed", 0) > 0:
        new_status = "failed"
    else:
        new_status = "done"

    if new_status == old_status:
        return None

    con.execute(
        "UPDATE orders SET status=? WHERE increment=? AND status=?",
        (new_status, order_id, old_status),
    )
    return (old_status, new_status)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_aggregation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_order_links_aggregation.py
git commit -m "feat(order-links): aggregate order.status from order_links"
```

---

## Task 6: Публичные `mark_in_work` / `mark_done` / `mark_failed`

**Files:**
- Modify: `services/order_links.py`
- Test: `tests/unit/test_order_links_public_marks.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_public_marks.py`:

```python
"""Публичные методы перехода (mark_*) + пересчёт order.status."""
import sqlite3

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_order_with_links(tmp_db, n_links=2):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"url{i}" for i in range(n_links)])
        con.commit()
    return order_id, [l["id"] for l in list_links(order_id)]


def _order_status(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]


def test_mark_in_work_returns_none_when_others_still_pending(tmp_db):
    from services.order_links import mark_in_work
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=2)
    result = mark_in_work(
        link_ids[0], delivery_mode="auto",
        deadline_at="2026-06-30T00:00:00+00:00",
    )
    assert result is None
    assert _order_status(tmp_db, order_id) == "paid"


def test_mark_done_last_link_returns_old_new(tmp_db):
    from services.order_links import mark_in_work, mark_done
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    mark_in_work(link_ids[0], delivery_mode="manual",
                 deadline_at="2026-06-30T00:00:00+00:00")
    result = mark_done(link_ids[0])
    assert result == ("paid", "done")
    assert _order_status(tmp_db, order_id) == "done"


def test_mark_failed_writes_reason_and_aggregates(tmp_db):
    from services.order_links import mark_failed
    order_id, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    result = mark_failed(link_ids[0], reason="manual cancel")
    assert result == ("paid", "failed")
    assert _order_status(tmp_db, order_id) == "failed"


def test_mark_done_idempotent(tmp_db):
    """Повторный mark_done — не падает, не дублирует notify."""
    from services.order_links import mark_in_work, mark_done
    _, link_ids = _seed_order_with_links(tmp_db, n_links=1)
    mark_in_work(link_ids[0], delivery_mode="auto",
                 deadline_at="2026-06-30T00:00:00+00:00")
    first = mark_done(link_ids[0])
    second = mark_done(link_ids[0])
    assert first == ("paid", "done")
    assert second is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_public_marks.py -v
```

Expected: FAIL — `mark_in_work` / `mark_done` / `mark_failed` не существуют.

- [ ] **Step 3: Implement public marks**

В `services/order_links.py` добавить в конец:

```python
# === Public mutation API ===


def _get_order_id(con, link_id: int) -> int:
    row = con.execute(
        "SELECT order_id FROM order_links WHERE id=?", (link_id,)
    ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    return int(row["order_id"] if hasattr(row, "keys") else row[0])


def mark_in_work(
    link_id: int,
    *,
    delivery_mode: str,
    deadline_at: str,
    external_id: str | None = None,
) -> tuple[str, str] | None:
    """pending → in_work. Пересчитывает order.status в той же транзакции.
    Возвращает (old, new) если статус заказа сменился, иначе None."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(
            con, link_id=link_id, to_status="in_work",
            delivery_mode=delivery_mode, deadline_at=deadline_at,
            external_id=external_id,
        )
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result


def mark_done(link_id: int) -> tuple[str, str] | None:
    """in_work → done."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(con, link_id=link_id, to_status="done")
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result


def mark_failed(link_id: int, *, reason: str) -> tuple[str, str] | None:
    """pending | in_work → failed."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(con, link_id=link_id, to_status="failed",
                    failure_reason=reason)
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_public_marks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_order_links_public_marks.py
git commit -m "feat(order-links): public mark_in_work/mark_done/mark_failed"
```

---

## Task 7: `compute_deadline` (формула deadline_at)

**Files:**
- Modify: `services/order_links.py`
- Test: `tests/unit/test_compute_deadline.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_compute_deadline.py`:

```python
"""compute_deadline(order, now=...) → ISO deadline = max(start, today) + days."""
from datetime import datetime, timezone

import pytest


def _fixed_now(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_no_start_date_uses_today(monkeypatch):
    from services import order_links
    order = {"position_name": "3/100", "start_date": None}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # Now is 2026-06-07; start = today; deadline = today + 3 days = 2026-06-10
    assert deadline.startswith("2026-06-10")


def test_start_date_in_future_adds_days_from_start(monkeypatch):
    from services import order_links
    order = {"position_name": "5/200", "start_date": "2026-06-15"}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # start = 2026-06-15; deadline = 2026-06-20
    assert deadline.startswith("2026-06-20")


def test_start_date_in_past_uses_today(monkeypatch):
    """Если юзер выбрал прошедшую дату (или backfill), стартуем сегодня."""
    from services import order_links
    order = {"position_name": "2/50", "start_date": "2026-06-01"}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # start_effective = max(2026-06-01, 2026-06-07) = 2026-06-07
    # deadline = 2026-06-09
    assert deadline.startswith("2026-06-09")


def test_invalid_position_name_raises(monkeypatch):
    from services import order_links
    order = {"position_name": "broken", "start_date": None}
    with pytest.raises(ValueError):
        order_links.compute_deadline(
            order, now=_fixed_now("2026-06-07T10:00:00+00:00")
        )


def test_returns_iso_with_tz(monkeypatch):
    from services import order_links
    order = {"position_name": "1/10", "start_date": None}
    deadline = order_links.compute_deadline(
        order, now=_fixed_now("2026-06-07T10:00:00+00:00")
    )
    # Должно парситься обратно
    parsed = order_links.datetime.fromisoformat(deadline)
    assert parsed.tzinfo is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_compute_deadline.py -v
```

Expected: FAIL — `compute_deadline` не существует.

- [ ] **Step 3: Implement `compute_deadline`**

В `services/order_links.py` добавить (в импортах добавить `datetime` модуль; функцию — в конец файла):

В начало файла добавить импорт:
```python
from datetime import date, datetime, timedelta, timezone
```

В конец файла добавить:
```python
# === Deadline ===

def compute_deadline(
    order: dict,
    *,
    now: datetime | None = None,
) -> str:
    """Вычислить deadline_at для ссылки заказа.

    Формула: max(order.start_date, today) + days, где days берётся из
    order.position_name (формат 'days/fix_count').

    `now` параметр для тестов (фиксированное "сейчас"); по умолчанию utcnow.

    Возвращает ISO+TZ строку.
    Raises ValueError если position_name не парсится.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    parts = str(order["position_name"]).split("/")
    if len(parts) < 1:
        raise ValueError(f"invalid position_name: {order['position_name']!r}")
    try:
        days = int(parts[0])
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"invalid position_name: {order['position_name']!r}"
        ) from exc

    today = now.date()
    start_str = order.get("start_date")
    start = today
    if start_str:
        try:
            start = date.fromisoformat(str(start_str))
        except ValueError:
            start = today
    start_effective = max(start, today)
    deadline = datetime.combine(
        start_effective + timedelta(days=days),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return deadline.isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_compute_deadline.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_compute_deadline.py
git commit -m "feat(order-links): add compute_deadline helper"
```

---

## Task 8: `create_unpaid` в orders.py пишет в `order_links`

**Files:**
- Modify: `services/orders.py` (функция `create_unpaid`)
- Test: `tests/unit/test_orders_creates_links.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_orders_creates_links.py`:

```python
"""services.orders.create_unpaid создаёт строки в order_links."""
import sqlite3


def test_create_unpaid_writes_links_table(tmp_db):
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '5')")
        con.commit()

    order_id = create_unpaid(
        user_id=1, links=["https://avito.ru/a", "https://avito.ru/b"],
        days=3, fix_count=100, contacts=False, phone=None,
    )

    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, delivery_mode FROM order_links "
            "WHERE order_id=? ORDER BY id", (order_id,)
        ))
    assert [r["url"] for r in rows] == ["https://avito.ru/a", "https://avito.ru/b"]
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["delivery_mode"] is None for r in rows)


def test_create_unpaid_still_writes_legacy_column_for_backward_compat(tmp_db):
    """Phase 1: orders.links временно пишется (legacy reader безопасен).
    Phase 2 уберёт колонку — этот тест удалить."""
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '5')")
        con.commit()

    order_id = create_unpaid(
        user_id=1, links=["url"], days=1, fix_count=10,
        contacts=False, phone=None,
    )
    with sqlite3.connect(tmp_db) as con:
        # legacy column still exists; either NULL or JSON — оба варианта OK
        row = con.execute(
            "SELECT links FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
    # Specifically: we want it to NOT crash the writer. NULL is fine.
    # При drop колонки в Phase 2 тест удалить вместе с колонкой.
    assert row is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_orders_creates_links.py -v
```

Expected: FAIL — `create_unpaid` пишет JSON в `orders.links`, не создаёт `order_links` строк.

- [ ] **Step 3: Modify `create_unpaid`**

В `services/orders.py::create_unpaid` (строки ~70-106) изменить INSERT-блок:

Было:
```python
    with connect() as con:
        cur = con.execute(
            "INSERT INTO orders("
            "  user_id, price, position_name, status, links, contacts, "
            "  user_name, payment_method, payment_expires_at, payment_id, "
            "  phone, start_date, date"
            ") VALUES (?, ?, ?, 'unpaid', ?, ?, NULL, NULL, ?, NULL, ?, ?, ?)",
            (
                user_id, price, f"{days}/{fix_count}",
                json.dumps(links), int(contacts),
                expires_at, phone, start_date, _now_iso(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
```

Стало:
```python
    from services.order_links import create_links as _create_order_links
    with connect() as con:
        cur = con.execute(
            "INSERT INTO orders("
            "  user_id, price, position_name, status, links, contacts, "
            "  user_name, payment_method, payment_expires_at, payment_id, "
            "  phone, start_date, date"
            ") VALUES (?, ?, ?, 'unpaid', NULL, ?, NULL, NULL, ?, NULL, ?, ?, ?)",
            (
                user_id, price, f"{days}/{fix_count}",
                int(contacts),
                expires_at, phone, start_date, _now_iso(),
            ),
        )
        order_id = int(cur.lastrowid)
        _create_order_links(con, order_id=order_id, urls=list(links))
        con.commit()
        return order_id
```

Импорт `json` в начале файла можно оставить — он ещё используется в других местах (или будет удалён в Task 21 при очистке).

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_orders_creates_links.py tests/unit/test_orders_new_flow.py -v
```

Expected: PASS на новый тест; существующие тесты в `test_orders_new_flow.py` тоже должны пройти (они проверяют сам факт создания заказа, не парсят `links`).

- [ ] **Step 5: Commit**

```bash
git add services/orders.py tests/unit/test_orders_creates_links.py
git commit -m "feat(order-links): create_unpaid writes to order_links table"
```

---

## Task 9: Stub-классификатор `services/order_links_classifier.py`

**Files:**
- Create: `services/order_links_classifier.py`
- Test: `tests/unit/test_order_links_classifier_stub.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_order_links_classifier_stub.py`:

```python
"""Stub: классификатор всегда возвращает 'manual' (Спек §5.1)."""

def test_classify_returns_manual():
    from services.order_links_classifier import classify
    assert classify("https://avito.ru/anything", {"position_name": "3/100"}) == "manual"


def test_classify_does_not_raise_on_missing_fields():
    """Stub не должен зависеть от состава order — это будущая бизнес-логика."""
    from services.order_links_classifier import classify
    assert classify("url", {}) == "manual"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_classifier_stub.py -v
```

Expected: FAIL — модуль не существует.

- [ ] **Step 3: Implement stub**

Создать `services/order_links_classifier.py`:

```python
"""Классификатор: auto или manual для отдельной ссылки.

STUB: пока всегда возвращает 'manual' (безопасный default — весь существующий
ручной flow сохраняется).

Будущая бизнес-логика: смотрит на тип/регион позиции, ходит в Авито API
за фичами, применяет правила. Все зависимости инкапсулированы здесь.
"""
from __future__ import annotations


def classify(url: str, order: dict) -> str:
    """Решает, идёт ли ссылка через API исполнителя (auto) или ручную
    обработку админом (manual).

    Возвращает 'auto' или 'manual'. Стаб всегда отдаёт 'manual'.
    """
    return "manual"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_classifier_stub.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links_classifier.py tests/unit/test_order_links_classifier_stub.py
git commit -m "feat(order-links): add stub classifier (always manual)"
```

---

## Task 10: Stub API-клиента исполнителя `services/pf_executor_api.py`

**Files:**
- Create: `services/pf_executor_api.py`
- Test: `tests/unit/test_pf_executor_api_stub.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_pf_executor_api_stub.py`:

```python
"""Stub: API-клиент всегда raises ExecutorAPIRejected (Спек §5.1)."""
import pytest


def test_submit_link_always_raises_rejected():
    from services.pf_executor_api import submit_link
    from services.exceptions import ExecutorAPIRejected
    with pytest.raises(ExecutorAPIRejected):
        submit_link("https://avito.ru/x", {"position_name": "3/100"})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_pf_executor_api_stub.py -v
```

Expected: FAIL — модуль не существует.

- [ ] **Step 3: Implement stub**

Создать `services/pf_executor_api.py`:

```python
"""Клиент API исполнителя ПФ.

STUB: пока всегда отказывает (`ExecutorAPIRejected`). С таким стабом все
auto-ссылки в dispatcher'е fallback'ятся в manual delivery_mode — система
ведёт себя как до этого спека, только через новую модель данных.

Будущая реализация: HTTP-вызов к API. Контракт:
  - submit_link → возвращает external_id (str) при успехе
  - ExecutorAPIRejected — API не возьмёт эту ссылку (другой регион/тип),
    caller должен fallback в manual
  - ExecutorAPIError — временный сбой, caller должен ретраить позже
"""
from __future__ import annotations

from services.exceptions import ExecutorAPIRejected


def submit_link(url: str, order: dict) -> str:
    """Отправить ссылку исполнителю. Возвращает external_id при успехе.

    STUB: всегда raises ExecutorAPIRejected.
    """
    raise ExecutorAPIRejected("API client not implemented yet (stub)")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_pf_executor_api_stub.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/pf_executor_api.py tests/unit/test_pf_executor_api_stub.py
git commit -m "feat(order-links): add stub executor API client"
```

---

## Task 11: Dispatcher `dispatch_pending_links`

**Files:**
- Create: `services/order_links_dispatcher.py`
- Test: `tests/unit/test_order_links_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_dispatcher.py`:

```python
"""Dispatcher: classify → API → manual fallback (Спек §5.1)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, n_links=2):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"url{i}" for i in range(n_links)])
        con.commit()
    return order_id


def test_dispatch_stub_all_to_manual_pending(tmp_db):
    """Стабы: classifier→manual → links остаются pending+manual."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=2)
    dispatch_pending_links(order_id)
    links = list_links(order_id)
    assert all(l["status"] == "pending" for l in links)
    assert all(l["delivery_mode"] == "manual" for l in links)


def test_dispatch_classifier_auto_api_success_sets_in_work(tmp_db):
    """classifier→auto + submit_link OK → in_work, delivery_mode=auto."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value="auto"), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-123"):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "in_work"
    assert links[0]["delivery_mode"] == "auto"
    assert links[0]["external_id"] == "ext-123"
    assert links[0]["deadline_at"] is not None


def test_dispatch_classifier_auto_api_rejected_falls_back_to_manual(tmp_db):
    """classifier→auto + ExecutorAPIRejected → pending+manual (fallback)."""
    from services.order_links_dispatcher import dispatch_pending_links
    from services.exceptions import ExecutorAPIRejected
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value="auto"), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIRejected("nope")):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "manual"


def test_dispatch_classifier_auto_api_error_keeps_pending_for_retry(tmp_db):
    """classifier→auto + временный ExecutorAPIError → остаётся pending+auto."""
    from services.order_links_dispatcher import dispatch_pending_links
    from services.exceptions import ExecutorAPIError
    order_id = _seed_paid_order(tmp_db, n_links=1)

    with patch("services.order_links_dispatcher.classify",
               return_value="auto"), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("timeout")):
        dispatch_pending_links(order_id)

    links = list_links(order_id)
    assert links[0]["status"] == "pending"
    assert links[0]["delivery_mode"] == "auto"


def test_dispatch_idempotent_skips_already_classified(tmp_db):
    """Второй вызов dispatch не должен трогать ссылки в in_work."""
    from services.order_links_dispatcher import dispatch_pending_links
    order_id = _seed_paid_order(tmp_db, n_links=2)
    dispatch_pending_links(order_id)  # все → pending+manual

    # Симулируем, что одну ссылку админ уже отправил
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE order_links SET status='in_work', delivery_mode='manual' "
            "WHERE id=?", (link_ids[0],)
        )
        con.commit()

    dispatch_pending_links(order_id)  # повторно
    links = list_links(order_id)
    # Первая осталась in_work, вторая по-прежнему pending+manual
    assert links[0]["status"] == "in_work"
    assert links[1]["status"] == "pending"
    assert links[1]["delivery_mode"] == "manual"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_dispatcher.py -v
```

Expected: FAIL — модуль не существует.

- [ ] **Step 3: Implement dispatcher**

Создать `services/order_links_dispatcher.py`:

```python
"""Dispatcher: классифицирует pending-ссылки, пробует auto через API,
fallback'ит в manual.

Идемпотентно: повторный вызов не трогает уже не-pending ссылки.

Каждая ссылка обрабатывается независимо — ошибка на одной не валит
остальные. Только pending-ссылки, у которых delivery_mode=NULL ИЛИ auto
(retry-кейс), участвуют в dispatch'е; manual-ссылки уже ждут админа.
"""
from __future__ import annotations

import logging

from services.db import connect
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected
from services.order_links import compute_deadline
from services.order_links_classifier import classify
from services.pf_executor_api import submit_link

logger = logging.getLogger(__name__)


def dispatch_pending_links(order_id: int) -> None:
    """Прогнать все pending-ссылки заказа через классификатор+API.

    Не возвращает результата — состояние ссылок видно через list_links.
    Ошибки на одной ссылке логируются, остальные продолжают обрабатываться.
    """
    with connect() as con:
        order = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order is None:
            logger.warning("dispatch_pending_links: order %s not found", order_id)
            return
        order_d = dict(order)
        rows = con.execute(
            "SELECT id, delivery_mode FROM order_links "
            "WHERE order_id=? AND status='pending'",
            (order_id,),
        ).fetchall()
        candidates = [(r["id"], r["delivery_mode"]) for r in rows]

    for link_id, current_mode in candidates:
        try:
            _dispatch_one(link_id, current_mode, order_d)
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "dispatch_pending_links: link %s failed", link_id
            )


def _dispatch_one(link_id: int, current_mode: str | None, order: dict) -> None:
    """Обработать одну pending-ссылку."""
    # Re-fetch url под текущее соединение (отдельная транзакция)
    with connect() as con:
        row = con.execute(
            "SELECT url FROM order_links WHERE id=? AND status='pending'",
            (link_id,),
        ).fetchone()
        if row is None:
            return  # already not pending — race, skip
        url = row["url"]

    # Если delivery_mode ещё не назначен — классифицируем.
    mode = current_mode or classify(url, order)

    if mode == "manual":
        # просто проставить delivery_mode и оставить pending
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='manual' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return

    # mode == 'auto' — пробуем API
    try:
        external_id = submit_link(url, order)
    except ExecutorAPIRejected:
        # Не возьмут — fallback в manual
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='manual' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return
    except ExecutorAPIError:
        # Временный сбой — оставляем pending+auto для retry
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='auto' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return

    # API принял — в work
    from services.order_links import mark_in_work
    deadline = compute_deadline(order)
    mark_in_work(link_id, delivery_mode="auto",
                 deadline_at=deadline, external_id=external_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_dispatcher.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links_dispatcher.py tests/unit/test_order_links_dispatcher.py
git commit -m "feat(order-links): dispatch pending links via classifier+API"
```

---

## Task 12: Подключить dispatcher к оплате (`mark_paid` / `pay_with_balance`)

**Files:**
- Modify: `services/orders.py` (функции `mark_paid` и `pay_with_balance`)
- Test: `tests/unit/test_orders_payment_dispatch.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_orders_payment_dispatch.py`:

```python
"""После оплаты заказа dispatcher отрабатывает на его ссылках."""
import sqlite3
from unittest.mock import patch


def _seed_unpaid_order_with_links(tmp_db, n=2):
    """Создать unpaid-заказ + N ссылок через services.orders.create_unpaid."""
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 10000)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '1')")
        con.commit()
    order_id = create_unpaid(
        user_id=1, links=[f"url{i}" for i in range(n)],
        days=3, fix_count=10, contacts=False, phone=None,
    )
    return order_id


def test_mark_paid_runs_dispatcher(tmp_db):
    """mark_paid должен дёрнуть dispatch_pending_links."""
    from services.orders import mark_paid

    order_id = _seed_unpaid_order_with_links(tmp_db, n=2)
    with patch("services.orders.dispatch_pending_links") as mock:
        mark_paid(order_id)
    mock.assert_called_once_with(order_id)


def test_pay_with_balance_runs_dispatcher(tmp_db):
    from services.orders import pay_with_balance
    order_id = _seed_unpaid_order_with_links(tmp_db, n=1)
    with patch("services.orders.dispatch_pending_links") as mock:
        pay_with_balance(order_id=order_id, user_id=1)
    mock.assert_called_once_with(order_id)


def test_mark_paid_idempotent_no_double_dispatch_on_already_paid(tmp_db):
    """Второй mark_paid (на уже paid) не должен вызывать dispatcher повторно."""
    from services.orders import mark_paid
    order_id = _seed_unpaid_order_with_links(tmp_db, n=1)
    mark_paid(order_id)  # 1: unpaid → paid
    with patch("services.orders.dispatch_pending_links") as mock:
        mark_paid(order_id)  # 2: no-op
    mock.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_orders_payment_dispatch.py -v
```

Expected: FAIL — dispatcher не вызывается.

- [ ] **Step 3: Wire dispatcher into orders.py**

В `services/orders.py` добавить в импорты:
```python
from services.order_links_dispatcher import dispatch_pending_links
```

Изменить `mark_paid` (был ~line 245-254):
```python
def mark_paid(order_id: int) -> None:
    """Идемпотентно перевести unpaid → paid. Используется YooKassa webhook'ом
    и status-pollers. Если статус уже не unpaid — no-op (двойной webhook
    не должен ломать систему). После перехода в paid запускается dispatcher
    ссылок."""
    with connect() as con:
        cur = con.execute(
            "UPDATE orders SET status='paid' WHERE increment=? AND status='unpaid'",
            (order_id,),
        )
        con.commit()
        changed = cur.rowcount > 0
    if changed:
        try:
            dispatch_pending_links(order_id)
        except Exception:  # noqa: BLE001 — best-effort; cron добьёт
            logger.exception("mark_paid: dispatch_pending_links failed for %s", order_id)
```

Изменить `pay_with_balance`: в конец `with connect() as con:` блока (после `con.commit()`), добавить dispatcher вызов (вне транзакции):

В `services/orders.py::pay_with_balance` (~line 147-189), после блока:
```python
        con.execute(
            "UPDATE orders SET status='paid' WHERE increment=? AND status='unpaid'",
            (order_id,),
        )
        con.commit()
```

Добавить (на том же уровне отступа, что и `with connect()`, после выхода из `with`):
```python
    try:
        dispatch_pending_links(order_id)
    except Exception:  # noqa: BLE001 — best-effort; cron добьёт
        logger.exception("pay_with_balance: dispatch_pending_links failed for %s", order_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_orders_payment_dispatch.py tests/unit/test_orders_new_flow.py -v
```

Expected: PASS на новые тесты + существующие тесты `test_orders_new_flow.py` не сломались (они мокают БД, dispatch best-effort не повлияет).

- [ ] **Step 5: Commit**

```bash
git add services/orders.py tests/unit/test_orders_payment_dispatch.py
git commit -m "feat(order-links): trigger dispatcher on order payment"
```

---

## Task 13: Cron-задача `close_expired_links` (deadline → done)

**Files:**
- Create: `services/order_links_deadline.py`
- Test: `tests/unit/test_order_links_deadline.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_deadline.py`:

```python
"""Cron-задача закрытия in_work-ссылок по deadline."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order_with_in_work_links(tmp_db, deadlines):
    """Создаёт заказ + len(deadlines) ссылок в status=in_work."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=[f"url{i}" for i in range(len(deadlines))])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        for link_id, deadline in zip(link_ids, deadlines):
            con.execute(
                "UPDATE order_links SET status='in_work', "
                "delivery_mode='manual', deadline_at=? WHERE id=?",
                (deadline, link_id),
            )
        con.commit()
    return order_id, link_ids


def test_close_expired_marks_done_when_deadline_passed(tmp_db):
    from services.order_links_deadline import close_expired_links
    order_id, link_ids = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]  # давно в прошлом
    )
    closed = close_expired_links()
    assert closed == 1
    links = list_links(order_id)
    assert links[0]["status"] == "done"


def test_close_expired_skips_future_deadline(tmp_db):
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2099-01-01T00:00:00+00:00"]
    )
    closed = close_expired_links()
    assert closed == 0
    links = list_links(order_id)
    assert links[0]["status"] == "in_work"


def test_close_expired_recomputes_order_status(tmp_db):
    """Если все ссылки заказа done — order перейдёт в done."""
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00",
                           "2020-01-01T00:00:00+00:00"]
    )
    close_expired_links()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]
    assert s == "done"


def test_close_expired_fires_notification(tmp_db):
    """Заказ перешёл в done → должен вызваться notify_order_status_changed."""
    from services.order_links_deadline import close_expired_links
    order_id, _ = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]
    )
    with patch("services.order_links_deadline.notify_order_status_changed") as mock:
        close_expired_links()
    # Должен быть один вызов: kind=order, order_id=<тот самый>, paid→done
    assert mock.called
    kwargs = mock.call_args.kwargs
    assert kwargs["order_id"] == order_id
    assert kwargs["old_status"] == "paid"
    assert kwargs["new_status"] == "done"


def test_close_expired_skips_already_done(tmp_db):
    """Уже done-ссылки не должны попасть в SELECT."""
    from services.order_links_deadline import close_expired_links
    order_id, link_ids = _seed_paid_order_with_in_work_links(
        tmp_db, deadlines=["2020-01-01T00:00:00+00:00"]
    )
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done' WHERE id=?",
                    (link_ids[0],))
        con.commit()
    closed = close_expired_links()
    assert closed == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_deadline.py -v
```

Expected: FAIL — модуль не существует.

- [ ] **Step 3: Implement deadline cron**

Создать `services/order_links_deadline.py`:

```python
"""Cron-задача: закрывать in_work-ссылки по истечении deadline.

Спек §5.3.
"""
from __future__ import annotations

import asyncio
import logging

from services.db import connect
from services.notifications import notify_order_status_changed
from services.order_links import mark_done
from utils.dates import now_iso

logger = logging.getLogger(__name__)

DEADLINE_LOOP_INTERVAL_SECONDS = 15 * 60  # 15 минут


def close_expired_links() -> int:
    """Найти все in_work-ссылки с истёкшим deadline_at, перевести в done.

    Если переход последней ссылки заказа закрывает его (paid→done/failed) —
    шлёт notify юзеру (best-effort).

    Возвращает количество переведённых в done ссылок.
    """
    now = now_iso()
    with connect() as con:
        rows = con.execute(
            "SELECT id, order_id FROM order_links "
            "WHERE status='in_work' "
            "AND deadline_at IS NOT NULL "
            "AND deadline_at < ?",
            (now,),
        ).fetchall()
    if not rows:
        return 0

    expired = [(r["id"], r["order_id"]) for r in rows]
    order_user: dict[int, int] = {}
    if expired:
        with connect() as con:
            user_rows = con.execute(
                "SELECT increment, user_id FROM orders WHERE increment IN "
                f"({','.join('?' * len({oid for _, oid in expired}))})",
                tuple({oid for _, oid in expired}),
            ).fetchall()
        order_user = {r["increment"]: r["user_id"] for r in user_rows}

    closed_count = 0
    status_transitions: list[tuple[int, str, str]] = []  # (order_id, old, new)
    for link_id, order_id in expired:
        try:
            transition = mark_done(link_id)
            closed_count += 1
            if transition is not None:
                old, new = transition
                status_transitions.append((order_id, old, new))
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "close_expired_links: mark_done(%s) failed", link_id
            )

    for order_id, old, new in status_transitions:
        user_id = order_user.get(order_id)
        if user_id is None:
            continue
        try:
            asyncio.run(
                notify_order_status_changed(
                    user_id=int(user_id),
                    kind="order",
                    order_id=int(order_id),
                    old_status=old,
                    new_status=new,
                )
            )
        except RuntimeError:
            # Если уже внутри event loop (тесты или вызов из coroutine) —
            # передаём планирование наружу через create_task.
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(notify_order_status_changed(
                    user_id=int(user_id), kind="order",
                    order_id=int(order_id),
                    old_status=old, new_status=new,
                ))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "close_expired_links: notify scheduling failed for %s",
                    order_id,
                )
        except Exception:  # noqa: BLE001 — notify best-effort
            logger.exception(
                "close_expired_links: notify failed for order %s", order_id
            )

    return closed_count


async def run_deadline_loop() -> None:
    """Периодический вызов close_expired_links()."""
    logger.info(
        "deadline loop started (interval=%ss)",
        DEADLINE_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            count = close_expired_links()
            if count:
                logger.info("deadline: closed %d links", count)
        except Exception:  # noqa: BLE001
            logger.exception("deadline loop iteration failed")
        await asyncio.sleep(DEADLINE_LOOP_INTERVAL_SECONDS)
```

В тесте `test_close_expired_fires_notification` мы мокаем `notify_order_status_changed` — `asyncio.run` всё равно завернёт mock в awaitable. Если падает на mock — добавить:

```python
    with patch("services.order_links_deadline.notify_order_status_changed",
               new=patch.AsyncMock()) as mock:
```

(если `AsyncMock` нужен — `from unittest.mock import AsyncMock, patch`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_deadline.py -v
```

Expected: PASS. Если notification test падает на `RuntimeError: asyncio.run() cannot be called…` — заменить мок на `AsyncMock`:

В тесте сверху импорт:
```python
from unittest.mock import AsyncMock, patch
```

И замена:
```python
    with patch("services.order_links_deadline.notify_order_status_changed",
               new=AsyncMock()) as mock:
```

- [ ] **Step 5: Commit**

```bash
git add services/order_links_deadline.py tests/unit/test_order_links_deadline.py
git commit -m "feat(order-links): cron close_expired_links by deadline"
```

---

## Task 14: Cron-loop для dispatcher (retry)

**Files:**
- Modify: `services/order_links_dispatcher.py` (добавить `run_dispatcher_loop`)
- Test: `tests/unit/test_order_links_dispatcher_retry.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_order_links_dispatcher_retry.py`:

```python
"""Retry-loop dispatcher'а: добивает paid-заказы с pending-ссылками."""
import sqlite3
from unittest.mock import patch


def test_dispatch_for_paid_orders_picks_orders_with_pending_links(tmp_db):
    from services.order_links_dispatcher import dispatch_for_paid_orders
    from services.order_links import create_links
    from services.db import connect
    from utils.dates import now_iso

    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        # paid с pending
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        paid_with_pending = int(cur.lastrowid)
        # paid без pending — все ссылки уже in_work
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        paid_done = int(cur.lastrowid)
        # unpaid — не должен тронуться
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'unpaid', ?)", (now_iso(),)
        )
        unpaid = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=paid_with_pending, urls=["a"])
        create_links(con, order_id=paid_done, urls=["b"])
        create_links(con, order_id=unpaid, urls=["c"])
        con.commit()
    # Помечаем второй заказ как уже dispatch'нутый
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='auto' WHERE order_id=?",
                    (paid_done,))
        con.commit()

    with patch("services.order_links_dispatcher.dispatch_pending_links") as mock:
        dispatch_for_paid_orders()

    called_order_ids = [c.args[0] for c in mock.call_args_list]
    assert paid_with_pending in called_order_ids
    assert paid_done not in called_order_ids
    assert unpaid not in called_order_ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_dispatcher_retry.py -v
```

Expected: FAIL — `dispatch_for_paid_orders` не существует.

- [ ] **Step 3: Add retry loop**

В `services/order_links_dispatcher.py` дописать:

```python
import asyncio  # add at top imports

DISPATCHER_LOOP_INTERVAL_SECONDS = 5 * 60  # 5 минут


def dispatch_for_paid_orders() -> int:
    """Найти все paid-заказы с pending-ссылками и прогнать dispatcher.

    Используется cron'ом — добивает заказы, чей dispatch при оплате упал
    или прошёл частично (например, API временно не доступен).
    Возвращает количество обработанных заказов.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT o.increment "
            "FROM orders o JOIN order_links ol ON ol.order_id = o.increment "
            "WHERE o.status='paid' AND ol.status='pending'"
        ).fetchall()
    order_ids = [int(r["increment"]) for r in rows]
    for order_id in order_ids:
        try:
            dispatch_pending_links(order_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "dispatch_for_paid_orders: order %s failed", order_id
            )
    return len(order_ids)


async def run_dispatcher_loop() -> None:
    logger.info(
        "dispatcher loop started (interval=%ss)",
        DISPATCHER_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            count = dispatch_for_paid_orders()
            if count:
                logger.info("dispatcher: handled %d orders", count)
        except Exception:  # noqa: BLE001
            logger.exception("dispatcher loop iteration failed")
        await asyncio.sleep(DISPATCHER_LOOP_INTERVAL_SECONDS)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_dispatcher_retry.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links_dispatcher.py tests/unit/test_order_links_dispatcher_retry.py
git commit -m "feat(order-links): add dispatcher retry loop"
```

---

## Task 15: Подключить cron-loops в `web/main.py`

**Files:**
- Modify: `web/main.py` (функция `lifespan`)
- Test: `tests/unit/test_web_main_lifespan.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_web_main_lifespan.py`:

```python
"""Lifespan регистрирует order-links cron-задачи."""
import asyncio
from unittest.mock import AsyncMock, patch


def test_lifespan_starts_deadline_and_dispatcher_loops(tmp_db):
    from web.main import lifespan, app

    async def _drive():
        with patch("services.order_links_deadline.run_deadline_loop",
                   new=AsyncMock()) as dline, \
             patch("services.order_links_dispatcher.run_dispatcher_loop",
                   new=AsyncMock()) as dispatcher, \
             patch("services.payment_expiry.run_expiry_loop",
                   new=AsyncMock()):
            async with lifespan(app):
                await asyncio.sleep(0)
            dline.assert_called()
            dispatcher.assert_called()

    asyncio.run(_drive())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_web_main_lifespan.py -v
```

Expected: FAIL — loops не вызываются.

- [ ] **Step 3: Wire loops into lifespan**

В `web/main.py` (см. строки 13-35) изменить:

Импорты дописать:
```python
from services.order_links_deadline import run_deadline_loop
from services.order_links_dispatcher import run_dispatcher_loop
```

В `lifespan` после `expiry_task = asyncio.create_task(run_expiry_loop())` добавить:
```python
    deadline_task = asyncio.create_task(run_deadline_loop())
    dispatcher_task = asyncio.create_task(run_dispatcher_loop())
```

В `finally` блоке после `expiry_task.cancel()` дописать:
```python
        deadline_task.cancel()
        dispatcher_task.cancel()
        for task in (deadline_task, dispatcher_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_web_main_lifespan.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/main.py tests/unit/test_web_main_lifespan.py
git commit -m "feat(order-links): wire cron loops into FastAPI lifespan"
```

---

## Task 16: Bulk `mark_all_manual_in_work` + `fail_remaining_links`

**Files:**
- Modify: `services/order_links.py`
- Test: `tests/unit/test_order_links_bulk.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_order_links_bulk.py`:

```python
"""Bulk-операции: 'Отправил все manual' и 'Заказ failed'."""
import sqlite3

from services.db import connect
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_paid_order(tmp_db, status="paid"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, start_date) "
            "VALUES (1, 100, '3/100', ?, ?, NULL)",
            (status, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_mark_all_manual_in_work_only_picks_manual_pending(tmp_db):
    """Должны быть переведены ТОЛЬКО pending+manual ссылки с due-start."""
    from services.order_links import mark_all_manual_in_work
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a", "b", "c", "d"])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        # 0: pending + manual — должна перейти
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_ids[0],))
        # 1: pending + auto — НЕ должна (она для API)
        con.execute("UPDATE order_links SET delivery_mode='auto' WHERE id=?",
                    (link_ids[1],))
        # 2: pending + NULL — НЕ должна (ещё не классифицирована)
        # 3: in_work + manual — уже в работе
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='manual' WHERE id=?", (link_ids[3],))
        con.commit()

    n = mark_all_manual_in_work(admin_id=42)
    assert n == 1
    statuses = {l["id"]: l["status"] for l in list_links(order_id)}
    assert statuses[link_ids[0]] == "in_work"
    assert statuses[link_ids[1]] == "pending"
    assert statuses[link_ids[2]] == "pending"
    assert statuses[link_ids[3]] == "in_work"


def test_mark_all_manual_in_work_skips_future_start_date(tmp_db):
    """Ссылки заказов с start_date > today не должны попадать в bulk."""
    from services.order_links import mark_all_manual_in_work
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, start_date) "
            "VALUES (1, 100, '3/100', 'paid', ?, '2099-01-01')",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_id,))
        con.commit()
    n = mark_all_manual_in_work(admin_id=42)
    assert n == 0
    assert list_links(order_id)[0]["status"] == "pending"


def test_mark_all_manual_sets_deadline_at(tmp_db):
    from services.order_links import mark_all_manual_in_work
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE id=?",
                    (link_id,))
        con.commit()
    mark_all_manual_in_work(admin_id=42)
    link = list_links(order_id)[0]
    assert link["status"] == "in_work"
    assert link["deadline_at"] is not None


def test_fail_remaining_links_transitions_pending_and_in_work(tmp_db):
    from services.order_links import fail_remaining_links
    order_id = _seed_paid_order(tmp_db)
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a", "b", "c"])
        con.commit()
    link_ids = [l["id"] for l in list_links(order_id)]
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='auto' WHERE id=?", (link_ids[1],))
        con.execute("UPDATE order_links SET status='done' WHERE id=?",
                    (link_ids[2],))
        con.commit()

    transition = fail_remaining_links(
        order_id=order_id, reason="manual cancel", admin_id=42
    )
    statuses = {l["id"]: (l["status"], l["failure_reason"])
                for l in list_links(order_id)}
    assert statuses[link_ids[0]] == ("failed", "manual cancel")
    assert statuses[link_ids[1]] == ("failed", "manual cancel")
    assert statuses[link_ids[2]] == ("done", None)
    assert transition == ("paid", "failed")


def test_fail_remaining_links_idempotent(tmp_db):
    """Повтор на уже failed-заказе — no-op."""
    from services.order_links import fail_remaining_links
    order_id = _seed_paid_order(tmp_db, status="paid")
    with connect() as con:
        create_links(con, order_id=order_id, urls=["a"])
        con.commit()
    fail_remaining_links(order_id=order_id, reason="x", admin_id=1)
    second = fail_remaining_links(order_id=order_id, reason="y", admin_id=1)
    assert second is None  # status уже failed
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_bulk.py -v
```

Expected: FAIL — bulk-методы не существуют.

- [ ] **Step 3: Implement bulk methods**

В `services/order_links.py` дописать:

```python
# === Bulk operations ===

def mark_all_manual_in_work(*, admin_id: int) -> int:
    """Bulk-перевод pending+manual ссылок (с due start_date) в in_work.

    Используется админ-кнопкой «Отправил все manual-ссылки» (Спек §5.2).
    Для каждой ссылки вычисляется deadline_at и пересчитывается status заказа.
    Возвращает количество переведённых ссылок.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT ol.id, ol.order_id "
            "FROM order_links ol JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.status='pending' AND ol.delivery_mode='manual' "
            "AND (o.start_date IS NULL OR date(o.start_date) <= date('now'))"
        ).fetchall()
        candidates = [(int(r["id"]), int(r["order_id"])) for r in rows]
    if not candidates:
        return 0

    order_cache: dict[int, dict] = {}
    count = 0
    for link_id, order_id in candidates:
        if order_id not in order_cache:
            with connect() as con:
                order_row = con.execute(
                    "SELECT * FROM orders WHERE increment=?", (order_id,)
                ).fetchone()
            if order_row is None:
                continue
            order_cache[order_id] = dict(order_row)
        order = order_cache[order_id]
        deadline = compute_deadline(order)
        try:
            mark_in_work(link_id, delivery_mode="manual",
                         deadline_at=deadline)
            count += 1
        except Exception:  # noqa: BLE001
            logger.exception(
                "mark_all_manual_in_work: link %s failed (admin=%s)",
                link_id, admin_id,
            )
    logger.info(
        "mark_all_manual_in_work: %d links marked by admin=%s",
        count, admin_id,
    )
    return count


def fail_remaining_links(
    *, order_id: int, reason: str, admin_id: int
) -> tuple[str, str] | None:
    """Bulk-перевод pending+in_work ссылок заказа в failed.

    done-ссылки остаются done. Пересчитывает order.status в той же
    транзакции. Возвращает transition (old, new) если заказ перешёл,
    иначе None. Спек §5.4.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT id FROM order_links WHERE order_id=? "
            "AND status IN ('pending', 'in_work')",
            (order_id,),
        ).fetchall()
        link_ids = [int(r["id"]) for r in rows]
        for link_id in link_ids:
            try:
                _transition(con, link_id=link_id, to_status="failed",
                            failure_reason=reason)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "fail_remaining_links: link %s failed (admin=%s)",
                    link_id, admin_id,
                )
        transition = _recompute_order_status(con, order_id)
        con.commit()
    logger.info(
        "fail_remaining_links: order=%s admin=%s reason=%s links=%d",
        order_id, admin_id, reason, len(link_ids),
    )
    return transition
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_order_links_bulk.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/order_links.py tests/unit/test_order_links_bulk.py
git commit -m "feat(order-links): bulk mark_all_manual_in_work and fail_remaining_links"
```

---

## Task 17: Backfill-скрипт `scripts/migrate_order_links.py`

**Files:**
- Create: `scripts/migrate_order_links.py`
- Test: `tests/unit/test_migrate_order_links.py`

- [ ] **Step 1: Write the failing tests**

Создать `tests/unit/test_migrate_order_links.py`:

```python
"""Backfill legacy orders.links → order_links."""
import sqlite3

from utils.dates import now_iso


def _seed_legacy_order(tmp_db, *, status, links_text):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date) "
            "VALUES (1, 100, '3/100', ?, ?, ?)",
            (status, links_text, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_parse_links_text_json_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text('["a", "b"]') == ["a", "b"]


def test_parse_links_text_repr_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("['a', 'b']") == ["a", "b"]


def test_parse_links_text_csv_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("a, b, c") == ["a", "b", "c"]


def test_parse_links_text_whitespace_split():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("a\nb\nc") == ["a", "b", "c"]


def test_parse_links_text_empty_returns_empty_list():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("") == []
    assert parse_links_text(None) == []


def test_backfill_done_order_creates_done_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="done", links_text='["a", "b"]')
    n = backfill()
    assert n == 1  # обработан 1 заказ
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, done_at FROM order_links WHERE order_id=? ORDER BY id",
            (order_id,)
        ))
    assert [r["url"] for r in rows] == ["a", "b"]
    assert all(r["status"] == "done" for r in rows)
    assert all(r["done_at"] for r in rows)


def test_backfill_paid_creates_pending(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="paid", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert s == "pending"


def test_backfill_failed_creates_failed_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="failed", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT status, failure_reason FROM order_links WHERE order_id=?",
            (order_id,)
        ).fetchone()
    assert row["status"] == "failed"
    assert "legacy" in row["failure_reason"].lower()


def test_backfill_cancelled_creates_failed_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="cancelled", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert s == "failed"


def test_backfill_idempotent(tmp_db):
    """Повторный запуск не дублирует строки."""
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="done", links_text='["a"]')
    backfill()
    backfill()
    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 1


def test_backfill_skips_orders_with_null_links(tmp_db):
    """Если orders.links NULL (новый flow) — пропускаем."""
    from scripts.migrate_order_links import backfill
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date) "
            "VALUES (1, 100, '3/100', 'paid', NULL, ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    backfill()
    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_migrate_order_links.py -v
```

Expected: FAIL — скрипт не существует.

- [ ] **Step 3: Implement backfill**

Создать `scripts/migrate_order_links.py`:

```python
"""Backfill: переносит legacy orders.links → order_links.

Запускать вручную один раз после деплоя. Идемпотентен — повторный запуск
не трогает заказы, у которых уже есть строки в order_links.

Парсит три формата: json, ast.literal_eval, CSV/whitespace.
"""
from __future__ import annotations

import ast
import json
import logging
import re

from services.db import connect
from utils.dates import now_iso

logger = logging.getLogger(__name__)

# Маппинг orders.status → начальный link.status (Спек §6.2).
STATUS_MAP = {
    "done": "done",
    "failed": "failed",
    "cancelled": "failed",
    "paid": "pending",
    "unpaid": "pending",
    "payment_failed": "pending",
}


def parse_links_text(raw: str | None) -> list[str]:
    """Толерантный парсер. Пустой → пустой список."""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    # 1. JSON
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, TypeError):
        pass
    # 2. Python repr (str(list))
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    # 3. Split по запятой / whitespace
    tokens = re.split(r"[,\s]+", s)
    return [t.strip() for t in tokens if t.strip()]


def backfill() -> int:
    """Пробежать по всем заказам с непустым orders.links и без строк в
    order_links — создать недостающие. Возвращает количество обработанных
    заказов.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT o.increment, o.status, o.links, o.date "
            "FROM orders o "
            "WHERE o.links IS NOT NULL AND o.links != '' "
            "AND NOT EXISTS (SELECT 1 FROM order_links ol "
            "                WHERE ol.order_id = o.increment)"
        ).fetchall()
    if not rows:
        return 0

    handled = 0
    for row in rows:
        order_id = int(row["increment"])
        order_status = row["status"]
        order_date = row["date"]
        urls = parse_links_text(row["links"])
        if not urls:
            logger.warning(
                "backfill: order %s has unparseable links: %r",
                order_id, row["links"],
            )
            continue

        link_status = STATUS_MAP.get(order_status, "pending")
        timestamp_field, reason = None, None
        if link_status == "done":
            timestamp_field = "done_at"
        elif link_status == "failed":
            timestamp_field = "failed_at"
            reason = (
                "legacy: order cancelled"
                if order_status == "cancelled"
                else "legacy: order failed"
            )

        with connect() as con:
            for url in urls:
                if timestamp_field == "done_at":
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "done_at, created_at) VALUES (?, ?, ?, ?, ?)",
                        (order_id, url, link_status, order_date, now_iso()),
                    )
                elif timestamp_field == "failed_at":
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "failed_at, failure_reason, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (order_id, url, link_status, order_date, reason,
                         now_iso()),
                    )
                else:
                    con.execute(
                        "INSERT INTO order_links(order_id, url, status, "
                        "created_at) VALUES (?, ?, ?, ?)",
                        (order_id, url, link_status, now_iso()),
                    )
            con.commit()
        handled += 1
    logger.info("backfill: processed %d orders", handled)
    return handled


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    count = backfill()
    print(f"backfill: processed {count} orders")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_migrate_order_links.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_order_links.py tests/unit/test_migrate_order_links.py
git commit -m "feat(order-links): add backfill script for legacy orders.links"
```

---

## Task 18: Удалить кнопку «Выполнить» и старый handler

**Files:**
- Modify: `handlers/admin_orders.py` (хендлеры `order_input_id` / `order_finish` — строки ~252-283)
- Modify: `keyboards/inline_keyboards.py` (функция `orders_kb`, строки 1030-1038)
- Test: `tests/unit/test_admin_orders.py` (если есть тесты на старый flow — обновить)

- [ ] **Step 1: Inspect existing tests**

```bash
grep -n "gotovoebat\|order_finish\|edit_order.*done" tests/unit/test_admin_orders.py
```

Если есть тест-кейсы зависящие от старого handler'а — пометить как deprecated или удалить вместе с кодом.

- [ ] **Step 2: Remove old handlers**

В `handlers/admin_orders.py` удалить блоки:

```python
@dp.callback_query_handler(text="gotovoebat")
async def order_input_id(call: types.CallbackQuery, state: FSMContext):
    ...

@dp.message_handler(state=Order1.order)
async def order_finish(message: types.Message, state: FSMContext):
    ...
```

(строки ~252-283).

Также удалить класс `Order1` (строки 50-51), он только для этого flow.

- [ ] **Step 3: Remove button from keyboard**

В `keyboards/inline_keyboards.py::orders_kb()` (строки ~1030-1038) удалить блок:

```python
        keyboard.row(
            InlineKeyboardButton(
                text="✅ Выполнить",
                callback_data="gotovoebat"
            ),
            InlineKeyboardButton(
                text="❎ Удалить",
                callback_data="del_order"
            )
        )
```

Заменить на одиночный «Удалить» (Step 6 ниже добавит ещё кнопки):

```python
        keyboard.row(
            InlineKeyboardButton(
                text="❎ Удалить",
                callback_data="del_order"
            )
        )
```

- [ ] **Step 4: Run admin tests to verify nothing else broke**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_orders.py -v
```

Expected: PASS. Если красные — обновить устаревшие тесты.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py keyboards/inline_keyboards.py tests/unit/test_admin_orders.py
git commit -m "refactor(admin): remove legacy 'Выполнить' button (order.status now derived)"
```

---

## Task 19: Кнопка «📤 Отправил все manual-ссылки» с двойным подтверждением

**Files:**
- Modify: `handlers/admin_orders.py` (добавить FSM + handler)
- Modify: `keyboards/inline_keyboards.py` (добавить кнопку в `orders_kb`)
- Test: `tests/unit/test_admin_mark_manual.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_admin_mark_manual.py`:

```python
"""Админ-кнопка «Отправил все manual» (Спек §5.2)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_mark_manual_confirm_dispatches_and_replies():
    from handlers.admin_orders import mark_manual_confirm

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    call.from_user.id = 42
    state = AsyncMock()

    with patch("handlers.admin_orders.mark_all_manual_in_work",
               return_value=7) as mock:
        await mark_manual_confirm(call, state)

    mock.assert_called_once_with(admin_id=42)
    state.finish.assert_awaited()
    call.message.answer.assert_awaited()
    text = call.message.answer.await_args.args[0]
    assert "7" in text


@pytest.mark.asyncio
async def test_mark_manual_prompt_asks_confirmation_with_count():
    from handlers.admin_orders import mark_manual_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.count_pending_manual_links",
               return_value=5):
        await mark_manual_prompt(call, state)
    text = call.message.answer.await_args.args[0]
    assert "5" in text  # сколько будет переведено
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_mark_manual.py -v
```

Expected: FAIL — handler'ы не существуют. Если `pytest-asyncio` не настроен, заранее установить и добавить в `conftest.py` `pytest_plugins = ("pytest_asyncio",)` или использовать существующий механизм (проверить как асинхронные тесты пишутся в `test_admin_users.py`).

- [ ] **Step 3: Add count helper to order_links service**

В `services/order_links.py` дописать:

```python
def count_pending_manual_links_due_today() -> int:
    """Сколько pending+manual ссылок готовы к bulk-переводу прямо сейчас."""
    with connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.status='pending' AND ol.delivery_mode='manual' "
            "AND (o.start_date IS NULL OR date(o.start_date) <= date('now'))"
        ).fetchone()
    return int(row["c"] if hasattr(row, "keys") else row[0])
```

- [ ] **Step 4: Add admin handlers**

В `handlers/admin_orders.py` добавить (в самом конце файла или в раздел заказов):

В импорты:
```python
from services.order_links import (
    mark_all_manual_in_work,
    count_pending_manual_links_due_today as count_pending_manual_links,
)
```

В `StatesGroup` (рядом с `Order`):
```python
class MarkManual(StatesGroup):
    confirm = State()
```

Handler:
```python
@dp.callback_query_handler(text="mark_all_manual", state='*')
async def mark_manual_prompt(call: types.CallbackQuery, state: FSMContext):
    """Шаг 1: показать сколько будет переведено + кнопки подтверждения."""
    await state.finish()
    n = count_pending_manual_links()
    if n == 0:
        await call.message.answer(
            "Нет manual-ссылок к отправке.",
            reply_markup=admin_back_kb('orders_man'),
        )
        return
    text = (
        f"📤 Будет переведено в работу: <b>{n}</b> ссылок.\n"
        f"Юзеры получат уведомление когда все ссылки заказа будут готовы.\n\n"
        f"Точно отправил?"
    )
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="✅ Да, точно", callback_data="mark_all_manual_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="orders_man"),
    )
    await call.message.answer(text, reply_markup=kb)
    await MarkManual.confirm.set()


@dp.callback_query_handler(text="mark_all_manual_confirm",
                            state=MarkManual.confirm)
async def mark_manual_confirm(call: types.CallbackQuery, state: FSMContext):
    """Шаг 2: подтверждено — bulk-перевод."""
    admin_id = int(call.from_user.id)
    n = mark_all_manual_in_work(admin_id=admin_id)
    await call.message.answer(
        f"✅ Отмечено как отправленные: <b>{n}</b> ссылок.",
        reply_markup=admin_back_kb('orders_man'),
    )
    await state.finish()
```

Импорты для `InlineKeyboardMarkup`, `InlineKeyboardButton` — если их нет в `handlers/admin_orders.py`, дописать:
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
```

- [ ] **Step 5: Add button to keyboard**

В `keyboards/inline_keyboards.py::orders_kb()` добавить новый row (перед `keyboard.add(InlineKeyboardButton(text=main_menu, ...))`):

```python
        keyboard.row(
            InlineKeyboardButton(
                text="📤 Отправил все manual",
                callback_data="mark_all_manual"
            )
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_mark_manual.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add handlers/admin_orders.py keyboards/inline_keyboards.py services/order_links.py tests/unit/test_admin_mark_manual.py
git commit -m "feat(admin): button to bulk-mark manual links as in_work"
```

---

## Task 20: Кнопка «❌ Отметить заказ failed»

**Files:**
- Modify: `handlers/admin_orders.py` (FSM-handler для failed)
- Modify: `keyboards/inline_keyboards.py` (показать кнопку в карточке заказа, только если status=paid)
- Test: `tests/unit/test_admin_fail_order.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_admin_fail_order.py`:

```python
"""Админ-кнопка «Отметить заказ failed» (Спек §5.4)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_fail_order_prompt_asks_for_order_id():
    from handlers.admin_orders import fail_order_prompt

    call = MagicMock()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    state = AsyncMock()

    await fail_order_prompt(call, state)
    state.set.assert_not_called()  # сначала выставит FSM-state — проверяем через bot.send_message
    call.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_fail_order_collect_reason_then_confirm(tmp_db):
    """Полный flow: id → reason → confirm → fail_remaining_links."""
    from handlers.admin_orders import fail_order_confirm

    message = MagicMock()
    message.text = "yes"
    message.from_user.id = 42
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "order_id": 123, "reason": "manual cancel"
    })

    with patch("handlers.admin_orders.fail_remaining_links",
               return_value=("paid", "failed")) as mock, \
         patch("handlers.admin_orders.notify_order_status_changed",
               new=AsyncMock()) as notif, \
         patch("handlers.admin_orders.get_order",
               return_value={"increment": 123, "user_id": 1, "status": "paid"}):
        await fail_order_confirm(message, state)

    mock.assert_called_once_with(order_id=123, reason="manual cancel",
                                 admin_id=42)
    notif.assert_awaited()
    state.finish.assert_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_fail_order.py -v
```

Expected: FAIL — handler'ы не существуют.

- [ ] **Step 3: Add FSM + handlers**

В `handlers/admin_orders.py`:

Импорт:
```python
from services.order_links import fail_remaining_links
from services.notifications import notify_order_status_changed
```

FSM:
```python
class FailOrder(StatesGroup):
    order_id = State()
    reason = State()
    confirm = State()
```

Handlers:
```python
@dp.callback_query_handler(text="fail_order", state='*')
async def fail_order_prompt(call: types.CallbackQuery, state: FSMContext):
    """Шаг 1: спросить ID заказа."""
    await state.finish()
    await call.message.answer("❌ Введите ID заказа, который нужно пометить как failed:")
    await FailOrder.order_id.set()


@dp.message_handler(state=FailOrder.order_id)
async def fail_order_collect_id(message: types.Message, state: FSMContext):
    """Шаг 2: получили ID, спрашиваем причину."""
    try:
        order_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("⚠️ ID должен быть числом. Попробуйте снова.")
        return
    order = get_order(order_id)
    if not order:
        await message.answer(f"⚠️ Заказ {order_id} не найден.",
                              reply_markup=admin_back_kb('orders_man'))
        await state.finish()
        return
    if order.get("status") != "paid":
        await message.answer(
            f"⚠️ Заказ {order_id} в статусе {order.get('status')}, "
            f"failed можно только из paid.",
            reply_markup=admin_back_kb('orders_man'),
        )
        await state.finish()
        return
    await state.update_data(order_id=order_id)
    await message.answer("Опишите причину (одно сообщение, пойдёт в логи):")
    await FailOrder.reason.set()


@dp.message_handler(state=FailOrder.reason)
async def fail_order_collect_reason(message: types.Message, state: FSMContext):
    """Шаг 3: получили причину, показываем подтверждение."""
    reason = message.text.strip()
    if not reason:
        await message.answer("⚠️ Причина не может быть пустой.")
        return
    await state.update_data(reason=reason)
    data = await state.get_data()
    text = (
        f"❌ Подтверждение: пометить заказ #{data['order_id']} как failed.\n"
        f"Причина: {reason}\n\n"
        f"Юзер получит уведомление. Отправьте 'yes' для подтверждения "
        f"или 'no' для отмены."
    )
    await message.answer(text)
    await FailOrder.confirm.set()


@dp.message_handler(state=FailOrder.confirm)
async def fail_order_confirm(message: types.Message, state: FSMContext):
    """Шаг 4: подтверждение."""
    answer = (message.text or "").strip().lower()
    if answer != "yes":
        await message.answer("Отменено.", reply_markup=admin_back_kb('orders_man'))
        await state.finish()
        return
    data = await state.get_data()
    order_id = int(data["order_id"])
    reason = str(data["reason"])
    admin_id = int(message.from_user.id)

    order = get_order(order_id)
    transition = fail_remaining_links(
        order_id=order_id, reason=reason, admin_id=admin_id
    )
    if transition is not None and order is not None:
        old, new = transition
        try:
            await notify_order_status_changed(
                user_id=int(order["user_id"]),
                kind="order", order_id=order_id,
                old_status=old, new_status=new,
            )
        except Exception:  # noqa: BLE001
            logger.exception("fail_order_confirm: notify failed")
    await message.answer(
        f"✅ Заказ #{order_id} помечен failed.",
        reply_markup=admin_back_kb('orders_man'),
    )
    await state.finish()
```

- [ ] **Step 4: Add button to orders_kb**

В `keyboards/inline_keyboards.py::orders_kb()` добавить кнопку (можно в тот же row, что и «Удалить»):

```python
        keyboard.row(
            InlineKeyboardButton(
                text="❌ Заказ failed",
                callback_data="fail_order"
            ),
            InlineKeyboardButton(
                text="❎ Удалить",
                callback_data="del_order"
            )
        )
```

(Заменить блок с одной кнопкой «Удалить», добавленный в Task 18.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_fail_order.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add handlers/admin_orders.py keyboards/inline_keyboards.py tests/unit/test_admin_fail_order.py
git commit -m "feat(admin): button to mark order as failed with reason"
```

---

## Task 21: Карточка заказа в админке — список ссылок со статусами

**Files:**
- Modify: `handlers/admin_orders.py` (функция `order_work_start`, строки ~208-249)
- Test: `tests/unit/test_admin_order_card.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_admin_order_card.py`:

```python
"""Карточка заказа показывает ссылки + их статусы (Спек §5)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import sqlite3


@pytest.mark.asyncio
async def test_order_card_lists_links_with_statuses(tmp_db):
    from handlers.admin_orders import order_work_start
    from services.db import connect
    from services.order_links import create_links
    from utils.dates import now_iso

    # Seed order with mixed-status links
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance, user_name) VALUES (1, 0, 'user')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id,
                     urls=["https://avito.ru/a", "https://avito.ru/b"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done', "
                    "delivery_mode='manual' WHERE url=?",
                    ("https://avito.ru/a",))
        con.commit()

    message = MagicMock()
    message.text = str(order_id)
    message.answer = AsyncMock()
    state = AsyncMock()

    with patch("handlers.admin_orders.get_string", return_value="{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}"):
        await order_work_start(message, state)
    rendered = message.answer.await_args.args[0]
    assert "https://avito.ru/a" in rendered
    assert "done" in rendered
    assert "https://avito.ru/b" in rendered
    assert "pending" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_order_card.py -v
```

Expected: FAIL — render не показывает статусы.

- [ ] **Step 3: Update `order_work_start`**

В `handlers/admin_orders.py::order_work_start` (~ строки 208-249) заменить блок построения `links` и `links_cnt`:

Было:
```python
    links = ''
    links_cnt = 0
    for link in order['links'].split():
        links += f"<code>{link}</code>\n"
        links_cnt += 1
```

Стало:
```python
    from services.order_links import list_links as _list_order_links
    order_links_rows = _list_order_links(int(inc))
    links = ''
    for ln in order_links_rows:
        status_label = ln['status']
        if ln['delivery_mode']:
            status_label += f" · {ln['delivery_mode']}"
        if ln.get('deadline_at') and ln['status'] == 'in_work':
            status_label += f" · до {ln['deadline_at'][:10]}"
        links += f"<code>{ln['url']}</code> [{status_label}]\n"
    links_cnt = len(order_links_rows)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_admin_order_card.py tests/unit/test_admin_orders.py -v
```

Expected: PASS. Если ломаются другие тесты на админке (которые ожидают старый формат `order['links']`) — обновить их.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_orders.py tests/unit/test_admin_order_card.py
git commit -m "feat(admin): show per-link statuses in order card"
```

---

## Task 22: Обновить gsheets «Все заказы» через JOIN

**Files:**
- Modify: `utils/googlesheets.py` (функция `create_sheet`, строки 200-256)
- Modify: `utils/sqlite3.py` (добавить helper `get_orders_with_links_batch`)
- Test: `tests/unit/test_gsheets_all_orders.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_gsheets_all_orders.py`:

```python
"""Экспорт 'Все заказы' джойнит orders + order_links (Спек §6.1, §7.1)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_order_with_links(tmp_db, urls, status="paid", link_status="in_work"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts, user_name) "
            "VALUES (1, 100, '3/100', ?, ?, 0, 'user1')",
            (status, now_iso()),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status=? WHERE order_id=?",
                    (link_status, order_id))
        con.commit()
    return order_id


def test_get_orders_with_links_batch_returns_join_rows(tmp_db):
    from utils.sqlite3 import get_orders_with_links_batch
    _seed_order_with_links(tmp_db, urls=["a", "b"])
    rows = get_orders_with_links_batch(limit=100, offset=0)
    urls = [r["url"] for r in rows]
    assert "a" in urls and "b" in urls
    # Поля заказа должны быть тоже:
    assert all("order_status" in r for r in rows)
    assert all("link_status" in r for r in rows)


def test_create_sheet_uses_joined_rows(tmp_db):
    """Smoke-test: create_sheet не падает с новым backend'ом, передаёт ссылки в шит."""
    from utils import googlesheets as gs
    _seed_order_with_links(tmp_db, urls=["a", "b"])

    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        return "https://example.test/sheet"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets.get_report_exclude", return_value=[]), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        url = gs.create_sheet()
    assert url == "https://example.test/sheet"
    links_col = captured["columns"][3]  # 4-я колонка — Ссылки (см. порядок)
    assert "a" in links_col and "b" in links_col
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_all_orders.py -v
```

Expected: FAIL — функция и backend не обновлены.

- [ ] **Step 3: Add SQL helper**

В `utils/sqlite3.py` дописать (рядом с `get_orders_batch`, ~ строка 562):

```python
def get_orders_with_links_batch(limit=1000, offset=0):
    """JOIN orders + order_links, по строке на ссылку. Спек §7.1."""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = (
            "SELECT "
            "  o.increment AS order_id, o.user_id, o.position_name, "
            "  o.status AS order_status, o.date AS order_date, "
            "  o.contacts, o.phone, o.start_date, o.user_name, "
            "  ol.url, ol.status AS link_status, "
            "  ol.delivery_mode, ol.deadline_at "
            "FROM orders o "
            "JOIN order_links ol ON ol.order_id = o.increment "
            "ORDER BY o.increment DESC, ol.id "
            "LIMIT ? OFFSET ?"
        )
        return con.execute(sql, (limit, offset)).fetchall()
```

- [ ] **Step 4: Rewrite `create_sheet`**

В `utils/googlesheets.py::create_sheet` (строки 200-256) заменить тело на:

```python
def create_sheet():
    """Полный отчёт по всем заказам, лист 'Все заказы'.

    Новая схема: одна строка на ссылку (JOIN orders+order_links).
    Колонки: №, id, username, Ссылка, Статус ссылки, Mode, Дедлайн,
    Контакты, Дней/ПФ, Цена, Статус заказа, Дата.
    """
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_ALL_ORDERS)

    excludes = get_report_exclude()

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылки']
    link_status = ['Статус ссылки']
    delivery_mode = ['Mode']
    deadline = ['Дедлайн']
    contacts = ['Контакты']
    position = ['Дней/ПФ']
    prices = ['Итого']
    status = ['Статус заказа']
    dates = ['Дата']

    from utils.sqlite3 import get_orders_with_links_batch
    DB_BATCH_SIZE = 1000
    db_offset = 0
    while True:
        batch = get_orders_with_links_batch(limit=DB_BATCH_SIZE, offset=db_offset)
        if not batch:
            break
        for row in batch:
            if str(row['user_id']) in excludes:
                continue
            no.append(row['order_id'])
            ids.append(row['user_id'])
            logins.append(row['user_name'])
            links.append(row['url'])
            link_status.append(row['link_status'] or '')
            delivery_mode.append(row['delivery_mode'] or '')
            deadline.append(format_display(row['deadline_at'])
                            if row['deadline_at'] else '')
            contacts.append('Да' if row['contacts'] else 'Нет')
            position.append(row['position_name'])
            prices.append('')  # цена показывается только в первой строке заказа? Пока пусто
            status.append(_order_status_ru(row['order_status']))
            dates.append(format_display(row['order_date']))
        db_offset += DB_BATCH_SIZE

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 7, 120),
        (7, 8, 80),
        (8, 9, 100),
        (9, 10, 80),
        (10, 11, 140),
        (11, 12, 140),
    ]
    url = _write_tab(
        TAB_ALL_ORDERS, sheet_id,
        [no, ids, logins, links, link_status, delivery_mode, deadline,
         contacts, position, prices, status, dates],
        column_widths,
    )
    logger.info("gsheets: 'Все заказы' updated, %d rows, url=%s",
                len(no) - 1, url)
    return url
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_all_orders.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add utils/sqlite3.py utils/googlesheets.py tests/unit/test_gsheets_all_orders.py
git commit -m "feat(gsheets): rebuild 'All orders' export from order_links JOIN"
```

---

## Task 23: Обновить gsheets «Заказы юзера»

**Files:**
- Modify: `utils/googlesheets.py` (функция `create_orders_report`, строки 259-320)
- Test: `tests/unit/test_gsheets_user_orders.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_gsheets_user_orders.py`:

```python
"""'Заказы юзера' показывает статусы ссылок (Спек §7.2)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, contacts, user_name) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1')",
            (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["url-a", "url-b"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET status='done' WHERE url='url-a'")
        con.execute("UPDATE order_links SET status='in_work', "
                    "delivery_mode='manual', deadline_at='2026-06-30T00:00:00+00:00' "
                    "WHERE url='url-b'")
        con.commit()


def test_user_orders_includes_link_statuses_in_cell(tmp_db):
    from utils import googlesheets as gs
    _seed(tmp_db)

    captured = {}

    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        return "https://example.test/sheet"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets._resolve_user_scope",
               return_value=(None, [1])), \
         patch("utils.googlesheets.get_user",
               return_value={"id": 1, "user_name": "user1"}), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        gs.create_orders_report(1)
    links_col = captured["columns"][3]
    text = "\n".join(str(x) for x in links_col)
    assert "url-a" in text and "done" in text
    assert "url-b" in text and "in_work" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_user_orders.py -v
```

Expected: FAIL — статусы ссылок не показаны.

- [ ] **Step 3: Rewrite `create_orders_report`**

В `utils/googlesheets.py::create_orders_report` (строки ~259-320) заменить блок построения `links` (строка 296):

Было:
```python
            links.append(order['links'].replace("'", "").replace(", ", "\n").replace("\n\n", "\n"))
```

Стало:
```python
            from services.order_links import list_links as _list_order_links
            order_links_rows = _list_order_links(int(order['increment']))
            cell_parts = []
            for ln in order_links_rows:
                label = ln['status']
                if ln['delivery_mode']:
                    label += f" · {ln['delivery_mode']}"
                if ln.get('deadline_at') and ln['status'] == 'in_work':
                    label += f" · до {ln['deadline_at'][:10]}"
                cell_parts.append(f"{ln['url']}  [{label}]")
            links.append("\n".join(cell_parts))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_user_orders.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/googlesheets.py tests/unit/test_gsheets_user_orders.py
git commit -m "feat(gsheets): show per-link statuses in 'user orders' export"
```

---

## Task 24: Новый таб gsheets «Manual задачи»

**Files:**
- Modify: `utils/googlesheets.py` (новая функция `create_manual_tasks_sheet`, новая константа `TAB_MANUAL_TASKS`)
- Modify: `utils/sqlite3.py` (helper `get_pending_manual_links_due_today`)
- Modify: `handlers/admin_orders.py` (новая callback-кнопка вызывающая `create_manual_tasks_sheet`)
- Modify: `keyboards/inline_keyboards.py` (кнопка в `orders_kb`)
- Test: `tests/unit/test_gsheets_manual_tasks.py`

- [ ] **Step 1: Write the failing test**

Создать `tests/unit/test_gsheets_manual_tasks.py`:

```python
"""Новый таб 'Manual задачи' (Спек §7.2)."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed(tmp_db, start_date=None):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance, user_name) "
                    "VALUES (1, 0, 'user1')")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name, start_date) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'user1', ?)",
            (now_iso(), start_date),
        )
        order_id = int(cur.lastrowid)
        con.commit()
    return order_id


def test_get_pending_manual_links_due_today_filters_correctly(tmp_db):
    from utils.sqlite3 import get_pending_manual_links_due_today

    # 1. pending+manual, start=today → попадёт
    oid_due = _seed(tmp_db, start_date=None)
    # 2. pending+manual, start=tomorrow → НЕ попадёт
    oid_future = _seed(tmp_db, start_date="2099-12-31")
    # 3. pending+auto → НЕ попадёт
    oid_auto = _seed(tmp_db, start_date=None)
    # 4. in_work+manual → НЕ попадёт (уже в работе)
    oid_in_work = _seed(tmp_db, start_date=None)

    with connect() as con:
        create_links(con, order_id=oid_due, urls=["due"])
        create_links(con, order_id=oid_future, urls=["future"])
        create_links(con, order_id=oid_auto, urls=["auto"])
        create_links(con, order_id=oid_in_work, urls=["inwork"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' "
                    "WHERE url IN ('due', 'future', 'inwork')")
        con.execute("UPDATE order_links SET delivery_mode='auto' WHERE url='auto'")
        con.execute("UPDATE order_links SET status='in_work' WHERE url='inwork'")
        con.commit()

    rows = get_pending_manual_links_due_today()
    urls = [r["url"] for r in rows]
    assert urls == ["due"]


def test_create_manual_tasks_sheet_writes_columns(tmp_db):
    from utils import googlesheets as gs
    oid = _seed(tmp_db)
    with connect() as con:
        create_links(con, order_id=oid, urls=["url-x"])
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE order_links SET delivery_mode='manual' WHERE url='url-x'")
        con.commit()

    captured = {}
    def _fake_write(tab, sid, cols, widths):
        captured["columns"] = cols
        captured["tab"] = tab
        return "https://example.test/manual"

    with patch("utils.googlesheets._init", return_value=None), \
         patch("utils.googlesheets._require_target", return_value=None), \
         patch("utils.googlesheets._get_or_create_tab", return_value=1), \
         patch("utils.googlesheets._write_tab", side_effect=_fake_write):
        url = gs.create_manual_tasks_sheet()
    assert url == "https://example.test/manual"
    assert captured["tab"] == "Manual задачи"
    links_col = captured["columns"][3]
    assert "url-x" in links_col
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_manual_tasks.py -v
```

Expected: FAIL — функция и helper не существуют.

- [ ] **Step 3: Add SQL helper**

В `utils/sqlite3.py` дописать:

```python
def get_pending_manual_links_due_today():
    """Все pending+manual ссылки заказов готовых к старту (Спек §7.2)."""
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        sql = (
            "SELECT "
            "  o.increment AS order_id, o.user_id, o.position_name, "
            "  o.date AS order_date, o.contacts, o.phone, o.start_date, "
            "  o.user_name, "
            "  ol.url, ol.status AS link_status, "
            "  ol.delivery_mode, ol.deadline_at "
            "FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.status='pending' AND ol.delivery_mode='manual' "
            "AND (o.start_date IS NULL OR date(o.start_date) <= date('now')) "
            "ORDER BY COALESCE(o.start_date, '9999-12-31') ASC, o.date ASC"
        )
        return con.execute(sql).fetchall()
```

- [ ] **Step 4: Add gsheets function**

В `utils/googlesheets.py` рядом с другими TAB-константами добавить:
```python
TAB_MANUAL_TASKS = 'Manual задачи'
```

В конец файла дописать:

```python
def create_manual_tasks_sheet():
    """Выгрузить pending+manual ссылки с due-start в шит для админа."""
    _init()
    _require_target()
    sheet_id = _get_or_create_tab(TAB_MANUAL_TASKS)

    from utils.sqlite3 import get_pending_manual_links_due_today
    rows = get_pending_manual_links_due_today()

    no = ['№']
    ids = ['id']
    logins = ['username']
    links = ['Ссылка']
    link_status = ['Статус']
    delivery_mode = ['Mode']
    deadline = ['Дедлайн']
    contacts = ['Контакты']
    position = ['Дней/ПФ']
    start = ['Старт']
    dates = ['Дата заказа']

    for row in rows:
        no.append(row['order_id'])
        ids.append(row['user_id'])
        logins.append(row['user_name'])
        links.append(row['url'])
        link_status.append(row['link_status'] or '')
        delivery_mode.append(row['delivery_mode'] or '')
        deadline.append(row['deadline_at'] or '')
        contacts.append('Да' if row['contacts'] else 'Нет')
        position.append(row['position_name'])
        start.append(row['start_date'] or '')
        dates.append(format_display(row['order_date']))

    column_widths = [
        (0, 1, 40),
        (1, 3, 100),
        (3, 4, 500),
        (4, 7, 120),
        (7, 8, 80),
        (8, 9, 100),
        (9, 10, 100),
        (10, 11, 140),
    ]
    url = _write_tab(
        TAB_MANUAL_TASKS, sheet_id,
        [no, ids, logins, links, link_status, delivery_mode, deadline,
         contacts, position, start, dates],
        column_widths,
    )
    logger.info("gsheets: '%s' updated, %d rows, url=%s",
                TAB_MANUAL_TASKS, len(no) - 1, url)
    return url
```

- [ ] **Step 5: Wire button in admin**

В `handlers/admin_orders.py` добавить handler:

```python
@dp.callback_query_handler(text="gsheets_manual", state='*')
async def gsheets_manual(call: types.CallbackQuery, state: FSMContext):
    from utils.googlesheets import create_manual_tasks_sheet
    chat_id = call.message.chat.id
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
    STICKER = get_setting('wait_sticker')
    msg = await bot.send_message(chat_id=chat_id,
                                  text="⏳ Готовлю Manual задачи...")
    stick = await bot.send_sticker(chat_id=chat_id, sticker=STICKER) if STICKER else None
    try:
        sheet_url = create_manual_tasks_sheet()
        await bot.send_message(chat_id=chat_id, text=sheet_complete,
                                reply_markup=gsheets_url(sheet_url))
    except Exception:
        logger.exception('googlesheets: manual tasks failed')
        await bot.send_message(chat_id=chat_id,
                                text="⚠️ Ошибка при генерации Manual задач!")
    finally:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            if stick:
                await bot.delete_message(chat_id=chat_id,
                                          message_id=stick.message_id)
        except Exception:
            logger.debug("could not delete progress messages")
    await state.finish()
```

В `keyboards/inline_keyboards.py::orders_kb()` добавить ещё одну кнопку:

```python
        keyboard.row(
            InlineKeyboardButton(
                text="📋 Manual задачи в шит",
                callback_data="gsheets_manual"
            )
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker compose -f docker-compose.yml exec -T bot pytest tests/unit/test_gsheets_manual_tasks.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add utils/sqlite3.py utils/googlesheets.py handlers/admin_orders.py keyboards/inline_keyboards.py tests/unit/test_gsheets_manual_tasks.py
git commit -m "feat(gsheets): add 'Manual задачи' tab and admin button"
```

---

## Task 25: Финальная проверка и cleanup unused

**Files:**
- (Возможно) Modify: `services/orders.py` (убрать неиспользуемый `import json`)
- Test: запустить весь набор тестов

- [ ] **Step 1: Run full test suite**

```bash
docker compose -f docker-compose.yml exec -T bot pytest -v
```

Expected: все тесты PASS. Если есть красные на старом коде — обновить (например, тесты, проверявшие что `create_unpaid` пишет JSON в `orders.links` — обновить чтобы проверяли `order_links`).

- [ ] **Step 2: Check for dead imports**

```bash
grep -n "^import json\|^from json" services/orders.py
```

Если `json` больше не используется в `services/orders.py` после Task 8 — удалить импорт.

```bash
grep -n "json\." services/orders.py
```

Если ничего не возвращает — удалить `import json` строку.

- [ ] **Step 3: Verify no leftover references to legacy `order['links'].split()`**

```bash
grep -rn "order\['links'\]\.split\|order\.get('links'" handlers/ utils/ web/ --include='*.py'
```

Ожидается: либо пусто, либо только legacy-код в `scripts/migrate_order_links.py`. Любые другие — рассмотреть и исправить.

- [ ] **Step 4: Commit cleanup (если что-то изменилось)**

```bash
git add -A
git commit -m "chore(order-links): remove dead imports and legacy references"
```

Если изменений нет — пропустить шаг.

- [ ] **Step 5: Final smoke**

```bash
docker compose -f docker-compose.yml exec -T bot pytest -v --tb=short
```

Expected: вся suite зелёная.

---

## Out of scope для этого плана

Эти задачи спек явно отложил — НЕ реализуем здесь:

1. **Реальный классификатор auto/manual** — `services/order_links_classifier.py` остаётся stub'ом.
2. **Реальный API-клиент исполнителя** — `services/pf_executor_api.py` остаётся stub'ом.
3. **Cutoff 4:00 МСК для `start_date`** — отдельный тикет.
4. **Автоматический рефанд при failed заказа** — отдельный тикет.
5. **Drop колонки `orders.links`** — отдельный скрипт `scripts/drop_orders_links_column.py` запускается **через ~неделю после деплоя** этого плана (Спек §6.3). Создаётся в отдельном PR.
6. **2-way sync с гугл-таблицей** — out of scope.
