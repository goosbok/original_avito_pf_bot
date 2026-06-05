# Web Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full web cabinet UI — dashboard with Services/Orders/Support sections, a Avito-PF order form, a paginated orders page, and a TG-relay support chat.

**Architecture:** FastAPI backend with new `/api/orders` and `/api/support` routers backed by SQLite via the existing `services/db.py` connect pattern. Frontend is vanilla JS/HTML following the existing `cabinet.html` style. The aiogram bot runs in the same process so web code can `await bot.send_message(...)` and existing `send_admins()` directly.

**Tech Stack:** FastAPI, Pydantic v2, aiogram 2.x (same process), SQLite, vanilla HTML/JS (no framework), pytest + FastAPI TestClient.

---

## File Structure

### New files
| Path | Responsibility |
|---|---|
| `services/orders.py` | PF order creation, paginated list, price lookup |
| `services/support.py` | Support-message CRUD (thin wrapper over sqlite3 helpers) |
| `web/routers/orders.py` | `GET /api/orders/pf/price`, `GET /api/orders`, `POST /api/orders/pf` |
| `web/routers/support.py` | `POST /api/support/messages`, `GET /api/support/messages` |
| `handlers/support_web.py` | aiogram handler: admin TG reply → support reply saved to DB |
| `web/static/pf-order.html` | Avito PF order form (all fields on one screen) |
| `web/static/orders.html` | Paginated order history |
| `tests/web/test_routers_orders.py` | API tests for orders router |
| `tests/web/test_routers_support.py` | API tests for support router |

### Modified files
| Path | Change |
|---|---|
| `utils/sqlite3.py` | Add `support_messages` table to schema; add `user_orders_paginated`, `user_orders_count`, `support_add_message`, `support_get_messages`, `support_find_by_tg_message_id` |
| `web/schemas.py` | Add `PFOrderRequest`, `PFOrderResponse`, `PFPriceResponse`, `OrderItem`, `OrderListResponse`, `SupportMessageCreate`, `SupportMessageItem` |
| `web/main.py` | Include `orders_router`, `support_router` |
| `handlers/__init__.py` | Import `support_web` |
| `web/static/cabinet.html` | Rewrite as dashboard: Services block, Recent Orders block (last 20), Support chat |

---

## Task 1 — DB: support_messages table + query helpers

**Files:**
- Modify: `utils/sqlite3.py`

- [ ] **Step 1.1: Add `support_messages` to `get_schema_statements()`**

Find the return list in `get_schema_statements()` and append the new entry **before** the closing `]`. Insert it right after the last existing tuple (after `seo` or wherever the list ends):

```python
        (
            "support_messages",
            "CREATE TABLE support_messages("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "direction TEXT NOT NULL,"
            "text TEXT NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "tg_message_id INTEGER,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            6,
        ),
```

- [ ] **Step 1.2: Add helper functions to `utils/sqlite3.py`**

Append to the bottom of the file (before any `if __name__` block if one exists, otherwise at the very end):

```python
def user_orders_paginated(user_id, limit=20, offset=0):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY increment DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()


def user_orders_count(user_id):
    with sqlite3.connect(path_db) as con:
        result = con.execute(
            "SELECT COUNT(*) as cnt FROM orders WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return (result["cnt"] if result else 0)


def support_add_message(user_id, direction, text, tg_message_id=None):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        cur = con.execute(
            "INSERT INTO support_messages(user_id, direction, text, created_at, tg_message_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, direction, text, get_date(), tg_message_id),
        )
        con.commit()
        return cur.lastrowid


def support_get_messages(user_id, limit=100):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM support_messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def support_find_by_tg_message_id(tg_message_id):
    with sqlite3.connect(path_db) as con:
        con.row_factory = dict_factory
        return con.execute(
            "SELECT * FROM support_messages WHERE tg_message_id = ?",
            (tg_message_id,),
        ).fetchone()
```

- [ ] **Step 1.3: Verify schema is recognised by conftest**

```bash
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot
python -c "from utils.sqlite3 import get_schema_statements; tables=[t for t,_,_ in get_schema_statements()]; assert 'support_messages' in tables, tables; print('OK', tables)"
```
Expected: `OK ['users', 'refills', 'orders', ..., 'support_messages', ...]`

- [ ] **Step 1.4: Commit**

```bash
git add utils/sqlite3.py
git commit -m "feat: add support_messages table + order/support query helpers"
```

---

## Task 2 — Schemas

**Files:**
- Modify: `web/schemas.py`

- [ ] **Step 2.1: Add new Pydantic models**

Append to `web/schemas.py`:

```python
import re as _re


class PFPriceResponse(BaseModel):
    price_per_unit: int


class PFOrderRequest(BaseModel):
    links: list[str] = Field(min_length=1)
    days: int = Field(gt=0)
    fix_count: int = Field(ge=5)
    contacts: bool

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v: list[str]) -> list[str]:
        for link in v:
            if not _re.search(r'avito\.ru', link):
                raise ValueError(f"invalid avito link: {link}")
        return v


class PFOrderResponse(BaseModel):
    order_id: int
    total_price: int
    status: str


class OrderItem(BaseModel):
    order_id: int
    price: int
    position_name: str
    status: str
    links: str
    date: str
    contacts: bool


class OrderListResponse(BaseModel):
    items: list[OrderItem]
    total: int
    page: int
    page_size: int


class SupportMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class SupportMessageItem(BaseModel):
    id: int
    direction: str
    text: str
    created_at: str
```

You also need to add `field_validator` to the pydantic import at the top of `web/schemas.py`:

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
```

- [ ] **Step 2.2: Verify import**

```bash
python -c "from web.schemas import PFOrderRequest, OrderListResponse, SupportMessageItem; print('OK')"
```
Expected: `OK`

- [ ] **Step 2.3: Commit**

```bash
git add web/schemas.py
git commit -m "feat: add web schemas for orders and support"
```

---

## Task 3 — Service: orders

**Files:**
- Create: `services/orders.py`

- [ ] **Step 3.1: Create `services/orders.py`**

```python
"""Business logic for order creation and listing."""
from __future__ import annotations

from dataclasses import dataclass

from services.db import connect
from services.exceptions import UserNotFound
from utils.sqlite3 import (
    add_order,
    get_price,
    get_users_last_order,
    user_orders_count,
    user_orders_paginated,
)


class InsufficientBalance(Exception):
    pass


@dataclass
class PFOrderResult:
    order_id: int
    total_price: int
    status: str


def get_pf_price_per_unit() -> int:
    raw = get_price("price_avito_pf")
    return int(raw) if raw is not None else 1


def create_pf_order(
    user_id: int,
    links: list[str],
    days: int,
    fix_count: int,
    contacts: bool,
) -> PFOrderResult:
    price_per_unit = get_pf_price_per_unit()
    total = price_per_unit * fix_count * days * len(links)

    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")

    balance = int(row["balance"] or 0)
    if balance < total:
        raise InsufficientBalance(f"need {total}, have {balance}")

    with connect() as con:
        con.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (balance - total, user_id),
        )
        con.commit()

    add_order(
        user_id=user_id,
        price=total,
        position_name=f"{days}/{fix_count}",
        status="Posted",
        links=str(links),
        contacts=contacts,
        user_name=row["user_name"],
    )

    order = get_users_last_order(user_id)
    return PFOrderResult(order_id=order["increment"], total_price=total, status="Posted")


def list_orders(user_id: int, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    items = user_orders_paginated(user_id, limit=page_size, offset=offset)
    total = user_orders_count(user_id)
    return items, total
```

- [ ] **Step 3.2: Verify import**

```bash
python -c "from services.orders import get_pf_price_per_unit, create_pf_order, list_orders; print('OK')"
```
Expected: `OK`

- [ ] **Step 3.3: Commit**

```bash
git add services/orders.py
git commit -m "feat: add services/orders.py with PF order creation and listing"
```

---

## Task 4 — Service: support

**Files:**
- Create: `services/support.py`

- [ ] **Step 4.1: Create `services/support.py`**

```python
"""Support-message CRUD for web chat relay."""
from __future__ import annotations

from utils.sqlite3 import (
    support_add_message,
    support_find_by_tg_message_id,
    support_get_messages,
)


def create_user_message(user_id: int, text: str) -> int:
    """Save a user question. Returns new row id."""
    return support_add_message(user_id, "user", text)


def create_admin_reply(user_id: int, text: str, tg_message_id: int | None = None) -> int:
    """Save admin reply for a user. Returns new row id."""
    return support_add_message(user_id, "admin", text, tg_message_id)


def get_conversation(user_id: int) -> list[dict]:
    return support_get_messages(user_id)


def find_message_by_tg_id(tg_message_id: int) -> dict | None:
    return support_find_by_tg_message_id(tg_message_id)
```

- [ ] **Step 4.2: Verify import**

```bash
python -c "from services.support import create_user_message, get_conversation; print('OK')"
```
Expected: `OK`

- [ ] **Step 4.3: Commit**

```bash
git add services/support.py
git commit -m "feat: add services/support.py with support message CRUD"
```

---

## Task 5 — Tests: orders router

**Files:**
- Create: `tests/web/test_routers_orders.py`

- [ ] **Step 5.1: Write failing tests**

```python
"""Tests for /api/orders and /api/orders/pf endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("user@example.com", "password123", first_name="User")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    client = TestClient(app)
    return client, uid, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_with_balance(authed, tmp_db):
    client, uid, headers = authed
    from services.db import connect
    with connect() as con:
        con.execute("UPDATE users SET balance = 10000 WHERE id = ?", (uid,))
        con.commit()
    return client, uid, headers


def test_get_pf_price_no_auth(authed):
    client, _, _ = authed
    r = client.get("/api/orders/pf/price")
    assert r.status_code == 200
    body = r.json()
    assert "price_per_unit" in body
    assert isinstance(body["price_per_unit"], int)
    assert body["price_per_unit"] >= 1


def test_list_orders_empty(authed):
    client, _, headers = authed
    r = client.get("/api/orders", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


def test_list_orders_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/orders")
    assert r.status_code == 401


def test_create_pf_order_success(authed_with_balance, monkeypatch):
    client, uid, headers = authed_with_balance
    # Stub price so test is deterministic: price_per_unit=1
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)
    # Stub notifications to avoid real bot calls
    import asyncio

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/123"],
        "days": 3,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["order_id"] > 0
    assert body["total_price"] == 1 * 5 * 3 * 1  # price*fix*days*link_count
    assert body["status"] == "Posted"


def test_create_pf_order_insufficient_balance(authed, monkeypatch):
    client, _, headers = authed
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 9999999)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/123"],
        "days": 1,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 402


def test_create_pf_order_invalid_link(authed_with_balance):
    client, _, headers = authed_with_balance
    r = client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.example.com/not-avito"],
        "days": 1,
        "fix_count": 5,
        "contacts": False,
    })
    assert r.status_code == 422


def test_list_orders_after_create(authed_with_balance, monkeypatch):
    client, uid, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    client.post("/api/orders/pf", headers=headers, json={
        "links": ["https://www.avito.ru/item/1", "https://www.avito.ru/item/2"],
        "days": 2,
        "fix_count": 5,
        "contacts": True,
    })

    r = client.get("/api/orders", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["price"] == 1 * 5 * 2 * 2


def test_list_orders_pagination(authed_with_balance, monkeypatch):
    client, _, headers = authed_with_balance
    monkeypatch.setattr("services.orders.get_pf_price_per_unit", lambda: 1)

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.orders._notify_new_order", _noop)

    for _ in range(5):
        client.post("/api/orders/pf", headers=headers, json={
            "links": ["https://www.avito.ru/item/1"],
            "days": 1,
            "fix_count": 5,
            "contacts": False,
        })

    r = client.get("/api/orders?page=1&page_size=3", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["page"] == 1

    r2 = client.get("/api/orders?page=2&page_size=3", headers=headers)
    body2 = r2.json()
    assert len(body2["items"]) == 2
```

- [ ] **Step 5.2: Run tests — expect FAIL (routers don't exist yet)**

```bash
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot
python -m pytest tests/web/test_routers_orders.py -v 2>&1 | tail -20
```
Expected: multiple `FAILED` or `ERROR` lines (ImportError for missing modules).

- [ ] **Step 5.3: Commit tests**

```bash
git add tests/web/test_routers_orders.py
git commit -m "test: add failing tests for orders router"
```

---

## Task 6 — Router: orders

**Files:**
- Create: `web/routers/orders.py`

- [ ] **Step 6.1: Create `web/routers/orders.py`**

```python
"""Orders API router.

GET  /api/orders/pf/price  — public: current price per unit
GET  /api/orders            — paginated order history for current user
POST /api/orders/pf         — create Avito PF order, deduct balance, notify
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from services import orders as orders_svc
from services.exceptions import UserNotFound
from services.orders import InsufficientBalance
from web.deps import require_user
from web.schemas import (
    OrderItem,
    OrderListResponse,
    PFOrderRequest,
    PFOrderResponse,
    PFPriceResponse,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/pf/price", response_model=PFPriceResponse)
async def get_pf_price() -> PFPriceResponse:
    return PFPriceResponse(price_per_unit=orders_svc.get_pf_price_per_unit())


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 20,
    user_id: int = Depends(require_user),
) -> OrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    items, total = orders_svc.list_orders(user_id, page=page, page_size=page_size)
    return OrderListResponse(
        items=[
            OrderItem(
                order_id=o["increment"],
                price=int(o["price"] or 0),
                position_name=str(o["position_name"] or ""),
                status=str(o["status"] or ""),
                links=str(o["links"] or ""),
                date=str(o["date"] or ""),
                contacts=bool(o["contacts"]),
            )
            for o in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/pf", response_model=PFOrderResponse, status_code=201)
async def create_pf_order(
    body: PFOrderRequest,
    user_id: int = Depends(require_user),
) -> PFOrderResponse:
    try:
        result = orders_svc.create_pf_order(
            user_id=user_id,
            links=body.links,
            days=body.days,
            fix_count=body.fix_count,
            contacts=body.contacts,
        )
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientBalance as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    asyncio.create_task(_notify_new_order(user_id, result.order_id, result.total_price))

    return PFOrderResponse(
        order_id=result.order_id,
        total_price=result.total_price,
        status=result.status,
    )


async def _notify_new_order(user_id: int, order_id: int, total_price: int) -> None:
    try:
        from data.loader import bot
        from utils.other import format_decimal
        from utils.sender import send_admins
        from utils.sqlite3 import get_tg_id_for_user, get_users_last_order

        order = get_users_last_order(user_id)
        if order is None:
            return

        f_price = format_decimal(total_price)
        links_str = ""
        for link in str(order["links"] or "").split(","):
            link = link.strip().strip("'\"[]")
            if link:
                links_str += f"\n<code>{link}</code>"

        adm_msg = (
            f"🌐 <b>Новый заказ #{order['increment']} (веб)</b>\n"
            f"Цена: {f_price} ₽\n"
            f"Параметры: {order['position_name']}\n"
            f"Контакты: {'Да' if order['contacts'] else 'Нет'}\n"
            f"Ссылки:{links_str}"
        )
        await send_admins(adm_msg)

        tg_id = get_tg_id_for_user(user_id)
        if tg_id:
            await bot.send_message(
                chat_id=tg_id,
                text=f"✅ Заказ #{order['increment']} принят. Сумма: {f_price} ₽",
            )
    except Exception:
        pass
```

- [ ] **Step 6.2: Register router in `web/main.py`**

Add after the existing router includes in `web/main.py`:

```python
from web.routers.orders import router as orders_router  # noqa: E402

app.include_router(orders_router)
```

- [ ] **Step 6.3: Run tests — expect PASS**

```bash
python -m pytest tests/web/test_routers_orders.py -v 2>&1 | tail -25
```
Expected: all tests PASSED.

- [ ] **Step 6.4: Commit**

```bash
git add web/routers/orders.py web/main.py
git commit -m "feat: add /api/orders router with PF order creation and pagination"
```

---

## Task 7 — Tests: support router

**Files:**
- Create: `tests/web/test_routers_support.py`

- [ ] **Step 7.1: Write failing tests**

```python
"""Tests for /api/support/messages endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed(tmp_db: Path, monkeypatch):
    monkeypatch.setattr("web.config.JWT_SECRET", "x" * 32)
    monkeypatch.setattr("web.auth.JWT_SECRET", "x" * 32)
    from services import auth_email
    uid = auth_email.register("user@example.com", "password123", first_name="User")
    from web.auth import create_jwt
    token = create_jwt(uid)
    from web.main import app
    client = TestClient(app)
    return client, uid, {"Authorization": f"Bearer {token}"}


def test_get_messages_empty(authed):
    client, _, headers = authed
    r = client.get("/api/support/messages", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_messages_requires_auth(authed):
    client, _, _ = authed
    r = client.get("/api/support/messages")
    assert r.status_code == 401


def test_send_message_success(authed, monkeypatch):
    client, _, headers = authed

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.support._forward_to_admins", _noop)

    r = client.post("/api/support/messages", headers=headers,
                    json={"text": "Hello support, I have a question"})
    assert r.status_code == 204


def test_send_message_requires_auth(authed):
    client, _, _ = authed
    r = client.post("/api/support/messages", json={"text": "hello"})
    assert r.status_code == 401


def test_send_message_empty_text_rejected(authed, monkeypatch):
    client, _, headers = authed
    r = client.post("/api/support/messages", headers=headers, json={"text": ""})
    assert r.status_code == 422


def test_messages_appear_after_send(authed, monkeypatch):
    client, uid, headers = authed

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.support._forward_to_admins", _noop)

    client.post("/api/support/messages", headers=headers, json={"text": "My question"})

    r = client.get("/api/support/messages", headers=headers)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 1
    assert msgs[0]["direction"] == "user"
    assert msgs[0]["text"] == "My question"
    assert "created_at" in msgs[0]


def test_admin_reply_visible_to_user(authed, tmp_db):
    client, uid, headers = authed
    from services.support import create_admin_reply
    create_admin_reply(uid, "Hello, this is support answering")

    r = client.get("/api/support/messages", headers=headers)
    msgs = r.json()
    assert any(m["direction"] == "admin" and "support answering" in m["text"] for m in msgs)
```

- [ ] **Step 7.2: Run tests — expect FAIL**

```bash
python -m pytest tests/web/test_routers_support.py -v 2>&1 | tail -15
```
Expected: multiple FAILED/ERROR.

- [ ] **Step 7.3: Commit tests**

```bash
git add tests/web/test_routers_support.py
git commit -m "test: add failing tests for support router"
```

---

## Task 8 — Router: support

**Files:**
- Create: `web/routers/support.py`

- [ ] **Step 8.1: Create `web/routers/support.py`**

```python
"""Support chat API.

POST /api/support/messages  — user sends question → relayed to admins via bot
GET  /api/support/messages  — full conversation history for current user
"""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends

from services import support as support_svc
from web.deps import require_user
from web.schemas import SupportMessageCreate, SupportMessageItem

router = APIRouter(prefix="/api/support", tags=["support"])

_SUPPORT_TAG = "Вопрос из веб"


@router.get("/messages", response_model=list[SupportMessageItem])
async def get_messages(user_id: int = Depends(require_user)) -> list[SupportMessageItem]:
    msgs = support_svc.get_conversation(user_id)
    return [
        SupportMessageItem(
            id=m["id"],
            direction=m["direction"],
            text=m["text"],
            created_at=str(m["created_at"] or ""),
        )
        for m in msgs
    ]


@router.post("/messages", status_code=204, response_model=None)
async def send_message(
    body: SupportMessageCreate,
    user_id: int = Depends(require_user),
) -> None:
    msg_id = support_svc.create_user_message(user_id, body.text)
    asyncio.create_task(_forward_to_admins(user_id, msg_id, body.text))


async def _forward_to_admins(user_id: int, msg_id: int, text: str) -> None:
    try:
        from data.loader import bot
        from services import identity
        from services.db import connect as db_connect
        from utils.sqlite3 import get_admins, get_spam_exclude, get_tg_id_for_user

        try:
            u = identity.get_user(user_id)
            user_str = f"@{u.user_name}" if u.user_name else f"ID {user_id}"
        except Exception:
            user_str = f"ID {user_id}"

        fwd_text = (
            f"💬 <b>{_SUPPORT_TAG} #{msg_id}</b>\n"
            f"От: {user_str}\n\n{text}"
        )

        first_tg_msg_id = None
        for admin in get_admins():
            if admin in get_spam_exclude():
                continue
            tg_id = get_tg_id_for_user(int(admin)) or int(admin)
            try:
                sent = await bot.send_message(chat_id=tg_id, text=fwd_text, parse_mode="HTML")
                if first_tg_msg_id is None:
                    first_tg_msg_id = sent.message_id
            except Exception:
                pass

        if first_tg_msg_id is not None:
            with db_connect() as con:
                con.execute(
                    "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
                    (first_tg_msg_id, msg_id),
                )
                con.commit()
    except Exception:
        pass
```

- [ ] **Step 8.2: Register router in `web/main.py`**

Add after the existing includes:

```python
from web.routers.support import router as support_router  # noqa: E402

app.include_router(support_router)
```

- [ ] **Step 8.3: Run tests — expect PASS**

```bash
python -m pytest tests/web/test_routers_support.py -v 2>&1 | tail -15
```
Expected: all PASSED.

- [ ] **Step 8.4: Run full test suite — no regressions**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```
Expected: all existing tests still PASSED.

- [ ] **Step 8.5: Commit**

```bash
git add web/routers/support.py web/main.py
git commit -m "feat: add /api/support/messages router with TG relay"
```

---

## Task 9 — Bot handler: admin TG replies

**Files:**
- Create: `handlers/support_web.py`
- Modify: `handlers/__init__.py`

- [ ] **Step 9.1: Create `handlers/support_web.py`**

The handler matches admin replies to messages that contain the `"Вопрос из веб #N"` pattern in the replied-to text. It saves the reply to DB and optionally notifies the user in TG.

```python
"""Bot handler: admin reply to a web support message → stored in support_messages."""
from __future__ import annotations

import logging
import re

from aiogram.types import Message

from data.loader import dp

logger = logging.getLogger(__name__)

_SUPPORT_PATTERN = re.compile(r"Вопрос из веб #(\d+)")


@dp.message_handler(
    lambda m: m.reply_to_message is not None and m.reply_to_message.text is not None,
    content_types=["text"],
    state="*",
)
async def admin_reply_to_support(message: Message) -> None:
    from utils.sqlite3 import get_admins

    admins = [str(a) for a in get_admins()]
    if str(message.from_user.id) not in admins:
        return

    replied_text = message.reply_to_message.text or ""
    match = _SUPPORT_PATTERN.search(replied_text)
    if match is None:
        return

    msg_id = int(match.group(1))

    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM support_messages WHERE id = ?",
            (msg_id,),
        ).fetchone()

    if row is None:
        logger.warning("support reply: msg_id=%s not found in DB", msg_id)
        return

    user_id = row["user_id"]

    from services.support import create_admin_reply
    create_admin_reply(user_id, message.text)

    from utils.sqlite3 import get_tg_id_for_user
    tg_id = get_tg_id_for_user(user_id)
    if tg_id:
        try:
            await message.bot.send_message(
                chat_id=tg_id,
                text=f"💬 Ответ поддержки:\n{message.text}",
            )
        except Exception:
            logger.warning("could not notify user_id=%s in TG", user_id)

    await message.reply("✅ Ответ сохранён")
    logger.info("support reply saved for user_id=%s, msg_id=%s", user_id, msg_id)
```

- [ ] **Step 9.2: Register in `handlers/__init__.py`**

Open `handlers/__init__.py`. The current content is:

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, seo, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings,
    commands,  # commands.py has unhandled_callback LAST
)
```

Change it to (add `support_web` before `commands`):

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, seo, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings,
    support_web,
    commands,  # commands.py has unhandled_callback LAST
)
```

- [ ] **Step 9.3: Verify import doesn't break bot startup**

```bash
python -c "from handlers import support_web; print('OK')"
```
Expected: `OK` (no errors, though aiogram will warn about fake token — that's fine).

- [ ] **Step 9.4: Commit**

```bash
git add handlers/support_web.py handlers/__init__.py
git commit -m "feat: bot handler for admin support replies via TG"
```

---

## Task 10 — Frontend: dashboard (cabinet.html)

**Files:**
- Modify: `web/static/cabinet.html`

- [ ] **Step 10.1: Rewrite `web/static/cabinet.html`**

Replace the entire file with the dashboard layout. The dashboard has four sections:
1. Profile header (name, balance)
2. Services block (one card: Авито ПФ)
3. Recent orders (last 20, table, "All orders" button)
4. Support chat (message history + text input)

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Личный кабинет</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f4f6f8; color: #1a1a1a; }
    .header { background: #fff; border-bottom: 1px solid #e0e0e0; padding: 14px 24px;
              display: flex; align-items: center; justify-content: space-between; }
    .header h1 { margin: 0; font-size: 20px; }
    .header-right { display: flex; align-items: center; gap: 16px; font-size: 14px; }
    .badge { background: #e8f4fd; color: #0077cc; border-radius: 20px;
             padding: 4px 12px; font-weight: 600; }
    a.logout { color: #888; text-decoration: none; font-size: 13px; }
    a.logout:hover { color: #c00; }
    .main { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
    .section-title { font-size: 16px; font-weight: 700; margin: 0 0 12px; }
    .card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px;
            padding: 20px; margin-bottom: 20px; }
    /* Services */
    .services-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
    .service-card { border: 1px solid #cce4f7; border-radius: 8px; padding: 16px;
                    text-decoration: none; color: inherit; display: block;
                    transition: background .15s; }
    .service-card:hover { background: #f0f8ff; }
    .service-card .sc-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
    .service-card .sc-desc { font-size: 13px; color: #666; }
    /* Orders table */
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 8px 10px; border-bottom: 2px solid #e0e0e0;
         color: #555; font-weight: 600; }
    td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    .status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
                    font-size: 11px; font-weight: 600; }
    .status-posted { background: #dff0d8; color: #3c763d; }
    .status-other { background: #f5f5f5; color: #555; }
    .btn { display: inline-block; padding: 8px 16px; font-size: 14px; border-radius: 6px;
           cursor: pointer; text-decoration: none; border: 1px solid #ccc;
           background: #fff; color: #333; }
    .btn:hover { background: #f0f0f0; }
    .btn.primary { background: #0088cc; color: #fff; border-color: #0088cc; }
    .btn.primary:hover { background: #006fa8; }
    .btn:disabled { opacity: .5; cursor: default; }
    /* Support */
    .chat-box { border: 1px solid #e0e0e0; border-radius: 8px; height: 280px;
                overflow-y: auto; padding: 12px; background: #fafafa;
                display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
    .msg { max-width: 80%; padding: 8px 12px; border-radius: 8px; font-size: 14px;
           line-height: 1.4; word-break: break-word; }
    .msg.user { align-self: flex-end; background: #dcf8c6; }
    .msg.admin { align-self: flex-start; background: #fff; border: 1px solid #e0e0e0; }
    .msg-meta { font-size: 11px; color: #aaa; margin-top: 3px; }
    .chat-input-row { display: flex; gap: 8px; }
    textarea.chat-input { flex: 1; padding: 8px 10px; font-size: 14px; resize: vertical;
                          border: 1px solid #ccc; border-radius: 6px; min-height: 60px;
                          font-family: inherit; }
    .err { color: #c00; font-size: 13px; margin-top: 6px; }
    .empty-state { color: #aaa; font-size: 13px; text-align: center; padding: 20px 0; }
  </style>
</head>
<body>

<div class="header">
  <h1>Личный кабинет</h1>
  <div class="header-right">
    <span id="profile-name">…</span>
    <span class="badge" id="profile-balance">…</span>
    <a href="index.html" class="logout" id="logout">Выйти</a>
  </div>
</div>

<div class="main">

  <!-- Services -->
  <div class="card">
    <div class="section-title">Сервисы</div>
    <div class="services-grid">
      <a href="pf-order.html" class="service-card">
        <div class="sc-title">📈 Авито ПФ</div>
        <div class="sc-desc">Накрутка поведенческих факторов для объявлений</div>
      </a>
    </div>
  </div>

  <!-- Recent Orders -->
  <div class="card">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
      <div class="section-title" style="margin:0;">Последние заказы</div>
      <a href="orders.html" class="btn" style="font-size:13px;">Все заказы →</a>
    </div>
    <div id="orders-container">
      <div class="empty-state">Загрузка…</div>
    </div>
  </div>

  <!-- Support Chat -->
  <div class="card">
    <div class="section-title">Написать в поддержку</div>
    <div class="chat-box" id="chat-box">
      <div class="empty-state" id="chat-empty">Нет сообщений. Задайте вопрос.</div>
    </div>
    <div class="chat-input-row">
      <textarea class="chat-input" id="chat-input" placeholder="Ваш вопрос…" rows="3"></textarea>
      <button class="btn primary" id="chat-send" style="align-self:flex-end;">Отправить</button>
    </div>
    <div id="chat-err" class="err"></div>
  </div>

  <!-- Account Settings (collapsible) -->
  <details>
    <summary style="cursor:pointer; font-size:14px; color:#555; margin-bottom:12px;">
      ⚙️ Настройки аккаунта
    </summary>

    <div class="card">
      <div class="section-title">Способы входа</div>
      <div id="providers-list">Загрузка…</div>
      <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn" id="link-email-btn">+ Привязать Email</button>
        <button class="btn" id="link-tg-btn">+ Привязать Telegram</button>
      </div>
      <div id="providers-err" class="err"></div>
    </div>

    <div class="card">
      <div class="section-title">API-приложения</div>
      <div id="apps-list">Загрузка…</div>
      <div style="margin-top:12px;">
        <button class="btn primary" id="create-app-btn">Создать приложение</button>
      </div>
      <div id="apps-err" class="err"></div>
      <div id="new-api-key-box" style="display:none; margin-top:12px;">
        <b>Ваш API-ключ (показывается один раз):</b>
        <div id="new-api-key" style="background:#f5f5f5;border:1px solid #ccc;border-radius:4px;
             padding:6px 10px;font-family:monospace;font-size:13px;word-break:break-all;margin-top:6px;"></div>
        <button class="btn" id="copy-key-btn" style="margin-top:8px;">Скопировать</button>
      </div>
    </div>
  </details>

</div><!-- .main -->

<!-- Link-provider modal (reused from original cabinet.html) -->
<div id="link-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.4);
     align-items:center; justify-content:center; z-index:100;">
  <div style="background:#fff; border-radius:10px; padding:24px; max-width:360px; width:90%;">
    <h3 id="link-modal-title" style="margin:0 0 16px;">Привязать</h3>
    <div id="link-modal-step1">
      <input id="link-modal-input" type="text" placeholder=""
             style="display:block;width:100%;padding:8px;font-size:15px;margin-bottom:12px;
                    border:1px solid #ccc;border-radius:6px;">
      <div id="link-modal-err" class="err"></div>
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:8px;">
        <button class="btn" id="link-modal-cancel">Отмена</button>
        <button class="btn primary" id="link-modal-next">Далее</button>
      </div>
    </div>
    <div id="link-modal-step2" style="display:none;">
      <p id="link-modal-step2-hint" style="font-size:14px;color:#555;margin:0 0 12px;"></p>
      <input id="link-modal-code" type="text" placeholder="Код" maxlength="10"
             style="display:block;width:100%;padding:8px;font-size:15px;margin-bottom:12px;
                    border:1px solid #ccc;border-radius:6px;">
      <div id="link-modal-err2" class="err"></div>
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:8px;">
        <button class="btn" id="link-modal-cancel2">Отмена</button>
        <button class="btn primary" id="link-modal-confirm">Подтвердить</button>
      </div>
    </div>
  </div>
</div>

<script>
/* ── auth guard ── */
const token = localStorage.getItem("access_token");
if (!token) { window.location.href = "/index.html"; }

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (token) opts.headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (r.status === 401) { localStorage.removeItem("access_token"); window.location.href = "/index.html"; }
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.status === 204 ? null : await r.json();
}

/* ── profile ── */
async function loadProfile() {
  try {
    const p = await api("GET", "/api/me");
    document.getElementById("profile-name").textContent = p.first_name || p.user_name || "—";
    document.getElementById("profile-balance").textContent = `${p.balance} ₽`;
  } catch (_) {}
}

/* ── recent orders ── */
async function loadRecentOrders() {
  const container = document.getElementById("orders-container");
  try {
    const data = await api("GET", "/api/orders?page=1&page_size=20");
    if (!data.items.length) {
      container.innerHTML = '<div class="empty-state">Заказов ещё нет.</div>';
      return;
    }
    const rows = data.items.map(o => {
      const statusClass = o.status === "Posted" ? "status-posted" : "status-other";
      return `<tr>
        <td>#${o.order_id}</td>
        <td>${o.date ? o.date.substring(0, 16).replace("T", " ") : "—"}</td>
        <td>${escHtml(o.position_name)}</td>
        <td>${o.price} ₽</td>
        <td><span class="status-badge ${statusClass}">${escHtml(o.status)}</span></td>
      </tr>`;
    }).join("");
    container.innerHTML = `<table>
      <thead><tr><th>#</th><th>Дата</th><th>Параметры</th><th>Сумма</th><th>Статус</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  } catch (e) {
    container.innerHTML = `<div class="err">Не удалось загрузить заказы: ${e}</div>`;
  }
}

/* ── support chat ── */
let chatMessages = [];

async function loadChat() {
  try {
    const msgs = await api("GET", "/api/support/messages");
    chatMessages = msgs;
    renderChat();
  } catch (_) {}
}

function renderChat() {
  const box = document.getElementById("chat-box");
  const empty = document.getElementById("chat-empty");
  if (!chatMessages.length) {
    box.innerHTML = '<div class="empty-state" id="chat-empty">Нет сообщений. Задайте вопрос.</div>';
    return;
  }
  empty && empty.remove();
  box.innerHTML = chatMessages.map(m => {
    const dir = m.direction === "user" ? "user" : "admin";
    const label = dir === "admin" ? "Поддержка" : "Вы";
    return `<div class="msg ${dir}">
      ${escHtml(m.text)}
      <div class="msg-meta">${label} · ${m.created_at ? m.created_at.substring(0, 16).replace("T", " ") : ""}</div>
    </div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
}

document.getElementById("chat-send").onclick = async () => {
  const input = document.getElementById("chat-input");
  const errEl = document.getElementById("chat-err");
  const text = input.value.trim();
  errEl.textContent = "";
  if (!text) return;
  const btn = document.getElementById("chat-send");
  btn.disabled = true;
  try {
    await api("POST", "/api/support/messages", { text });
    input.value = "";
    chatMessages.push({ direction: "user", text, created_at: new Date().toISOString() });
    renderChat();
  } catch (e) {
    errEl.textContent = "Ошибка: " + e;
  } finally {
    btn.disabled = false;
  }
};

/* Poll for new support replies every 15 s */
setInterval(loadChat, 15000);

/* ── providers ── */
let providersCache = [];

async function loadProviders() {
  try {
    providersCache = await api("GET", "/api/me/providers");
    renderProviders();
  } catch (e) {
    document.getElementById("providers-err").textContent = String(e);
  }
}

function renderProviders() {
  const el = document.getElementById("providers-list");
  if (!providersCache.length) { el.textContent = "Нет привязанных способов входа."; return; }
  el.innerHTML = "";
  const canDelete = providersCache.length > 1;
  for (const p of providersCache) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px;";
    const label = p.provider === "email" ? "Email" : "Telegram";
    row.innerHTML = `<span style="flex:1;font-size:14px;"><b>${label}</b>: ${escHtml(p.identifier)}</span>`;
    if (canDelete) {
      const btn = document.createElement("button");
      btn.className = "btn"; btn.style.color = "#c00"; btn.style.borderColor = "#c00";
      btn.textContent = "Удалить";
      btn.onclick = () => deleteProvider(p.provider, p.identifier, btn);
      row.appendChild(btn);
    }
    el.appendChild(row);
  }
}

async function deleteProvider(provider, identifier, btn) {
  if (!confirm(`Удалить ${provider} (${identifier})?`)) return;
  btn.disabled = true;
  try {
    await api("DELETE", `/api/auth/link/${provider}/${encodeURIComponent(identifier)}`);
    await loadProviders();
  } catch (e) {
    document.getElementById("providers-err").textContent = String(e);
    btn.disabled = false;
  }
}

/* ── link-provider modal ── */
let linkMode = "", linkIdentifier = "";

function openLinkModal(mode) {
  linkMode = mode; linkIdentifier = "";
  document.getElementById("link-modal-title").textContent =
    mode === "email" ? "Привязать Email" : "Привязать Telegram";
  document.getElementById("link-modal-input").placeholder =
    mode === "email" ? "you@example.com" : "@username или +7...";
  document.getElementById("link-modal-input").value = "";
  document.getElementById("link-modal-err").textContent = "";
  document.getElementById("link-modal-step1").style.display = "";
  document.getElementById("link-modal-step2").style.display = "none";
  document.getElementById("link-modal").style.display = "flex";
}

function closeLinkModal() {
  document.getElementById("link-modal").style.display = "none";
}

document.getElementById("link-email-btn").onclick = () => openLinkModal("email");
document.getElementById("link-tg-btn").onclick = () => openLinkModal("telegram");
document.getElementById("link-modal-cancel").onclick = closeLinkModal;
document.getElementById("link-modal-cancel2").onclick = closeLinkModal;

document.getElementById("link-modal-next").onclick = async () => {
  const btn = document.getElementById("link-modal-next");
  const errEl = document.getElementById("link-modal-err");
  errEl.textContent = "";
  const val = document.getElementById("link-modal-input").value.trim();
  if (!val) { errEl.textContent = "Заполните поле."; return; }
  linkIdentifier = val;
  btn.disabled = true;
  try {
    if (linkMode === "email") {
      document.getElementById("link-modal-step2-hint").textContent = "Введите пароль:";
      document.getElementById("link-modal-code").type = "password";
    } else {
      await api("POST", "/api/auth/link/telegram/request-code", { identifier: val });
      document.getElementById("link-modal-step2-hint").textContent = "Код отправлен в Telegram:";
      document.getElementById("link-modal-code").type = "text";
    }
    document.getElementById("link-modal-code").value = "";
    document.getElementById("link-modal-step1").style.display = "none";
    document.getElementById("link-modal-step2").style.display = "";
  } catch (e) {
    errEl.textContent = String(e);
  } finally {
    btn.disabled = false;
  }
};

document.getElementById("link-modal-confirm").onclick = async () => {
  const btn = document.getElementById("link-modal-confirm");
  const errEl = document.getElementById("link-modal-err2");
  errEl.textContent = "";
  const val = document.getElementById("link-modal-code").value.trim();
  if (!val) { errEl.textContent = "Заполните поле."; return; }
  btn.disabled = true;
  try {
    if (linkMode === "email") {
      await api("POST", "/api/auth/link/email", { email: linkIdentifier, password: val });
    } else {
      await api("POST", "/api/auth/link/telegram/verify-code", { identifier: linkIdentifier, code: val });
    }
    closeLinkModal();
    await loadProviders();
  } catch (e) {
    errEl.textContent = String(e);
    btn.disabled = false;
  }
};

/* ── applications ── */
async function loadApps() {
  const el = document.getElementById("apps-list");
  try {
    const apps = await api("GET", "/api/applications");
    if (!apps.length) { el.textContent = "Нет приложений."; return; }
    el.innerHTML = "";
    for (const app of apps) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px;";
      const revoked = app.revoked_at ? ' <span style="color:#c00">[отозван]</span>' : "";
      row.innerHTML = `<span style="flex:1;font-size:14px;"><b>${escHtml(app.name)}</b> — ключ: <code>${escHtml(app.api_key_prefix)}…</code>${revoked}</span>`;
      if (!app.revoked_at) {
        const btn = document.createElement("button");
        btn.className = "btn"; btn.style.color = "#c00"; btn.style.borderColor = "#c00";
        btn.textContent = "Удалить";
        btn.onclick = () => deleteApp(app.id, btn);
        row.appendChild(btn);
      }
      el.appendChild(row);
    }
  } catch (e) {
    document.getElementById("apps-err").textContent = String(e);
  }
}

async function deleteApp(id, btn) {
  if (!confirm("Удалить приложение и отозвать API-ключ?")) return;
  btn.disabled = true;
  try {
    await api("DELETE", `/api/applications/${id}`);
    await loadApps();
  } catch (e) {
    document.getElementById("apps-err").textContent = String(e);
    btn.disabled = false;
  }
}

document.getElementById("create-app-btn").onclick = async () => {
  const name = prompt("Название приложения:");
  if (!name) return;
  const btn = document.getElementById("create-app-btn");
  btn.disabled = true;
  try {
    const app = await api("POST", "/api/applications", { name });
    document.getElementById("new-api-key").textContent = app.api_key;
    document.getElementById("new-api-key-box").style.display = "";
    await loadApps();
  } catch (e) {
    document.getElementById("apps-err").textContent = String(e);
  } finally {
    btn.disabled = false;
  }
};

document.getElementById("copy-key-btn").onclick = () => {
  const key = document.getElementById("new-api-key").textContent;
  navigator.clipboard.writeText(key).then(() => {
    document.getElementById("copy-key-btn").textContent = "Скопировано!";
    setTimeout(() => { document.getElementById("copy-key-btn").textContent = "Скопировать"; }, 2000);
  });
};

/* ── logout ── */
document.getElementById("logout").onclick = (e) => {
  e.preventDefault();
  localStorage.removeItem("access_token");
  window.location.href = "/index.html";
};

/* ── helpers ── */
function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

/* ── init ── */
loadProfile();
loadRecentOrders();
loadChat();
loadProviders();
loadApps();
</script>
</body>
</html>
```

- [ ] **Step 10.2: Start the server and verify dashboard loads**

```bash
START_WEB=1 python __main__.py &
sleep 3
curl -s http://localhost:8000/ | grep -c "Личный кабинет" && kill %1
```
Expected: `1` (the HTML is served).

- [ ] **Step 10.3: Commit**

```bash
git add web/static/cabinet.html
git commit -m "feat: rewrite cabinet.html as dashboard with Services/Orders/Support"
```

---

## Task 11 — Frontend: PF order form

**Files:**
- Create: `web/static/pf-order.html`

- [ ] **Step 11.1: Create `web/static/pf-order.html`**

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Новый заказ — Авито ПФ</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f4f6f8; }
    .header { background: #fff; border-bottom: 1px solid #e0e0e0; padding: 14px 24px;
              display: flex; align-items: center; gap: 16px; }
    .header h1 { margin: 0; font-size: 20px; flex: 1; }
    .btn { display: inline-block; padding: 8px 16px; font-size: 14px; border-radius: 6px;
           cursor: pointer; text-decoration: none; border: 1px solid #ccc;
           background: #fff; color: #333; }
    .btn:hover { background: #f0f0f0; }
    .btn.primary { background: #0088cc; color: #fff; border-color: #0088cc; font-size: 16px;
                   width: 100%; padding: 12px; }
    .btn.primary:hover:not(:disabled) { background: #006fa8; }
    .btn:disabled { opacity: .5; cursor: default; }
    .main { max-width: 560px; margin: 0 auto; padding: 24px 16px; }
    .card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 24px; }
    .field { margin-bottom: 20px; }
    label { display: block; font-weight: 600; font-size: 14px; margin-bottom: 6px; color: #333; }
    .hint { font-size: 12px; color: #888; margin-top: 4px; }
    input[type=number], textarea {
      width: 100%; padding: 10px 12px; font-size: 15px;
      border: 1px solid #ccc; border-radius: 6px; font-family: inherit;
    }
    input[type=number]:focus, textarea:focus { outline: none; border-color: #0088cc; }
    textarea { resize: vertical; min-height: 100px; }
    .contacts-row { display: flex; gap: 12px; }
    .contacts-row label { font-weight: normal; display: flex; align-items: center;
                          gap: 6px; cursor: pointer; font-size: 15px; }
    .price-box { background: #f0f8ff; border: 1px solid #cce4f7; border-radius: 8px;
                 padding: 14px 16px; margin-bottom: 20px; font-size: 15px; }
    .price-box .price-total { font-size: 22px; font-weight: 700; color: #0077cc; }
    .err { color: #c00; font-size: 14px; margin-top: 12px; }
    .success { color: #3c763d; background: #dff0d8; border-radius: 8px;
               padding: 14px 16px; font-size: 15px; margin-top: 16px; }
    .balance-info { font-size: 13px; color: #666; margin-bottom: 16px; }
  </style>
</head>
<body>
<div class="header">
  <a href="cabinet.html" class="btn">← Назад</a>
  <h1>Авито ПФ — новый заказ</h1>
  <span class="btn" id="balance-badge" style="background:#e8f4fd;color:#0077cc;border-color:#cce4f7;">…</span>
</div>

<div class="main">
  <div class="card">
    <div class="field">
      <label for="links">Ссылки на объявления Авито</label>
      <textarea id="links" placeholder="https://www.avito.ru/...&#10;https://www.avito.ru/..." rows="5"></textarea>
      <div class="hint">Каждая ссылка с новой строки. Только avito.ru.</div>
    </div>

    <div class="field">
      <label for="days">Количество дней</label>
      <input type="number" id="days" min="1" value="7" placeholder="Дней">
      <div class="hint">Минимум 1 день.</div>
    </div>

    <div class="field">
      <label for="fix-count">Количество ПФ в день</label>
      <input type="number" id="fix-count" min="5" value="50" placeholder="Показов/день">
      <div class="hint">Минимум 5.</div>
    </div>

    <div class="field">
      <label>Добавлять контакты в объявление?</label>
      <div class="contacts-row">
        <label><input type="radio" name="contacts" value="yes"> Да</label>
        <label><input type="radio" name="contacts" value="no" checked> Нет</label>
      </div>
    </div>

    <div class="price-box">
      <div>Итого: <span class="price-total" id="price-total">—</span></div>
      <div style="font-size:12px;color:#888;margin-top:4px;" id="price-breakdown"></div>
    </div>

    <button class="btn primary" id="submit-btn" disabled>Оформить заказ</button>
    <div id="form-err" class="err"></div>
    <div id="form-success" class="success" style="display:none;"></div>
  </div>
</div>

<script>
const token = localStorage.getItem("access_token");
if (!token) { window.location.href = "/index.html"; }

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  opts.headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (r.status === 401) { localStorage.removeItem("access_token"); window.location.href = "/index.html"; }
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.status === 204 ? null : await r.json();
}

let pricePerUnit = 1;

async function init() {
  try {
    const [priceData, profile] = await Promise.all([
      api("GET", "/api/orders/pf/price"),
      api("GET", "/api/me"),
    ]);
    pricePerUnit = priceData.price_per_unit;
    document.getElementById("balance-badge").textContent = `Баланс: ${profile.balance} ₽`;
    recalcPrice();
  } catch (e) {
    document.getElementById("form-err").textContent = "Ошибка загрузки: " + e;
  }
}

function parseLinks() {
  return document.getElementById("links").value
    .split("\n")
    .map(l => l.trim())
    .filter(l => l.length > 0 && l.includes("avito.ru"));
}

function recalcPrice() {
  const days = parseInt(document.getElementById("days").value, 10) || 0;
  const fix = parseInt(document.getElementById("fix-count").value, 10) || 0;
  const links = parseLinks();
  const btn = document.getElementById("submit-btn");
  const totalEl = document.getElementById("price-total");
  const breakdownEl = document.getElementById("price-breakdown");

  if (days >= 1 && fix >= 5 && links.length >= 1) {
    const total = pricePerUnit * fix * days * links.length;
    totalEl.textContent = total + " ₽";
    breakdownEl.textContent = `${pricePerUnit} ₽/ед × ${fix} ПФ/день × ${days} дн × ${links.length} ссылок`;
    btn.disabled = false;
  } else {
    totalEl.textContent = "—";
    breakdownEl.textContent = links.length === 0 ? "Добавьте ссылки avito.ru" :
      days < 1 ? "Укажите кол-во дней" : "Минимум 5 ПФ/день";
    btn.disabled = true;
  }
}

document.getElementById("links").addEventListener("input", recalcPrice);
document.getElementById("days").addEventListener("input", recalcPrice);
document.getElementById("fix-count").addEventListener("input", recalcPrice);

document.getElementById("submit-btn").onclick = async () => {
  const btn = document.getElementById("submit-btn");
  const errEl = document.getElementById("form-err");
  const successEl = document.getElementById("form-success");
  errEl.textContent = "";
  successEl.style.display = "none";

  const links = parseLinks();
  const days = parseInt(document.getElementById("days").value, 10);
  const fixCount = parseInt(document.getElementById("fix-count").value, 10);
  const contacts = document.querySelector('input[name="contacts"]:checked').value === "yes";

  if (!links.length || days < 1 || fixCount < 5) {
    errEl.textContent = "Проверьте заполнение полей.";
    return;
  }

  btn.disabled = true;
  try {
    const result = await api("POST", "/api/orders/pf", { links, days, fix_count: fixCount, contacts });
    successEl.style.display = "";
    successEl.innerHTML = `✅ Заказ <b>#${result.order_id}</b> принят!<br>
      Списано: <b>${result.total_price} ₽</b><br>
      <a href="cabinet.html" style="color:#3c763d;">← Вернуться в кабинет</a>`;
    document.getElementById("links").value = "";
    recalcPrice();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("402")) {
      errEl.textContent = "Недостаточно средств на балансе. Пополните баланс.";
    } else {
      errEl.textContent = "Ошибка: " + msg;
    }
    btn.disabled = false;
  }
};

init();
</script>
</body>
</html>
```

- [ ] **Step 11.2: Commit**

```bash
git add web/static/pf-order.html
git commit -m "feat: add pf-order.html — Avito PF order form"
```

---

## Task 12 — Frontend: orders page

**Files:**
- Create: `web/static/orders.html`

- [ ] **Step 12.1: Create `web/static/orders.html`**

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Мои заказы</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 0; background: #f4f6f8; }
    .header { background: #fff; border-bottom: 1px solid #e0e0e0; padding: 14px 24px;
              display: flex; align-items: center; gap: 16px; }
    .header h1 { margin: 0; font-size: 20px; flex: 1; }
    .btn { display: inline-block; padding: 8px 16px; font-size: 14px; border-radius: 6px;
           cursor: pointer; text-decoration: none; border: 1px solid #ccc;
           background: #fff; color: #333; }
    .btn:hover { background: #f0f0f0; }
    .btn:disabled { opacity: .5; cursor: default; }
    .main { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
    .card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 8px 10px; border-bottom: 2px solid #e0e0e0;
         color: #555; font-weight: 600; white-space: nowrap; }
    td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    .status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
                    font-size: 11px; font-weight: 600; }
    .status-posted { background: #dff0d8; color: #3c763d; }
    .status-other { background: #f5f5f5; color: #555; }
    .links-cell { max-width: 240px; font-size: 11px; word-break: break-all; color: #555; }
    .pagination { display: flex; gap: 8px; align-items: center; margin-top: 16px; flex-wrap: wrap; }
    .page-info { font-size: 13px; color: #666; }
    .empty-state { text-align: center; color: #aaa; padding: 40px 0; font-size: 15px; }
    .err { color: #c00; font-size: 14px; }
  </style>
</head>
<body>
<div class="header">
  <a href="cabinet.html" class="btn">← Назад</a>
  <h1>Мои заказы</h1>
</div>

<div class="main">
  <div class="card">
    <div id="orders-content"><div class="empty-state">Загрузка…</div></div>
    <div class="pagination" id="pagination" style="display:none;">
      <button class="btn" id="prev-btn" disabled>← Назад</button>
      <span class="page-info" id="page-info"></span>
      <button class="btn" id="next-btn" disabled>Вперёд →</button>
    </div>
  </div>
</div>

<script>
const token = localStorage.getItem("access_token");
if (!token) { window.location.href = "/index.html"; }

async function api(method, path) {
  const r = await fetch(path, { headers: { "Authorization": `Bearer ${token}` } });
  if (r.status === 401) { localStorage.removeItem("access_token"); window.location.href = "/index.html"; }
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

const PAGE_SIZE = 20;
let currentPage = 1;
let totalItems = 0;

async function loadOrders(page) {
  const content = document.getElementById("orders-content");
  const pagination = document.getElementById("pagination");
  try {
    const data = await api("GET", `/api/orders?page=${page}&page_size=${PAGE_SIZE}`);
    totalItems = data.total;
    currentPage = data.page;

    if (!data.items.length) {
      content.innerHTML = '<div class="empty-state">Заказов пока нет.<br><a href="pf-order.html">Создать первый заказ →</a></div>';
      pagination.style.display = "none";
      return;
    }

    const rows = data.items.map(o => {
      const statusClass = o.status === "Posted" ? "status-posted" : "status-other";
      const links = parseLinks(o.links);
      const linksHtml = links.slice(0, 3).map(l =>
        `<a href="${escHtml(l)}" target="_blank" rel="noopener" style="display:block;color:#0077cc;">${escHtml(l.replace(/https?:\/\/(www\.)?avito\.ru/, "avito.ru"))}</a>`
      ).join("") + (links.length > 3 ? `<span style="color:#aaa;">ещё ${links.length-3}…</span>` : "");

      return `<tr>
        <td>#${o.order_id}</td>
        <td style="white-space:nowrap;">${o.date ? o.date.substring(0, 16).replace("T", " ") : "—"}</td>
        <td>${escHtml(o.position_name)}</td>
        <td style="white-space:nowrap;">${o.price} ₽</td>
        <td>${o.contacts ? "Да" : "Нет"}</td>
        <td><span class="status-badge ${statusClass}">${escHtml(o.status)}</span></td>
        <td class="links-cell">${linksHtml}</td>
      </tr>`;
    }).join("");

    content.innerHTML = `<table>
      <thead><tr>
        <th>#</th><th>Дата</th><th>Параметры</th>
        <th>Сумма</th><th>Контакты</th><th>Статус</th><th>Ссылки</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

    const totalPages = Math.ceil(totalItems / PAGE_SIZE);
    document.getElementById("page-info").textContent =
      `Стр. ${currentPage} из ${totalPages} (всего ${totalItems})`;
    document.getElementById("prev-btn").disabled = currentPage <= 1;
    document.getElementById("next-btn").disabled = currentPage >= totalPages;
    pagination.style.display = totalPages > 1 ? "flex" : "none";

  } catch (e) {
    content.innerHTML = `<div class="err">Ошибка загрузки: ${e}</div>`;
  }
}

function parseLinks(raw) {
  const matches = (raw || "").match(/https?:\/\/[^\s'"[\],]+/g);
  return matches || [];
}

function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

document.getElementById("prev-btn").onclick = () => loadOrders(currentPage - 1);
document.getElementById("next-btn").onclick = () => loadOrders(currentPage + 1);

loadOrders(1);
</script>
</body>
</html>
```

- [ ] **Step 12.2: Run full test suite — all green**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```
Expected: all tests PASSED. Zero failures.

- [ ] **Step 12.3: Final commit**

```bash
git add web/static/orders.html
git commit -m "feat: add orders.html — paginated order history page"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|---|---|
| Auth already exists | N/A — not in scope |
| Main screen with Services block | Task 10 |
| Avito PF only service (for now) | Task 10, 11 |
| PF order form (all fields on one screen) | Task 11 |
| Order creation notifies admins via bot | Task 6 (`_notify_new_order`) |
| Order creation notifies user in TG if linked | Task 6 (`get_tg_id_for_user`) |
| Support: user writes question | Tasks 7, 8 |
| Support: bot forwards to admins with ID tag | Task 8 (`_forward_to_admins`) |
| Support: admin TG reply → web chat | Task 9 (`support_web.py` handler) |
| Recent 20 orders block on dashboard | Task 10 |
| "All orders" button → dedicated page | Task 10, 12 |
| Orders page with pagination | Task 12 |

### Placeholder scan

No TBD, TODO, or placeholder content — all code is complete and runnable.

### Type consistency

- `PFOrderRequest.fix_count` → `services/orders.create_pf_order(fix_count=...)` ✓
- `OrderItem.order_id` ← `o["increment"]` ✓
- `SupportMessageItem.direction` ← `m["direction"]` ('user'|'admin') ✓
- `_SUPPORT_TAG = "Вопрос из веб"` used in both `support.py` router and `support_web.py` handler ✓ (handler uses same literal string to match)
