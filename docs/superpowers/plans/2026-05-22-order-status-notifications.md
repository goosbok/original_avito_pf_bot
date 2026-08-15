# Order Status Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an order's status changes to `Posted` / `Completed` / `Cancelled`, the customer gets a Telegram push and a durable record in a new in-app bell feed. Covers regular orders, review-orders, and delete-review-orders; replaces ad-hoc one-off `bot.send_message` legacy calls.

**Architecture:** A single service `services/notifications.py` materializes a notification row in a new `notifications` SQLite table, then fire-and-forgets a Telegram push. Two web HTTP endpoints serve the bell (list + mark-all-read). A React component `NotificationsBell.jsx` polls every 30s and renders a badge + dropdown. Four callsites (1 web admin route, 3 TG admin handlers) call the service.

**Tech Stack:** Python 3 / FastAPI / aiogram / SQLite / React 18 (via babel-standalone in static).

**Spec:** [docs/superpowers/specs/2026-05-22-order-status-notifications-design.md](../specs/2026-05-22-order-status-notifications-design.md)

**Tests in this codebase:** All Python tests run inside Docker via `docker compose -f docker-compose.yml exec -T app pytest <path> -v` (per repo convention). Don't run pytest locally.

---

## Task 1: Add `notifications` table and indexes to schema

**Files:**
- Modify: `utils/sqlite3.py` (function `get_schema_statements`, ~line 816; function `get_index_statements`, ~line 1034)
- Test: `tests/unit/test_db_schema.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_db_schema.py` (append at end):

```python
def test_notifications_table_in_schema(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(notifications)")}
    assert cols == {
        "id", "user_id", "kind", "order_id", "new_status",
        "text", "created_at", "read_at",
    }


def test_notifications_indexes_present(tmp_db):
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        idx = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notifications'"
        )}
    assert "idx_notifications_user_unread" in idx
    assert "idx_notifications_user_created" in idx
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_db_schema.py::test_notifications_table_in_schema tests/unit/test_db_schema.py::test_notifications_indexes_present -v
```

Expected: FAIL — table `notifications` doesn't exist.

- [ ] **Step 3: Add schema statement**

In `utils/sqlite3.py`, locate `get_schema_statements()` (~line 816). After the last tuple inside the returned list (before the closing `]`), append:

```python
        (
            "notifications",
            "CREATE TABLE IF NOT EXISTS notifications("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "kind TEXT NOT NULL,"
            "order_id INTEGER,"
            "new_status TEXT,"
            "text TEXT NOT NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "read_at TIMESTAMP)",
            8,
        ),
```

In `get_index_statements()` (~line 1034), append the two new indexes to the returned list:

```python
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread "
        "ON notifications(user_id, read_at)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_created "
        "ON notifications(user_id, created_at DESC)",
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_db_schema.py -v
```

Expected: PASS (both new tests + all existing schema tests).

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_db_schema.py
git commit -m "feat(db): add notifications table for order status feed"
```

---

## Task 2: Service — `_build_text` (template lookup)

**Files:**
- Create: `services/notifications.py`
- Test: `tests/unit/test_notifications.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_notifications.py`:

```python
"""Tests for services.notifications."""
from __future__ import annotations

import pytest


def test_build_text_order_posted():
    from services.notifications import _build_text
    assert _build_text("order", "Posted", order_id=5) == "📌 Заказ №5 размещён."


def test_build_text_order_completed():
    from services.notifications import _build_text
    assert _build_text("order", "Completed", order_id=42) == "✅ Заказ №42 выполнен."


def test_build_text_order_cancelled():
    from services.notifications import _build_text
    assert _build_text("order", "Cancelled", order_id=7) == "❌ Заказ №7 отменён."


def test_build_text_order_review_completed():
    from services.notifications import _build_text
    assert _build_text(
        "order_review", "Completed", order_id=3, service="Avito",
    ) == "🎉 Заказ №3 на отзыв (Avito) выполнен."


def test_build_text_order_delreview_completed():
    from services.notifications import _build_text
    assert _build_text(
        "order_delreview", "Completed", order_id=9, service="Yandex",
    ) == "🎉 Заказ №9 на удаление отзыва (Yandex) выполнен."


def test_build_text_unknown_status_returns_none():
    from services.notifications import _build_text
    assert _build_text("order", "Pending", order_id=1) is None
    assert _build_text("order", "In progress", order_id=1) is None


def test_build_text_unknown_kind_returns_none():
    from services.notifications import _build_text
    assert _build_text("guest_order", "Completed", order_id=1) is None


def test_build_text_review_with_cancelled_not_supported():
    from services.notifications import _build_text
    assert _build_text("order_review", "Cancelled", order_id=1, service="x") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: FAIL — `services.notifications` module doesn't exist.

- [ ] **Step 3: Create the service with `_build_text`**

Create `services/notifications.py`:

```python
"""Order status notifications service.

Materializes status-change events as durable rows in `notifications`
(consumed by the LK bell feed) and pushes them to Telegram (best-effort).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TEMPLATES: dict[tuple[str, str], str] = {
    ("order", "Posted"):    "📌 Заказ №{order_id} размещён.",
    ("order", "Completed"): "✅ Заказ №{order_id} выполнен.",
    ("order", "Cancelled"): "❌ Заказ №{order_id} отменён.",
    ("order_review", "Completed"):
        "🎉 Заказ №{order_id} на отзыв ({service}) выполнен.",
    ("order_delreview", "Completed"):
        "🎉 Заказ №{order_id} на удаление отзыва ({service}) выполнен.",
}


def _build_text(kind: str, new_status: str, **fields: object) -> str | None:
    tpl = _TEMPLATES.get((kind, new_status))
    if tpl is None:
        return None
    return tpl.format(**fields)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add services/notifications.py tests/unit/test_notifications.py
git commit -m "feat(notifications): add _build_text template lookup"
```

---

## Task 3: Service — feed read functions

**Files:**
- Modify: `services/notifications.py`
- Test: `tests/unit/test_notifications.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_notifications.py`:

```python
def _insert_notification(tmp_db, *, user_id: int, kind: str = "order",
                        order_id: int = 1, new_status: str = "Completed",
                        text: str = "test", read_at: str | None = None) -> int:
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text, read_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kind, order_id, new_status, text, read_at),
        )
        con.commit()
        return cur.lastrowid


def test_list_notifications_empty(tmp_db):
    from services.notifications import list_notifications
    assert list_notifications(user_id=42) == []


def test_list_notifications_orders_desc_by_id(tmp_db):
    from services.notifications import list_notifications
    a = _insert_notification(tmp_db, user_id=1, text="first")
    b = _insert_notification(tmp_db, user_id=1, text="second")
    rows = list_notifications(user_id=1)
    assert [r["id"] for r in rows] == [b, a]
    assert rows[0]["text"] == "second"


def test_list_notifications_filters_by_user(tmp_db):
    from services.notifications import list_notifications
    _insert_notification(tmp_db, user_id=1, text="alice")
    _insert_notification(tmp_db, user_id=2, text="bob")
    rows = list_notifications(user_id=1)
    assert len(rows) == 1
    assert rows[0]["text"] == "alice"


def test_list_notifications_respects_limit(tmp_db):
    from services.notifications import list_notifications
    for i in range(5):
        _insert_notification(tmp_db, user_id=1, text=f"n{i}")
    assert len(list_notifications(user_id=1, limit=3)) == 3


def test_unread_count_excludes_read(tmp_db):
    from services.notifications import unread_count
    _insert_notification(tmp_db, user_id=1, text="unread1")
    _insert_notification(tmp_db, user_id=1, text="unread2")
    _insert_notification(tmp_db, user_id=1, text="read",
                        read_at="2026-05-22 10:00:00")
    assert unread_count(user_id=1) == 2


def test_unread_count_filters_by_user(tmp_db):
    from services.notifications import unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=2)
    assert unread_count(user_id=1) == 1


def test_mark_all_read_sets_timestamp(tmp_db):
    import sqlite3
    from services.notifications import mark_all_read, unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=1)
    assert mark_all_read(user_id=1) == 2
    assert unread_count(user_id=1) == 0
    with sqlite3.connect(tmp_db) as con:
        read_ats = [r[0] for r in con.execute(
            "SELECT read_at FROM notifications WHERE user_id = 1"
        )]
    assert all(t is not None for t in read_ats)


def test_mark_all_read_idempotent(tmp_db):
    from services.notifications import mark_all_read
    _insert_notification(tmp_db, user_id=1)
    assert mark_all_read(user_id=1) == 1
    assert mark_all_read(user_id=1) == 0


def test_mark_all_read_only_current_user(tmp_db):
    from services.notifications import mark_all_read, unread_count
    _insert_notification(tmp_db, user_id=1)
    _insert_notification(tmp_db, user_id=2)
    assert mark_all_read(user_id=1) == 1
    assert unread_count(user_id=2) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: 9 new tests FAIL with `ImportError` / `AttributeError` for missing functions.

- [ ] **Step 3: Implement the read functions**

Append to `services/notifications.py`:

```python
import sqlite3


def _connect():
    """Open a sqlite3 connection with row factory; honors test path overrides."""
    from utils.sqlite3 import path_db
    con = sqlite3.connect(path_db)
    con.row_factory = sqlite3.Row
    return con


def list_notifications(user_id: int, limit: int = 50) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, kind, order_id, new_status, text, created_at, read_at "
            "FROM notifications WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def unread_count(user_id: int) -> int:
    with _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM notifications "
            "WHERE user_id = ? AND read_at IS NULL",
            (user_id,),
        ).fetchone()
    return int(row["c"])


def mark_all_read(user_id: int) -> int:
    with _connect() as con:
        cur = con.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND read_at IS NULL",
            (user_id,),
        )
        con.commit()
        return cur.rowcount
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/notifications.py tests/unit/test_notifications.py
git commit -m "feat(notifications): add list/unread_count/mark_all_read"
```

---

## Task 4: Service — `notify_order_status_changed` (write path)

**Files:**
- Modify: `services/notifications.py`
- Test: `tests/unit/test_notifications.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_notifications.py`:

```python
import asyncio


def test_notify_noop_when_same_status(tmp_db, monkeypatch):
    from services import notifications

    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(notifications, "_send_tg", fake_send)

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order", order_id=1,
        old_status="Completed", new_status="Completed",
    ))
    assert notifications.unread_count(user_id=10) == 0
    assert sent == []


def test_notify_skips_status_outside_whitelist(tmp_db, monkeypatch):
    from services import notifications

    sent = []
    async def fake_send(**kwargs):
        sent.append(kwargs)
    monkeypatch.setattr(notifications, "_send_tg", fake_send)

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order", order_id=1,
        old_status="Posted", new_status="Pending",
    ))
    assert notifications.unread_count(user_id=10) == 0
    assert sent == []


def test_notify_inserts_row_and_pushes_tg(tmp_db, monkeypatch):
    from services import notifications

    sent = []
    async def fake_send(*, tg_id, text, reply_markup):
        sent.append({"tg_id": tg_id, "text": text})

    monkeypatch.setattr(notifications, "_get_tg_id", lambda uid: 555)
    monkeypatch.setattr(notifications, "_send_tg", fake_send)

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order", order_id=42,
        old_status="Pending", new_status="Completed",
    ))

    rows = notifications.list_notifications(user_id=10)
    assert len(rows) == 1
    assert rows[0]["text"] == "✅ Заказ №42 выполнен."
    assert rows[0]["kind"] == "order"
    assert rows[0]["new_status"] == "Completed"
    assert rows[0]["order_id"] == 42
    assert sent == [{"tg_id": 555, "text": "✅ Заказ №42 выполнен."}]


def test_notify_review_with_service_field(tmp_db, monkeypatch):
    from services import notifications

    sent = []
    async def fake_send(*, tg_id, text, reply_markup):
        sent.append(text)

    monkeypatch.setattr(notifications, "_get_tg_id", lambda uid: 555)
    monkeypatch.setattr(notifications, "_send_tg", fake_send)

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order_review", order_id=3,
        old_status="Posted", new_status="Completed",
        service="Avito",
    ))

    rows = notifications.list_notifications(user_id=10)
    assert rows[0]["text"] == "🎉 Заказ №3 на отзыв (Avito) выполнен."
    assert rows[0]["kind"] == "order_review"
    assert sent == ["🎉 Заказ №3 на отзыв (Avito) выполнен."]


def test_notify_no_tg_id_still_writes_row(tmp_db, monkeypatch):
    from services import notifications

    sent = []
    async def fake_send(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(notifications, "_get_tg_id", lambda uid: None)
    monkeypatch.setattr(notifications, "_send_tg", fake_send)

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order", order_id=1,
        old_status="Pending", new_status="Posted",
    ))

    assert notifications.unread_count(user_id=10) == 1
    assert sent == []


def test_notify_tg_failure_swallowed_row_persists(tmp_db, monkeypatch, caplog):
    from services import notifications
    import logging

    async def boom(**kwargs):
        raise RuntimeError("BotBlocked")

    monkeypatch.setattr(notifications, "_get_tg_id", lambda uid: 555)
    monkeypatch.setattr(notifications, "_send_tg", boom)

    caplog.set_level(logging.ERROR, logger="services.notifications")

    asyncio.run(notifications.notify_order_status_changed(
        user_id=10, kind="order", order_id=1,
        old_status="Pending", new_status="Posted",
    ))

    assert notifications.unread_count(user_id=10) == 1
    assert any("TG notify failed" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: 6 new tests FAIL — `notify_order_status_changed`, `_send_tg`, `_get_tg_id` don't exist.

- [ ] **Step 3: Implement the notify function with seams for testing**

Append to `services/notifications.py`:

```python
def _get_tg_id(user_id: int) -> int | None:
    """Test seam — wraps utils.sqlite3.get_tg_id_for_user."""
    from utils.sqlite3 import get_tg_id_for_user
    return get_tg_id_for_user(user_id)


async def _send_tg(*, tg_id: int, text: str, reply_markup) -> None:
    """Test seam — wraps data.loader.bot.send_message."""
    from data.loader import bot
    await bot.send_message(chat_id=tg_id, text=text, reply_markup=reply_markup)


async def notify_order_status_changed(
    *,
    user_id: int,
    kind: str,
    order_id: int,
    old_status: str,
    new_status: str,
    **fields: object,
) -> None:
    if old_status == new_status:
        return

    text = _build_text(kind, new_status, order_id=order_id, **fields)
    if text is None:
        return

    # 1. durable insert (bell feed)
    with _connect() as con:
        con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, order_id, new_status, text),
        )
        con.commit()

    # 2. best-effort TG push
    try:
        tg_id = _get_tg_id(user_id)
        if tg_id is None:
            return
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"))
        await _send_tg(tg_id=tg_id, text=text, reply_markup=kb)
    except Exception:
        logger.exception(
            "TG notify failed for user_id=%s kind=%s order=%s",
            user_id, kind, order_id,
        )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/notifications.py tests/unit/test_notifications.py
git commit -m "feat(notifications): add notify_order_status_changed"
```

---

## Task 5: HTTP API — schemas

**Files:**
- Modify: `web/schemas.py`

- [ ] **Step 1: Inspect existing schemas style**

```bash
grep -n "class.*Response\|class.*Item\|AdminSupport" web/schemas.py | head -15
```

Note: the codebase uses `pydantic.BaseModel` directly with `ConfigDict` or simple Field types. Match the existing style.

- [ ] **Step 2: Add schemas**

Append to `web/schemas.py`:

```python
class NotificationItem(BaseModel):
    id: int
    kind: str
    order_id: int | None
    new_status: str | None
    text: str
    created_at: str
    read_at: str | None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked: int
```

If `BaseModel` is not yet imported in `web/schemas.py`, add `from pydantic import BaseModel` at the top (check first — it's almost certainly already imported).

- [ ] **Step 3: Verify imports parse**

```bash
docker compose -f docker-compose.yml exec -T app python -c "from web.schemas import NotificationItem, NotificationListResponse, MarkAllReadResponse; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add web/schemas.py
git commit -m "feat(web): add notification schemas"
```

---

## Task 6: HTTP API — `notifications` router

**Files:**
- Create: `web/routers/notifications.py`
- Modify: `web/main.py`
- Test: `tests/unit/test_notifications_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_notifications_api.py`:

```python
"""Notifications HTTP API."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (20, 'bob', 'Bob', 0, '2026-01-02')"
        )
        con.commit()


def _seed_notif(tmp_db: Path, **kwargs):
    defaults = {
        "user_id": 10, "kind": "order", "order_id": 1,
        "new_status": "Completed", "text": "test", "read_at": None,
    }
    defaults.update(kwargs)
    with sqlite3.connect(tmp_db) as con:
        cur = con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text, read_at) "
            "VALUES (:user_id, :kind, :order_id, :new_status, :text, :read_at)",
            defaults,
        )
        con.commit()
        return cur.lastrowid


def _token_for(user_id: int) -> str:
    from web.auth import create_jwt
    return create_jwt(user_id)


def _client():
    from web.main import app
    return TestClient(app)


def test_list_notifications_unauthorized(tmp_db):
    _seed(tmp_db)
    r = _client().get("/api/notifications")
    assert r.status_code == 401


def test_list_notifications_returns_user_records_only(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10, text="alice-1")
    _seed_notif(tmp_db, user_id=20, text="bob-1")
    _seed_notif(tmp_db, user_id=10, text="alice-2")

    r = _client().get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    assert r.status_code == 200
    body = r.json()
    texts = [i["text"] for i in body["items"]]
    assert texts == ["alice-2", "alice-1"]  # newest first
    assert body["unread_count"] == 2


def test_list_notifications_unread_count_excludes_read(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10, text="unread")
    _seed_notif(tmp_db, user_id=10, text="read", read_at="2026-05-22 10:00:00")

    r = _client().get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    body = r.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 2


def test_mark_all_read_marks_only_caller(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10)
    _seed_notif(tmp_db, user_id=10)
    _seed_notif(tmp_db, user_id=20)

    r = _client().post(
        "/api/notifications/mark-all-read",
        headers={"Authorization": f"Bearer {_token_for(10)}"},
    )
    assert r.status_code == 200
    assert r.json() == {"marked": 2}

    # bob's record untouched
    with sqlite3.connect(tmp_db) as con:
        bob_unread = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = 20 AND read_at IS NULL"
        ).fetchone()[0]
    assert bob_unread == 1


def test_mark_all_read_idempotent(tmp_db):
    _seed(tmp_db)
    _seed_notif(tmp_db, user_id=10)

    headers = {"Authorization": f"Bearer {_token_for(10)}"}
    assert _client().post("/api/notifications/mark-all-read", headers=headers).json() == {"marked": 1}
    assert _client().post("/api/notifications/mark-all-read", headers=headers).json() == {"marked": 0}


def test_mark_all_read_unauthorized(tmp_db):
    _seed(tmp_db)
    r = _client().post("/api/notifications/mark-all-read")
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications_api.py -v
```

Expected: all FAIL — route returns 404.

- [ ] **Step 3: Implement the router**

Create `web/routers/notifications.py`:

```python
"""Endpoints for the in-app notifications bell feed."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from services import notifications as svc
from web.deps import require_user
from web.schemas import (
    MarkAllReadResponse,
    NotificationItem,
    NotificationListResponse,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_(
    user_id: int = Depends(require_user),
) -> NotificationListResponse:
    rows = svc.list_notifications(user_id, limit=50)
    return NotificationListResponse(
        items=[
            NotificationItem(
                id=int(r["id"]),
                kind=str(r["kind"]),
                order_id=(int(r["order_id"]) if r["order_id"] is not None else None),
                new_status=(str(r["new_status"]) if r["new_status"] is not None else None),
                text=str(r["text"]),
                created_at=str(r["created_at"]),
                read_at=(str(r["read_at"]) if r["read_at"] is not None else None),
            )
            for r in rows
        ],
        unread_count=svc.unread_count(user_id),
    )


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    user_id: int = Depends(require_user),
) -> MarkAllReadResponse:
    return MarkAllReadResponse(marked=svc.mark_all_read(user_id))
```

- [ ] **Step 4: Register the router in `web/main.py`**

In `web/main.py`, find the block of `include_router(...)` calls (~line 25–60). Add the import alongside other router imports near the top:

```python
from web.routers.notifications import router as notifications_router
```

And register the router after `me_router` (logical grouping with user-scoped reads):

```python
app.include_router(notifications_router)
```

- [ ] **Step 5: Run tests to verify pass**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications_api.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web/routers/notifications.py web/main.py tests/unit/test_notifications_api.py
git commit -m "feat(web): add /api/notifications endpoints"
```

---

## Task 7: Wire web admin order status change to the service

**Files:**
- Modify: `web/routers/admin_orders.py` (function `change_status`, ~line 107)
- Modify: `tests/unit/test_admin_orders.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_admin_orders.py`:

```python
def test_change_status_creates_notification(tmp_db):
    _seed(tmp_db)
    c = _client_for(tmp_db)
    r = c.post(
        "/api/admin/orders/1/status",
        json={"status": "Completed"},
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200

    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, kind, order_id, new_status, text "
            "FROM notifications WHERE user_id = 10"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "order"
    assert rows[0][3] == "Completed"
    assert "Заказ №1" in rows[0][4]


def test_change_status_no_op_does_not_create_notification(tmp_db):
    _seed(tmp_db)
    c = _client_for(tmp_db)

    # order #2 in _seed is already 'Completed'
    r = c.post(
        "/api/admin/orders/2/status",
        json={"status": "Completed"},
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200

    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = 10"
        ).fetchone()[0]
    assert count == 0


def test_change_status_to_pending_does_not_notify(tmp_db):
    _seed(tmp_db)
    c = _client_for(tmp_db)
    r = c.post(
        "/api/admin/orders/1/status",
        json={"status": "Pending"},
        headers={"Authorization": f"Bearer {_token_for(1)}"},
    )
    assert r.status_code == 200

    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    assert count == 0
```

Note: the test must wait for the `asyncio.create_task` to complete. `TestClient` in starlette runs the route synchronously inside the event loop, and `create_task` may schedule the coroutine without it executing before the response returns. **Important:** to make this deterministic in tests, we change the route to `await` directly when running under TestClient is too invasive — instead we patch the service to also write the DB row synchronously (DB write is sync sqlite, only the TG push is async). The current design already inserts to the DB *before* the TG attempt — so the DB row should be visible immediately if the route awaits the coroutine.

Look at the route changes below — we'll keep `asyncio.create_task` for prod, but the inserted row appears synchronously via the service's synchronous DB write *before any await*. The `create_task` schedules the coroutine — which on starting executes synchronously up to the first `await`. **In CPython asyncio, `create_task` schedules but doesn't run; the coroutine runs only when the loop yields.** That means in TestClient, the test would see no row.

**Resolution:** in the route, run the DB part synchronously by extracting it as a sync helper, then schedule only the TG push via `create_task`. See Step 3.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_admin_orders.py::test_change_status_creates_notification tests/unit/test_admin_orders.py::test_change_status_no_op_does_not_create_notification tests/unit/test_admin_orders.py::test_change_status_to_pending_does_not_notify -v
```

Expected: FAIL.

- [ ] **Step 3: Refactor the service to split sync write and async push**

Modify `services/notifications.py`. Replace the existing `notify_order_status_changed` and add a new sync helper:

```python
def record_order_status_change(
    *,
    user_id: int,
    kind: str,
    order_id: int,
    old_status: str,
    new_status: str,
    **fields: object,
) -> str | None:
    """Sync: write durable notification row. Returns the rendered text, or None
    if the (kind, status) is not in the whitelist or status didn't change.
    Callers schedule push_tg_notification(text=...) for TG delivery."""
    if old_status == new_status:
        return None
    text = _build_text(kind, new_status, order_id=order_id, **fields)
    if text is None:
        return None
    with _connect() as con:
        con.execute(
            "INSERT INTO notifications(user_id, kind, order_id, new_status, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, order_id, new_status, text),
        )
        con.commit()
    return text


async def push_tg_notification(*, user_id: int, text: str) -> None:
    """Best-effort: send text to user's Telegram with a 'Main menu' inline button."""
    try:
        tg_id = _get_tg_id(user_id)
        if tg_id is None:
            return
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"))
        await _send_tg(tg_id=tg_id, text=text, reply_markup=kb)
    except Exception:
        logger.exception("TG notify failed for user_id=%s", user_id)


async def notify_order_status_changed(
    *,
    user_id: int,
    kind: str,
    order_id: int,
    old_status: str,
    new_status: str,
    **fields: object,
) -> None:
    """High-level: sync DB row + async TG push, in that order."""
    text = record_order_status_change(
        user_id=user_id, kind=kind, order_id=order_id,
        old_status=old_status, new_status=new_status, **fields,
    )
    if text is None:
        return
    await push_tg_notification(user_id=user_id, text=text)
```

Re-run the existing service tests to confirm nothing broke:

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_notifications.py -v
```

Expected: all PASS (Task 4 tests still green; `notify_order_status_changed` behavior preserved).

- [ ] **Step 4: Wire the web admin route**

Edit `web/routers/admin_orders.py`. Add imports near the top:

```python
import asyncio

from services.notifications import (
    push_tg_notification,
    record_order_status_change,
)
```

Replace `change_status` (currently ~line 107) with:

```python
@router.post("/{order_id}/status", status_code=200)
async def change_status(
    order_id: int,
    body: AdminOrderStatusChange,
    _: int = Depends(require_admin),
) -> dict:
    with connect() as con:
        row = con.execute(
            "SELECT increment, user_id, status FROM orders WHERE increment = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="order not found")
        old_status = str(row["status"] or "")
        user_id = int(row["user_id"])
        if old_status != body.status:
            con.execute(
                "UPDATE orders SET status = ? WHERE increment = ?",
                (body.status, order_id),
            )
            con.commit()

    if old_status != body.status:
        text = record_order_status_change(
            user_id=user_id, kind="order", order_id=order_id,
            old_status=old_status, new_status=body.status,
        )
        if text is not None:
            asyncio.create_task(push_tg_notification(user_id=user_id, text=text))

    return {"order_id": order_id, "status": body.status}
```

- [ ] **Step 5: Run all related tests**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit/test_admin_orders.py tests/unit/test_notifications.py tests/unit/test_notifications_api.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add services/notifications.py web/routers/admin_orders.py tests/unit/test_admin_orders.py
git commit -m "feat(web): notify on order status change via admin route"
```

---

## Task 8: Wire TG admin orders handler

**Files:**
- Modify: `handlers/admin_orders.py` (function `order_finish`, ~line 257–270)

- [ ] **Step 1: Inspect current implementation**

```bash
sed -n '255,275p' handlers/admin_orders.py
```

Confirm current code matches the spec quote (lines ~256–270).

- [ ] **Step 2: Apply the change**

Replace `order_finish` body. Add at the top of the function:

```python
@dp.message_handler(state=Order1.order)
async def order_finish(message: types.Message, state: FSMContext):
    order = message.text
    order1 = get_order(order)
    if not order1:
        await bot.send_message(chat_id=message.from_user.id, text=f"⚠️ Заказ {order} не найден!", reply_markup=admin_back_kb('orders_man'))
        await state.finish()
        return
    old_status = str(order1.get('status') or '')
    edit_order(status="Completed", order=order)

    from services.notifications import notify_order_status_changed
    await notify_order_status_changed(
        user_id=int(order1['user_id']),
        kind="order",
        order_id=int(order),
        old_status=old_status,
        new_status="Completed",
    )

    await bot.send_message(chat_id=message.from_user.id, text="✅ Успешно")
    await state.finish()
```

Remove the previous `internal_id = ...`, `tg_id = ...`, `if tg_id: await bot.send_message(...)` block — the service handles it.

- [ ] **Step 3: Smoke-import to catch syntax errors**

```bash
docker compose -f docker-compose.yml exec -T app python -c "import handlers.admin_orders; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/admin_orders.py
git commit -m "refactor(handlers): route admin_orders.order_finish via notifications service"
```

---

## Task 9: Wire TG admin reviews handlers

**Files:**
- Modify: `handlers/admin_reviews.py` (functions `review_close` ~line 205, `delreview_close` ~line 305)

- [ ] **Step 1: Inspect current implementations**

```bash
sed -n '205,225p' handlers/admin_reviews.py
sed -n '300,322p' handlers/admin_reviews.py
```

Locate both `bot.send_message(... "🎉 ...")` calls and the surrounding `if tg_id:` blocks.

- [ ] **Step 2: Apply changes**

In `review_close` (~lines 205–225), replace the success branch (`if review['status'] == 'Posted':` ... `await bot.send_message(..., text=f"<b>🎉 Ваш заказ номер {...} ...</b>")`) with:

```python
        if review['status'] == 'Posted':
            edit_order_reviews('Completed', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('reviews_man'))

            from services.notifications import notify_order_status_changed
            await notify_order_status_changed(
                user_id=int(review['user_id']),
                kind="order_review",
                order_id=int(review['increment']),
                old_status='Posted',
                new_status='Completed',
                service=str(review.get('service') or ''),
            )
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('reviews_man'))
```

Also drop the `from utils.sqlite3 import get_tg_id_for_user` at line 207 if it's only used by this removed block (verify with `grep -n "get_tg_id_for_user" handlers/admin_reviews.py` — if no other usage, remove the import).

In `delreview_close` (~lines 300–322), mirror the change:

```python
        if del_review['status'] == 'Posted':
            edit_order_delreviews('Completed', message.text)
            await message.answer('⚙️ Заказ успешно завершен!', reply_markup=admin_back_kb('delreviews_man'))

            from services.notifications import notify_order_status_changed
            await notify_order_status_changed(
                user_id=int(del_review['user_id']),
                kind="order_delreview",
                order_id=int(del_review['increment']),
                old_status='Posted',
                new_status='Completed',
                service=str(del_review.get('service') or ''),
            )
        else:
            await message.answer('⚠️ Заказ уже завершен!', reply_markup=admin_back_kb('delreviews_man'))
```

(Use the actual button keys in `admin_back_kb(...)` calls — check current code in case they differ slightly.)

- [ ] **Step 3: Smoke-import**

```bash
docker compose -f docker-compose.yml exec -T app python -c "import handlers.admin_reviews; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add handlers/admin_reviews.py
git commit -m "refactor(handlers): route admin_reviews close handlers via notifications service"
```

---

## Task 10: Remove the dead `'In progress'` branch

**Files:**
- Modify: `handlers/admin_reviews.py` (~line 145–149)

- [ ] **Step 1: Verify the status is never written**

```bash
grep -rn "'In progress'" --include="*.py" .
grep -rn '"In progress"' --include="*.py" .
```

Expected: every match is a READ (right-hand side of `==`, dict comparison, or admin button label). If any match is a `INSERT INTO ... status` or `UPDATE ... SET status = ...` with `'In progress'`, **abort this task** and document the surviving callsite.

- [ ] **Step 2: Inspect the branch**

```bash
sed -n '140,155p' handlers/admin_reviews.py
```

Confirm the branch is `elif order['status'] == 'In progress':` and is reachable only when DB rows have that value — which Step 1 proved cannot happen for new rows.

- [ ] **Step 3: Remove the branch**

Edit `handlers/admin_reviews.py:~145–149`. Drop the `elif order['status'] == 'In progress':` block and merge its content into preceding/following branches if needed (most likely just delete it — the surrounding logic likely sets a display label; dead status → dead branch).

If unsure how the value would have been displayed historically, keep behavior identical for any rows that *might* still have it by treating them as fallback in the existing `else` branch (no separate elif).

- [ ] **Step 4: Smoke-import**

```bash
docker compose -f docker-compose.yml exec -T app python -c "import handlers.admin_reviews; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add handlers/admin_reviews.py
git commit -m "chore(handlers): drop dead 'In progress' status branch"
```

---

## Task 11: Frontend — `NotificationsBell` component (skeleton + bell button)

**Files:**
- Create: `web/static/components/NotificationsBell.jsx`
- Modify: `web/static/index.html` (add `<script>` tag if components are loaded individually)
- Modify: `web/static/platform.css`

- [ ] **Step 1: Inspect how existing components are loaded**

```bash
grep -n "components/" web/static/index.html
```

Note the order and pattern (Babel-transformed `<script type="text/babel" src="components/X.jsx">`).

- [ ] **Step 2: Create the component file (no functionality yet)**

Create `web/static/components/NotificationsBell.jsx`:

```jsx
// NotificationsBell — bell icon with unread badge + dropdown panel of recent notifications.

const {
  useState: useBellState,
  useEffect: useBellEffect,
  useRef: useBellRef,
} = React;

function NotificationsBell({ pollMs = 30000 }) {
  const [items, setItems] = useBellState([]);
  const [unread, setUnread] = useBellState(0);
  const [open, setOpen] = useBellState(false);
  const panelRef = useBellRef(null);

  const fetchNow = async () => {
    try {
      const resp = await fetch('/api/notifications', {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      setItems(data.items || []);
      setUnread(data.unread_count || 0);
    } catch (e) { /* swallow */ }
  };

  useBellEffect(() => {
    fetchNow();
    const t = setInterval(fetchNow, pollMs);
    return () => clearInterval(t);
  }, [pollMs]);

  // Close on outside click
  useBellEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const onToggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      try {
        await fetch('/api/notifications/mark-all-read', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
        });
        setUnread(0);
        const nowIso = new Date().toISOString();
        setItems(items.map(i => i.read_at ? i : { ...i, read_at: nowIso }));
      } catch (e) { /* swallow */ }
    }
  };

  const formatTime = (iso) => {
    if (!iso) return '';
    // expect 'YYYY-MM-DD HH:MM:SS' or ISO; show HH:MM
    const m = String(iso).match(/(\d{2}):(\d{2}):\d{2}/);
    return m ? `${m[1]}:${m[2]}` : '';
  };

  return (
    <div className="bell" ref={panelRef}>
      <button className="bell__btn" onClick={onToggle} aria-label="Уведомления">
        🔔
        {unread > 0 && (
          <span className="bell__badge">{unread > 99 ? '99+' : unread}</span>
        )}
      </button>
      {open && (
        <div className="bell__panel">
          {items.length === 0 ? (
            <div className="bell__empty">Уведомлений пока нет</div>
          ) : items.map(n => (
            <div
              key={n.id}
              className={`bell__item ${n.read_at ? '' : 'bell__item--unread'}`}
            >
              <div className="bell__item-text">{n.text}</div>
              <div className="bell__item-time">{formatTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

Note: token reading uses `localStorage.getItem('token')` — verify this matches how other components do auth fetches:

```bash
grep -n "localStorage.getItem\|Authorization" web/static/components/Cabinet.jsx | head -10
```

If the project uses a helper like `apiGet`/`apiPost` from a shared module, use that instead. The grep result will tell you. **If a helper exists, replace the two `fetch(...)` calls above with it before proceeding.**

- [ ] **Step 3: Add script tag to `index.html`**

In `web/static/index.html`, find the block of `<script type="text/babel" src="components/...">` tags. Add (place alphabetically or near `AppHeader.jsx`):

```html
<script type="text/babel" src="components/NotificationsBell.jsx"></script>
```

- [ ] **Step 4: Add CSS**

Append to `web/static/platform.css`:

```css
/* ===== NOTIFICATIONS BELL ===== */
.bell { position: relative; }
.bell__btn {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 50%;
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  font-size: 1rem;
  color: var(--text-1);
  position: relative;
}
.bell__btn:hover { background: var(--surface-3); }
.bell__badge {
  position: absolute;
  top: -4px; right: -4px;
  background: #e53e3e;
  color: #fff;
  font-size: 0.65rem;
  font-weight: 700;
  border-radius: 9px;
  min-width: 18px; height: 18px;
  padding: 0 5px;
  display: flex; align-items: center; justify-content: center;
  line-height: 1;
}
.bell__panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 340px;
  max-height: 420px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.18);
  z-index: 50;
  padding: 6px 0;
}
.bell__empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-3);
  font-size: 0.875rem;
}
.bell__item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 2px;
}
.bell__item:last-child { border-bottom: none; }
.bell__item--unread {
  border-left: 3px solid var(--primary);
  background: var(--surface-2);
}
.bell__item-text { font-size: 0.875rem; color: var(--text-1); line-height: 1.4; }
.bell__item-time { font-size: 0.7rem; color: var(--text-3); }

@media (max-width: 640px) {
  .bell__panel { width: 90vw; right: -8px; }
}
```

- [ ] **Step 5: Smoke check — page still loads**

```bash
docker compose -f docker-compose.yml up -d
# Wait for app to be ready (the SessionStart hook usually warms it),
# then verify:
curl -sf http://localhost:8000/ | head -3
```

Expected: HTML response. Open the page in a browser; the component file should be fetched (Network tab shows 200 on `components/NotificationsBell.jsx`).

- [ ] **Step 6: Commit**

```bash
git add web/static/components/NotificationsBell.jsx web/static/index.html web/static/platform.css
git commit -m "feat(web): add NotificationsBell component skeleton"
```

---

## Task 12: Mount bell in `AppHeader`

**Files:**
- Modify: `web/static/components/AppHeader.jsx`

- [ ] **Step 1: Inspect AppHeader actions area**

```bash
sed -n '115,160p' web/static/components/AppHeader.jsx
```

Locate the `header__actions` block (after `header__spacer`).

- [ ] **Step 2: Add the bell**

Inside `header__actions`, before the balance/user-dropdown block, render the bell when `user && !adminMode`:

```jsx
{user && !adminMode && <NotificationsBell />}
```

The exact insertion point is in the JSX returned by `AppHeader`, inside `<div className="header__actions">`.

- [ ] **Step 3: Visual smoke**

Reload the app in browser as an authenticated non-admin user. Bell icon appears in the header. Clicking it opens an empty panel (`Уведомлений пока нет`) since no notifications exist yet for this user.

- [ ] **Step 4: Commit**

```bash
git add web/static/components/AppHeader.jsx
git commit -m "feat(web): mount NotificationsBell in AppHeader"
```

---

## Task 13: End-to-end smoke + spec cross-check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
docker compose -f docker-compose.yml exec -T app pytest tests/unit -v
```

Expected: all PASS.

- [ ] **Step 2: Manual TC-1 (Posted → bell + TG)**

Working from spec section 10 (manual tests). Pre-req: dev compose up, admin token in browser, test user `@yamagruh` (tg_id=7050873595) with an existing `Pending` order.

- In admin web UI, change a `@yamagruh` order from `Pending` → `Posted`.
- In Telegram, `@yamagruh` receives `📌 Заказ №N размещён.` + `🏠 Главное меню` button.
- Click the button → main menu appears.
- In `@yamagruh`'s LK, bell shows `1` within 30s. Open panel → see the entry with unread accent. Bell badge clears.
- Reload LK → no badge, entry without accent.

- [ ] **Step 3: Manual TC-3 (idempotency)**

- Repeat the status set with the same value → no new TG message, no new DB row (`SELECT COUNT(*) FROM notifications WHERE user_id = <yamagruh_id>` unchanged).

- [ ] **Step 4: Manual TC-6 (TG fail, LK still works)**

- Have `@yamagruh` `/stop` the bot.
- Change another order status from admin web.
- TG silent. LK bell still receives the entry within 30s. Server logs show `TG notify failed` exception.

- [ ] **Step 5: Manual TC-7a (review close)**

- Create a `reviews` order for `@yamagruh` via the `/reviews` flow.
- As admin in TG: `/admin → reviews_man → close → enter ID`.
- `@yamagruh` receives `🎉 Заказ №N на отзыв (<service>) выполнен.` (NOT the old `<b>🎉 Ваш заказ номер ...</b>` legacy text).
- Bell increments in LK.

- [ ] **Step 6: Spec coverage walkthrough**

Open `docs/superpowers/specs/2026-05-22-order-status-notifications-design.md` side-by-side. For each numbered section, confirm a corresponding task above implements it. List any uncovered requirement; if found, add a follow-up task.

- [ ] **Step 7: Commit (if any docs/notes need updating)**

If manual testing surfaced spec inaccuracies or missing edge cases, fix them inline in the spec, then:

```bash
git add docs/superpowers/specs/2026-05-22-order-status-notifications-design.md
git commit -m "docs: clarifications from manual testing"
```

If everything matched, no commit needed — just confirm and proceed.

---

## Spec coverage map

| Spec section | Implementing task(s) |
|---|---|
| 1. Цель | All |
| 2. Скоуп — kinds & statuses | Tasks 2, 4 (templates whitelist) |
| 2. No-op suppression | Tasks 4, 7 |
| 3. Архитектура — new files | Tasks 2, 6, 11 |
| 3. Architecture — edits | Tasks 7, 8, 9, 10, 12 |
| 4. Схема БД | Task 1 |
| 5. Сервис — `_build_text` | Task 2 |
| 5. Сервис — write path | Tasks 3, 4, 7 |
| 6. HTTP API | Tasks 5, 6 |
| 7. Callsite-ы | Tasks 7, 8, 9 |
| 8. UI колокольчика | Tasks 11, 12 |
| 9. Обработка ошибок | Task 4 (covered by tests) |
| 10. Тестирование — unit | Tasks 1, 2, 3, 4 |
| 10. Тестирование — integration | Tasks 6, 7 |
| 10. Тестирование — manual | Task 13 |
| 11. Уборка легаси | Tasks 8 (admin_orders), 9 (admin_reviews), 10 (In progress) |
| 12. Не входит в скоуп | (intentionally not implemented) |
