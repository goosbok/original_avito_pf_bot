# Guest Order (Авито ПФ без регистрации) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Заказать без регистрации" button to the landing page, leading to a guest PF order form that accepts a phone number and pays via YooKassa directly (no balance), storing orders in a new `guest_orders` table visible in the admin panel.

**Architecture:** New `guest_orders` SQLite table isolated from `users`/`orders`. Three new public API endpoints handle availability check, order creation, and payment status polling. Three new React JSX components (GuestOrderForm, GuestOrderSuccess) + Landing/app.jsx/AdminOrders.jsx edits. Tests mock YooKassa calls exactly as existing refill tests do.

**Tech Stack:** FastAPI, SQLite (via `services/db.py`), Pydantic v2, YooKassa SDK, React 18 (Babel, no build step), pytest + TestClient.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `utils/sqlite3.py` | Modify | Add `guest_orders` to `get_schema_statements()` |
| `tests/conftest.py` | Modify | Add `SITE_URL` to config stub |
| `scripts/migrate_guest_orders.py` | Create | One-shot migration for existing prod DB |
| `web/schemas.py` | Modify | 4 new schemas, extend `AdminOrderItem` |
| `services/guest_orders.py` | Create | DB ops + YooKassa payment creation |
| `web/routers/guest_orders.py` | Create | 3 public API endpoints |
| `web/main.py` | Modify | Include guest_orders router |
| `web/routers/admin_orders.py` | Modify | Add `?is_guest` param for guest tab |
| `tests/web/test_routers_guest_orders.py` | Create | API tests for all 3 endpoints |
| `web/static/components/Landing.jsx` | Modify | payment-available fetch + disabled button |
| `web/static/components/GuestOrderForm.jsx` | Create | Order form without balance, with phone |
| `web/static/components/GuestOrderSuccess.jsx` | Create | Polling + success/fail screen |
| `web/static/app.jsx` | Modify | URL param detection + 2 new routes |
| `web/static/index.html` | Modify | Load 2 new JSX files |
| `web/static/components/AdminOrders.jsx` | Modify | Guest filter tab + phone display |

---

## Task 1: DB Schema — add `guest_orders` table

**Files:**
- Modify: `utils/sqlite3.py`
- Modify: `tests/conftest.py`
- Create: `scripts/migrate_guest_orders.py`

- [ ] **Step 1: Add `guest_orders` to `get_schema_statements()` in `utils/sqlite3.py`**

Find the end of the `return [` list in `get_schema_statements()` (after the last tuple, before the closing `]`) and append:

```python
        (
            "guest_orders",
            "CREATE TABLE IF NOT EXISTS guest_orders("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "phone TEXT NOT NULL,"
            "links TEXT NOT NULL,"
            "days INTEGER NOT NULL,"
            "fix_count INTEGER NOT NULL,"
            "contacts INTEGER NOT NULL DEFAULT 0,"
            "price INTEGER NOT NULL,"
            "price_per_unit INTEGER NOT NULL,"
            "payment_id TEXT,"
            "status TEXT NOT NULL DEFAULT 'pending_payment',"
            "created_at TEXT NOT NULL)",
            11,
        ),
```

- [ ] **Step 2: Add `SITE_URL` to the config stub in `tests/conftest.py`**

In `_make_config_stub()`, after the `stub.botlink = ...` line, add:

```python
    stub.SITE_URL = ""
```

- [ ] **Step 3: Create migration script `scripts/migrate_guest_orders.py`**

```python
"""One-shot migration: create guest_orders table on existing prod DB.

Idempotent — safe to run multiple times.
Run: python scripts/migrate_guest_orders.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.config import path_database


DDL = (
    "CREATE TABLE IF NOT EXISTS guest_orders("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "phone TEXT NOT NULL,"
    "links TEXT NOT NULL,"
    "days INTEGER NOT NULL,"
    "fix_count INTEGER NOT NULL,"
    "contacts INTEGER NOT NULL DEFAULT 0,"
    "price INTEGER NOT NULL,"
    "price_per_unit INTEGER NOT NULL,"
    "payment_id TEXT,"
    "status TEXT NOT NULL DEFAULT 'pending_payment',"
    "created_at TEXT NOT NULL)"
)


def main() -> None:
    con = sqlite3.connect(path_database)
    try:
        con.execute(DDL)
        con.commit()
        print("guest_orders table created (or already existed).")
    finally:
        con.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify schema appears in test DB**

Run: `docker exec <container> python -c "from utils.sqlite3 import get_schema_statements; print([t for t,_,_ in get_schema_statements()])"`

Expected output contains `'guest_orders'`.

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py tests/conftest.py scripts/migrate_guest_orders.py
git commit -m "feat(db): add guest_orders table schema and migration"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Modify: `web/schemas.py`

- [ ] **Step 1: Add 4 new schemas to `web/schemas.py`**

After the existing `PFOrderResponse` class (around line 163), add:

```python
class PaymentAvailableResponse(BaseModel):
    available: bool


class GuestPFOrderRequest(BaseModel):
    links: list[str] = Field(min_length=1)
    days: int = Field(gt=0)
    fix_count: int = Field(ge=5)
    contacts: bool
    phone: str = Field(min_length=5, max_length=32)

    @field_validator("links")
    @classmethod
    def links_must_be_avito(cls, v: list[str]) -> list[str]:
        for link in v:
            if not _re.search(r'avito\.ru', link):
                raise ValueError(f"invalid avito link: {link}")
        return v


class GuestPFOrderResponse(BaseModel):
    guest_order_id: int
    payment_url: str


class GuestOrderStatusResponse(BaseModel):
    status: str   # "pending" | "paid" | "failed"
    order_id: int | None = None
```

- [ ] **Step 2: Extend `AdminOrderItem` with guest fields**

Change the existing `AdminOrderItem` class from:

```python
class AdminOrderItem(BaseModel):
    order_id: int
    user_id: int
    user_name: str | None
    price: int
    position_name: str
    status: str
    links: str
    date: str
    contacts: bool
```

to:

```python
class AdminOrderItem(BaseModel):
    order_id: int
    user_id: int | None
    user_name: str | None
    price: int
    position_name: str
    status: str
    links: str
    date: str
    contacts: bool
    is_guest: bool = False
    guest_phone: str | None = None
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

Run: `docker exec <container> python -m pytest tests/web/test_routers_orders.py tests/web/test_routers_refill.py -v`

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add web/schemas.py
git commit -m "feat(schemas): add guest order schemas, extend AdminOrderItem"
```

---

## Task 3: Service Layer — `services/guest_orders.py`

**Files:**
- Create: `services/guest_orders.py`

- [ ] **Step 1: Create `services/guest_orders.py`**

```python
"""Guest order service — DB ops and YooKassa payment creation."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from services.db import connect
from services.exceptions import PaymentError


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")


def create_guest_order(
    phone: str,
    links: list[str],
    days: int,
    fix_count: int,
    contacts: bool,
    price: int,
    price_per_unit: int,
) -> int:
    """Insert a pending_payment guest order, return its id."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO guest_orders"
            "(phone, links, days, fix_count, contacts, price, price_per_unit, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_payment', ?)",
            (
                phone,
                json.dumps(links),
                days,
                fix_count,
                int(contacts),
                price,
                price_per_unit,
                _now(),
            ),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def get_guest_order(guest_order_id: int) -> dict | None:
    """Return the guest_orders row as dict, or None if not found."""
    with connect() as con:
        return con.execute(
            "SELECT * FROM guest_orders WHERE id = ?", (guest_order_id,)
        ).fetchone()


def set_payment_id(guest_order_id: int, payment_id: str) -> None:
    """Store the YooKassa payment_id on the order."""
    with connect() as con:
        con.execute(
            "UPDATE guest_orders SET payment_id = ? WHERE id = ?",
            (payment_id, guest_order_id),
        )
        con.commit()


def update_status(guest_order_id: int, status: str) -> None:
    """Set status to 'paid' or 'failed'."""
    with connect() as con:
        con.execute(
            "UPDATE guest_orders SET status = ? WHERE id = ?",
            (status, guest_order_id),
        )
        con.commit()


def create_payment(guest_order_id: int, amount: int, phone: str) -> tuple[str, str]:
    """Create a YooKassa payment. Returns (payment_url, payment_id).

    Raises PaymentError if the YooKassa call fails.
    """
    from data.config import SHOP_ID, SECRET_KEY, SITE_URL
    from yookassa import Configuration, Payment

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    return_url = f"{SITE_URL}/?guest_order_id={guest_order_id}"

    try:
        payment = Payment.create(
            {
                "amount": {"value": f"{amount}.00", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": return_url},
                "capture": True,
                "description": f"Авито ПФ (гостевой заказ #{guest_order_id})",
                "receipt": {
                    "phone": phone,
                    "items": [
                        {
                            "description": f"Авито ПФ #{guest_order_id}",
                            "quantity": 1,
                            "amount": {"value": f"{amount}.00", "currency": "RUB"},
                            "vat_code": 1,
                            "payment_mode": "full_prepayment",
                            "payment_subject": "service",
                        }
                    ],
                    "tax_system_code": 1,
                },
            },
            str(uuid.uuid4()),
        )
        data = json.loads(payment.json())
        return data["confirmation"]["confirmation_url"], data["id"]
    except Exception as exc:
        raise PaymentError(f"yookassa create failed: {exc}") from exc
```

- [ ] **Step 2: Commit**

```bash
git add services/guest_orders.py
git commit -m "feat(services): add guest_orders service — DB ops and payment creation"
```

---

## Task 4: Guest Orders Router + Wire

**Files:**
- Create: `web/routers/guest_orders.py`
- Modify: `web/main.py`

- [ ] **Step 1: Create `web/routers/guest_orders.py`**

```python
"""Guest orders API — public endpoints, no auth required.

GET  /api/guest-orders/payment-available   — is YooKassa accepting payments?
POST /api/guest-orders/pf                  — create guest order + YooKassa payment
GET  /api/guest-orders/{guest_order_id}/status — poll payment status
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from services import guest_orders as svc
from services.exceptions import PaymentError
from services.payment_probe import is_yookassa_enabled
from services.orders import get_pf_price_per_unit
from web.schemas import (
    GuestOrderStatusResponse,
    GuestPFOrderRequest,
    GuestPFOrderResponse,
    PaymentAvailableResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guest-orders", tags=["guest-orders"])


@router.get("/payment-available", response_model=PaymentAvailableResponse)
async def payment_available() -> PaymentAvailableResponse:
    return PaymentAvailableResponse(available=is_yookassa_enabled())


@router.post("/pf", response_model=GuestPFOrderResponse, status_code=201)
async def create_guest_pf_order(body: GuestPFOrderRequest) -> GuestPFOrderResponse:
    if not is_yookassa_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Онлайн-оплата временно недоступна",
        )

    price_per_unit = get_pf_price_per_unit()
    price = body.fix_count * body.days * len(body.links) * price_per_unit

    guest_order_id = svc.create_guest_order(
        phone=body.phone,
        links=body.links,
        days=body.days,
        fix_count=body.fix_count,
        contacts=body.contacts,
        price=price,
        price_per_unit=price_per_unit,
    )

    try:
        payment_url, payment_id = svc.create_payment(guest_order_id, price, body.phone)
    except PaymentError as exc:
        logger.error("guest order %s payment creation failed: %s", guest_order_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось создать платёж. Попробуйте позже или обратитесь в поддержку.",
        ) from exc

    svc.set_payment_id(guest_order_id, payment_id)

    return GuestPFOrderResponse(guest_order_id=guest_order_id, payment_url=payment_url)


@router.get("/{guest_order_id}/status", response_model=GuestOrderStatusResponse)
async def get_guest_order_status(guest_order_id: int) -> GuestOrderStatusResponse:
    order = svc.get_guest_order(guest_order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="guest order not found")

    if order["status"] == "paid":
        return GuestOrderStatusResponse(status="paid", order_id=guest_order_id)

    if order["status"] == "failed":
        return GuestOrderStatusResponse(status="failed")

    if not order["payment_id"]:
        return GuestOrderStatusResponse(status="pending")

    # Check YooKassa
    from data.config import SHOP_ID, SECRET_KEY
    from yookassa import Configuration, Payment

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    try:
        payment = Payment.find_one(order["payment_id"])
    except Exception as exc:
        logger.warning("guest order %s yookassa check failed: %s", guest_order_id, exc)
        return GuestOrderStatusResponse(status="pending")

    if payment.status == "succeeded":
        svc.update_status(guest_order_id, "paid")
        asyncio.create_task(_notify_guest_order_paid(order))
        return GuestOrderStatusResponse(status="paid", order_id=guest_order_id)

    if payment.status in {"canceled", "expired", "rejected"}:
        svc.update_status(guest_order_id, "failed")
        return GuestOrderStatusResponse(status="failed")

    return GuestOrderStatusResponse(status="pending")


async def _notify_guest_order_paid(order: dict) -> None:
    """Fire-and-forget Telegram admin notification."""
    try:
        from utils.other import format_decimal
        from utils.sender import send_admins

        import json
        links = json.loads(order["links"]) if order["links"] else []
        links_str = "".join(f"\n<code>{l}</code>" for l in links)

        msg = (
            f"🌐 <b>Новый гостевой заказ #{order['id']}</b>\n"
            f"💰 Сумма: <b>{format_decimal(order['price'])} ₽</b>\n"
            f"📞 Телефон: {order['phone']}\n"
            f"📋 Авито ПФ · {order['fix_count']} просм./д · {order['days']} дн.\n"
            f"📞 Контакты: {'Да' if order['contacts'] else 'Нет'}\n"
            f"🔗 Объявлений: {len(links)}{links_str}"
        )
        await send_admins(msg)
    except Exception:
        logger.exception("_notify_guest_order_paid failed for order id=%s", order.get("id"))
```

- [ ] **Step 2: Add router to `web/main.py`**

After the line `app.include_router(config_router)`, add:

```python
from web.routers.guest_orders import router as guest_orders_router  # noqa: E402

app.include_router(guest_orders_router)
```

- [ ] **Step 3: Quick smoke test — server starts**

Run: `docker exec <container> python -c "from web.main import app; print('OK')"`

Expected: `OK` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add web/routers/guest_orders.py web/main.py
git commit -m "feat(api): add guest orders router — payment-available, create, status"
```

---

## Task 5: Admin Orders — Guest Filter

**Files:**
- Modify: `web/routers/admin_orders.py`

- [ ] **Step 1: Add `is_guest` param and separate query path to `list_orders`**

Replace the entire `list_orders` function with:

```python
def _guest_row_to_item(row) -> AdminOrderItem:
    return AdminOrderItem(
        order_id=int(row["id"]),
        user_id=None,
        user_name=None,
        price=int(row["price"] or 0),
        position_name="Авито ПФ (гостевой)",
        status=str(row["status"] or ""),
        links=str(row["links"] or ""),
        date=str(row["created_at"] or ""),
        contacts=bool(row["contacts"]),
        is_guest=True,
        guest_phone=str(row["phone"] or ""),
    )


@router.get("", response_model=AdminOrderListResponse)
async def list_orders(
    status: str | None = None,
    user_id: int | None = None,
    is_guest: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    _: int = Depends(require_admin),
) -> AdminOrderListResponse:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    if is_guest is True:
        # Query guest_orders table only
        with connect() as con:
            total = con.execute(
                "SELECT COUNT(*) AS c FROM guest_orders"
            ).fetchone()["c"]
            rows = con.execute(
                "SELECT id, phone, price, status, links, created_at, contacts "
                "FROM guest_orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
        return AdminOrderListResponse(
            items=[_guest_row_to_item(r) for r in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    # Default: regular orders only (existing behaviour, backward-compatible)
    where = []
    params: list = []
    if status:
        where.append("status = ?")
        params.append(status)
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with connect() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM orders {where_sql}", tuple(params)
        ).fetchone()["c"]
        rows = con.execute(
            f"SELECT increment, user_id, user_name, price, position_name, status, links, date, contacts "
            f"FROM orders {where_sql} ORDER BY increment DESC LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        ).fetchall()

    return AdminOrderListResponse(
        items=[_row_to_item(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 2: Run existing admin orders test (if any)**

Run: `docker exec <container> python -m pytest tests/ -k "admin_order" -v`

Expected: pass (or "no tests collected" — that's fine too).

- [ ] **Step 3: Commit**

```bash
git add web/routers/admin_orders.py
git commit -m "feat(admin): add is_guest filter to admin orders endpoint"
```

---

## Task 6: Tests — `test_routers_guest_orders.py`

**Files:**
- Create: `tests/web/test_routers_guest_orders.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for /api/guest-orders/* endpoints."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_db: Path):
    from web.main import app
    return TestClient(app)


def _fake_payment(url="https://pay.yookassa.ru/pay/abc", pid="pay-guest-1"):
    return (url, pid)


# ── payment-available ────────────────────────────────────────────────────────

def test_payment_available_false_when_yookassa_disabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: False)
    r = client.get("/api/guest-orders/payment-available")
    assert r.status_code == 200
    assert r.json() == {"available": False}


def test_payment_available_true_when_enabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: True)
    r = client.get("/api/guest-orders/payment-available")
    assert r.status_code == 200
    assert r.json() == {"available": True}


# ── POST /api/guest-orders/pf ────────────────────────────────────────────────

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: True)
    monkeypatch.setattr("web.routers.guest_orders.get_pf_price_per_unit", lambda: 6)


VALID_BODY = {
    "links": ["https://www.avito.ru/item/123"],
    "days": 7,
    "fix_count": 30,
    "contacts": False,
    "phone": "+79991234567",
}


def test_create_guest_order_success(client, enabled, monkeypatch):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/abc", "pay-1"),
    )
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["guest_order_id"] > 0
    assert body["payment_url"] == "https://pay/abc"


def test_create_guest_order_503_when_payment_disabled(client, monkeypatch):
    monkeypatch.setattr("web.routers.guest_orders.is_yookassa_enabled", lambda: False)
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    assert r.status_code == 503


def test_create_guest_order_invalid_link(client, enabled):
    body = {**VALID_BODY, "links": ["https://www.example.com/not-avito"]}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_empty_phone(client, enabled):
    body = {**VALID_BODY, "phone": ""}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_fix_count_too_low(client, enabled):
    body = {**VALID_BODY, "fix_count": 3}
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 422


def test_create_guest_order_price_calculated_correctly(client, enabled, monkeypatch):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/x", "pay-x"),
    )
    monkeypatch.setattr("web.routers.guest_orders.get_pf_price_per_unit", lambda: 6)
    body = {**VALID_BODY, "days": 7, "fix_count": 30}
    # price = 30 * 7 * 1 (link) * 6 = 1260
    r = client.post("/api/guest-orders/pf", json=body)
    assert r.status_code == 201
    gid = r.json()["guest_order_id"]
    from services.guest_orders import get_guest_order
    order = get_guest_order(gid)
    assert order["price"] == 1260


# ── GET /api/guest-orders/{id}/status ────────────────────────────────────────

def _create_order_with_payment(client, enabled, monkeypatch, payment_id="pay-2"):
    monkeypatch.setattr(
        "web.routers.guest_orders.svc.create_payment",
        lambda gid, amt, phone: ("https://pay/x", payment_id),
    )
    r = client.post("/api/guest-orders/pf", json=VALID_BODY)
    return r.json()["guest_order_id"]


def test_status_pending_when_yookassa_returns_pending(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "pending"

    with patch("web.routers.guest_orders.Payment") as MockPayment:
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_status_paid_when_yookassa_returns_succeeded(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "succeeded"

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.guest_orders._notify_guest_order_paid", _noop)

    with patch("web.routers.guest_orders.Payment") as MockPayment, \
         patch("web.routers.guest_orders.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paid"
    assert body["order_id"] == gid


def test_status_paid_is_idempotent(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "succeeded"

    async def _noop(*a, **kw):
        pass

    monkeypatch.setattr("web.routers.guest_orders._notify_guest_order_paid", _noop)

    with patch("web.routers.guest_orders.Payment") as MockPayment, \
         patch("web.routers.guest_orders.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r1 = client.get(f"/api/guest-orders/{gid}/status")
        r2 = client.get(f"/api/guest-orders/{gid}/status")

    assert r1.json()["status"] == "paid"
    assert r2.json()["status"] == "paid"
    # Second call should not crash and should return same result


def test_status_failed_when_yookassa_canceled(client, enabled, monkeypatch):
    gid = _create_order_with_payment(client, enabled, monkeypatch)

    fake_payment = MagicMock()
    fake_payment.status = "canceled"

    with patch("web.routers.guest_orders.Payment") as MockPayment, \
         patch("web.routers.guest_orders.Configuration"):
        MockPayment.find_one.return_value = fake_payment
        r = client.get(f"/api/guest-orders/{gid}/status")

    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_status_404_for_unknown_order(client):
    r = client.get("/api/guest-orders/99999/status")
    assert r.status_code == 404
```

- [ ] **Step 2: Run the tests to make sure they pass**

Run: `docker exec <container> python -m pytest tests/web/test_routers_guest_orders.py -v`

Expected: all 12 tests pass.

- [ ] **Step 3: Run full test suite to check for regressions**

Run: `docker exec <container> python -m pytest tests/ -v --tb=short`

Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/web/test_routers_guest_orders.py
git commit -m "test(guest-orders): full API test coverage for guest order endpoints"
```

---

## Task 7: Frontend — Landing.jsx

**Files:**
- Modify: `web/static/components/Landing.jsx`

- [ ] **Step 1: Add `useEffect` to the destructure at top of file**

Change line 2 from:
```js
const { useState: useLandingState } = React;
```
to:
```js
const { useState: useLandingState, useEffect: useLandingEffect } = React;
```

- [ ] **Step 2: Add `paymentAvailable` state and fetch inside `LandingPage` component**

Inside `const LandingPage = ({ onNavigate, brandName }) => {`, add at the top of the function body (before `return`):

```jsx
  const [paymentAvailable, setPaymentAvailable] = useLandingState(true);

  useLandingEffect(() => {
    api.get('/api/guest-orders/payment-available')
      .then(d => { if (!d.__unauthorized) setPaymentAvailable(d.available !== false); })
      .catch(() => {});
  }, []);
```

- [ ] **Step 3: Add the "Заказать без регистрации" button**

In the Hero section, find the `<div className="landing-hero__ctas">` block (contains "Войти через Telegram" and "Войти через Email"). Replace it with:

```jsx
        <div className="landing-hero__ctas">
          <button className="btn btn--primary btn--lg" onClick={() => onNavigate('login-tg')}>
            Войти через Telegram
          </button>
          <button className="btn btn--ghost btn--lg" onClick={() => onNavigate('login')}>
            Войти через Email
          </button>
        </div>
        <div style={{ marginTop: 10 }}>
          <button
            className="btn btn--ghost btn--lg"
            onClick={() => paymentAvailable && onNavigate('guest-order-pf')}
            disabled={!paymentAvailable}
            title={!paymentAvailable ? 'Онлайн-оплата временно недоступна' : undefined}
            style={!paymentAvailable ? { opacity: 0.45, cursor: 'not-allowed' } : undefined}
          >
            ⚡ Заказать без регистрации
          </button>
        </div>
```

- [ ] **Step 4: Commit**

```bash
git add web/static/components/Landing.jsx
git commit -m "feat(landing): add guest order button with payment-available check"
```

---

## Task 8: Frontend — GuestOrderForm.jsx

**Files:**
- Create: `web/static/components/GuestOrderForm.jsx`

- [ ] **Step 1: Create `web/static/components/GuestOrderForm.jsx`**

```jsx
// Guest PF Order Form — same as OrderFormPage but no balance, + phone field, direct YooKassa payment
const { useState: useGOFState, useEffect: useGOFEffect } = React;

// parseAvitoUrls is defined locally (not exported from OrderForm.jsx)
function parseGuestAvitoUrls(text) {
  if (!text) return [];
  const normalized = text.replace(/(?<=\S)[\r\n]+(?=\S)/g, '');
  const raw = normalized.match(/https?:\/\/(?:www\.)?avito\.ru\/\S+/g) || [];
  const seen = new Set();
  return raw
    .map(u => u.replace(/["')\].,;]+$/, '').split('?')[0])
    .filter(u => { if (seen.has(u)) return false; seen.add(u); return true; });
}

function GuestOrderForm({ onNavigate }) {
  const [inputText, setInputText] = useGOFState('');
  const [links, setLinks] = useGOFState([]);
  const [views, setViews] = useGOFState(30);
  const [days, setDays] = useGOFState(7);
  const [contacts, setContacts] = useGOFState(false);
  const [startDate, setStartDate] = useGOFState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0];
  });
  const [phone, setPhone] = useGOFState('');
  const [pricePerUnit, setPricePerUnit] = useGOFState(6);
  const [paymentAvailable, setPaymentAvailable] = useGOFState(true);
  const [loading, setLoading] = useGOFState(false);
  const [error, setError] = useGOFState('');

  useGOFEffect(() => {
    api.get('/api/orders/pf/price').then(d => {
      if (!d.__unauthorized) setPricePerUnit(d.price_per_unit || 6);
    }).catch(() => {});
    api.get('/api/guest-orders/payment-available').then(d => {
      if (!d.__unauthorized) setPaymentAvailable(d.available !== false);
    }).catch(() => {});
  }, []);

  const urlCount = links.length;
  const totalPrice = urlCount > 0 ? views * days * urlCount * pricePerUnit : 0;

  const handleInputChange = e => {
    const val = e.target.value;
    const parsed = parseGuestAvitoUrls(val);
    const toAdd = parsed.filter(u => !links.includes(u));
    if (toAdd.length) setLinks(prev => [...prev, ...toAdd]);
    setInputText(val);
  };

  const removeLink = url => setLinks(prev => prev.filter(u => u !== url));

  const handleSubmit = async () => {
    if (urlCount === 0) return setError('Вставьте хотя бы одну ссылку на объявление');
    if (!phone.trim()) return setError('Укажите номер телефона');
    if (!paymentAvailable) return setError('Онлайн-оплата временно недоступна');
    setError(''); setLoading(true);
    try {
      const data = await api.post('/api/guest-orders/pf', {
        links,
        days,
        fix_count: views,
        contacts,
        phone: phone.trim(),
      });
      window.location.href = data.payment_url;
    } catch (e) {
      setError(e.message || 'Ошибка создания заказа. Попробуйте позже или напишите в поддержку.');
    } finally { setLoading(false); }
  };

  const noUrlsWarning = inputText.length > 5 && parseGuestAvitoUrls(inputText).length === 0 && urlCount === 0;

  return (
    <div className="page-wrap">
      <div className="order-page">
        <div className="container" style={{ maxWidth: 900 }}>

          <button className="order-back" onClick={() => onNavigate('landing')}>← На главную</button>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>Авито ПФ</h1>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-3)' }}>
              Поведенческие факторы · {pricePerUnit} ₽ за просмотр
            </span>
            <span style={{ marginLeft: 'auto', background: 'var(--primary-dim)', color: 'var(--primary)', fontSize: '0.75rem', fontWeight: 700, padding: '3px 10px', borderRadius: 4 }}>
              Без регистрации
            </span>
          </div>

          {!paymentAvailable && (
            <div className="alert alert--error" style={{ marginBottom: 16 }}>
              Онлайн-оплата временно недоступна. Для заказа <a href="https://t.me/avito_pf_otzizi" target="_blank" rel="noopener" style={{ color: 'inherit', fontWeight: 700 }}>напишите в поддержку</a>.
            </div>
          )}
          {error && <div className="alert alert--error" style={{ marginBottom: 16 }}>{error}</div>}

          <div className="order-two-col" style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>

            {/* LEFT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid var(--primary)' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, marginBottom: 5, color: 'var(--text-1)' }}>Рекомендация</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-2)', lineHeight: 1.65 }}>
                  Начните с <strong>15–30 просм./день без контактов</strong> в течение недели.
                  После оживления органики постепенно добавляйте 5–8 контактов.
                </div>
              </div>

              <div className="card" style={{ padding: '18px 20px' }}>
                <div className="form-field">
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
                    <label className="form-label" style={{ margin: 0, fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-1)' }}>
                      Ссылки на объявления
                    </label>
                    {urlCount > 0 && (
                      <span className="badge badge--new">✓ {urlCount} {urlCount === 1 ? 'объявление' : urlCount < 5 ? 'объявления' : 'объявлений'}</span>
                    )}
                  </div>
                  <textarea
                    className="textarea input-mono"
                    rows={4}
                    placeholder="Вставьте ссылки или любой текст со ссылками Авито"
                    value={inputText}
                    onChange={handleInputChange}
                    style={{ resize: 'none' }}
                  />
                  {noUrlsWarning && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--status-cancel-text)', marginTop: 6 }}>⚠ Авито-ссылки не найдены</div>
                  )}
                  {urlCount > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>Добавленные объявления</div>
                      {links.map((url, i) => (
                        <div key={url} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: i < links.length - 1 ? '1px solid var(--border)' : 'none' }}>
                          <a href={url} target="_blank" rel="noopener noreferrer" title={url}
                            style={{ flex: 1, fontSize: '0.775rem', fontFamily: 'monospace', color: 'var(--primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380, textDecoration: 'none' }}>
                            {url.length > 60 ? url.slice(0, 60) + '…' : url}
                          </a>
                          <button onClick={() => removeLink(url)}
                            style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-cancel-text)', fontWeight: 700, fontSize: '1.1rem', padding: '0 4px', lineHeight: 1 }}>
                            −
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  {urlCount === 0 && (
                    <div className="form-hint" style={{ marginTop: 6 }}>Каждое уникальное объявление — отдельная строка в счёте</div>
                  )}
                </div>
              </div>

              {/* Phone field */}
              <div className="card" style={{ padding: '18px 20px' }}>
                <div className="form-field">
                  <label className="form-label">Номер телефона</label>
                  <input
                    type="tel"
                    className="input"
                    placeholder="+7 (999) 000-00-00"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                  />
                  <div className="form-hint" style={{ marginTop: 6 }}>
                    Нужен для связи при проблемах с заказом. Назовите его в поддержке — найдём заказ без регистрации.
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                <SliderField label="Просмотров в день" min={5} max={500} step={5} value={views} onChange={setViews} hint="Рекомендуем 15–50 для начала" />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <SliderField label="Количество дней" min={1} max={30} step={1} value={days} onChange={setDays} suffix=" дн." hint="Лучше крутить непрерывно от 7 дней" />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="form-field">
                  <label className="form-label">Дата начала</label>
                  <input type="date" className="input" value={startDate} min={new Date().toISOString().split('T')[0]} onChange={e => setStartDate(e.target.value)} />
                  <div className="form-hint">Запуск на следующий день или до 04:00 МСК — сегодня</div>
                </div>
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="toggle-row" onClick={() => setContacts(v => !v)} style={{ userSelect: 'none', cursor: 'pointer' }}>
                  <div className={`toggle${contacts ? ' on' : ''}`} />
                  <div>
                    <div className="toggle-label" style={{ fontSize: '0.875rem' }}>Запросы контактов</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: 2 }}>Включать постепенно</div>
                  </div>
                </div>
              </div>

              {/* Price preview */}
              <div style={{ background: 'var(--surface)', border: '1.5px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                <div style={{ background: 'var(--primary-dim)', borderBottom: '1px solid rgba(0,136,204,0.15)', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Стоимость</span>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.03em' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
                </div>
                <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[
                    { label: 'Просмотров в день', val: views },
                    { label: 'Количество дней', val: days },
                    { label: 'Объявлений', val: Math.max(urlCount, 1) },
                    { label: 'Цена за просмотр', val: `${pricePerUnit} ₽` },
                  ].map((row, i, arr) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.8125rem', color: 'var(--text-2)' }}>{row.label}</span>
                        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-1)' }}>× {row.val}</span>
                      </div>
                      {i < arr.length - 1 && <div style={{ height: 1, background: 'var(--border)', marginTop: 8 }} />}
                    </div>
                  ))}
                </div>
              </div>

              <button
                className="btn btn--primary btn--lg btn--full desktop-only"
                onClick={handleSubmit}
                disabled={loading || urlCount === 0 || !paymentAvailable}
                style={{ fontSize: '0.9375rem' }}
              >
                {loading ? 'Создаём заказ...' : 'Перейти к оплате →'}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile sticky footer */}
        <div className="order-sticky-footer">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-2)' }}>Итого:</span>
            <span style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--primary)' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleSubmit}
            disabled={loading || urlCount === 0 || !paymentAvailable}>
            {loading ? 'Создаём...' : 'Перейти к оплате →'}
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GuestOrderForm });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/GuestOrderForm.jsx
git commit -m "feat(frontend): add GuestOrderForm component"
```

---

## Task 9: Frontend — GuestOrderSuccess.jsx

**Files:**
- Create: `web/static/components/GuestOrderSuccess.jsx`

- [ ] **Step 1: Create `web/static/components/GuestOrderSuccess.jsx`**

```jsx
// GuestOrderSuccess — polls payment status, shows order number + TP instructions
const { useState: useGOSState, useEffect: useGOSEffect, useRef: useGOSRef } = React;

const SUPPORT_LINK = 'https://t.me/avito_pf_otzizi';
const MAX_POLLS = 30;
const POLL_INTERVAL_MS = 2000;

function GuestOrderSuccess({ guestOrderId, onNavigate }) {
  const [state, setState] = useGOSState('polling'); // polling | paid | failed | timeout
  const [orderId, setOrderId] = useGOSState(null);
  const polls = useGOSRef(0);

  useGOSEffect(() => {
    if (!guestOrderId) { setState('failed'); return; }

    const timer = setInterval(async () => {
      polls.current += 1;
      if (polls.current > MAX_POLLS) {
        clearInterval(timer);
        setState('timeout');
        return;
      }
      try {
        const data = await api.get(`/api/guest-orders/${guestOrderId}/status`);
        if (data.status === 'paid') {
          clearInterval(timer);
          setOrderId(data.order_id || guestOrderId);
          setState('paid');
        } else if (data.status === 'failed') {
          clearInterval(timer);
          setState('failed');
        }
      } catch (_) {}
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [guestOrderId]);

  if (state === 'polling') return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ textAlign: 'center', padding: 40 }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 16 }}>⏳</div>
        <h2 style={{ marginBottom: 8 }}>Проверяем оплату...</h2>
        <p style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Это займёт несколько секунд</p>
      </div>
    </div>
  );

  if (state === 'paid') return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ maxWidth: 460, padding: '0 20px', width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>✅</div>
          <h2 style={{ marginBottom: 6 }}>Оплата прошла! Заказ принят</h2>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Спасибо, заказ передан в работу.</p>
        </div>

        <div style={{ background: 'var(--primary-dim)', borderRadius: 8, padding: '14px 18px', marginBottom: 20 }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--primary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Ваш заказ</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)' }}>#{orderId}</div>
        </div>

        <div className="card" style={{ padding: '18px 20px', marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: 14 }}>📞 Как узнать статус заказа</div>
          {[
            <>Напишите в <a href={SUPPORT_LINK} target="_blank" rel="noopener" style={{ color: 'var(--primary)', fontWeight: 700 }}>@avito_pf_otzizi</a></>,
            <>Назовите ваш <strong>номер телефона</strong> (и номер заказа <strong>#{orderId}</strong> — по желанию)</>,
            <>Мы найдём заказ и ответим в течение рабочего дня</>,
          ].map((text, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: i < 2 ? 12 : 0 }}>
              <div style={{ width: 22, height: 22, background: 'var(--primary)', color: '#fff', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 700, flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-1)', lineHeight: 1.5 }}>{text}</div>
            </div>
          ))}
        </div>

        <a href={SUPPORT_LINK} target="_blank" rel="noopener"
          style={{ display: 'block', background: 'var(--primary)', color: '#fff', textDecoration: 'none', textAlign: 'center', padding: '11px 0', borderRadius: 8, fontWeight: 600, fontSize: '0.9rem', marginBottom: 10 }}>
          Написать в поддержку
        </a>
        <div style={{ textAlign: 'center' }}>
          <span style={{ color: 'var(--primary)', fontSize: '0.875rem', cursor: 'pointer' }} onClick={() => onNavigate('landing')}>← На главную</span>
        </div>
      </div>
    </div>
  );

  // failed or timeout
  return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ maxWidth: 400, padding: '0 20px', width: '100%', textAlign: 'center' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>❌</div>
        <h2 style={{ marginBottom: 8 }}>Оплата не прошла</h2>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: 24 }}>
          Платёж был отменён или время ожидания истекло. Попробуйте ещё раз или напишите в поддержку.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button className="btn btn--primary btn--lg btn--full" onClick={() => onNavigate('guest-order-pf')}>
            Попробовать снова
          </button>
          <a href={SUPPORT_LINK} target="_blank" rel="noopener"
            style={{ display: 'block', border: '1.5px solid var(--primary)', color: 'var(--primary)', textDecoration: 'none', textAlign: 'center', padding: '11px 0', borderRadius: 8, fontWeight: 600, fontSize: '0.9rem' }}>
            Написать в поддержку
          </a>
          <span style={{ color: 'var(--primary)', fontSize: '0.875rem', cursor: 'pointer' }} onClick={() => onNavigate('landing')}>← На главную</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GuestOrderSuccess });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/GuestOrderSuccess.jsx
git commit -m "feat(frontend): add GuestOrderSuccess component with polling"
```

---

## Task 10: Frontend — app.jsx

**Files:**
- Modify: `web/static/app.jsx`

- [ ] **Step 1: Add URL param detection for guest order return**

After the existing `_isResetRoute` lines (around line 13), add:

```jsx
  const _guestOrderId = new URLSearchParams(window.location.search).get('guest_order_id');
  const _isGuestReturn = !!_guestOrderId;
```

- [ ] **Step 2: Update initial route state to handle guest return**

Change the `useState` for `route` from:
```jsx
  const [route, setRoute] = useState(_isResetRoute ? 'auth' : 'landing');
```
to:
```jsx
  const [route, setRoute] = useState(_isGuestReturn ? 'guest-order-success' : (_isResetRoute ? 'auth' : 'landing'));
```

- [ ] **Step 3: Add `guestOrderId` state**

After the `const [resetToken]` line, add:
```jsx
  const [guestOrderId] = useState(_guestOrderId);
```

- [ ] **Step 4: Add two new routes to `renderScreen`**

Inside the `switch (route)` in `renderScreen()`, after the `case 'order-pf':` line, add:

```jsx
      case 'guest-order-pf':      return <GuestOrderForm onNavigate={handleNavigate} />;
      case 'guest-order-success': return <GuestOrderSuccess guestOrderId={guestOrderId} onNavigate={handleNavigate} />;
```

- [ ] **Step 5: Commit**

```bash
git add web/static/app.jsx
git commit -m "feat(frontend): wire guest order routes and URL param detection in app.jsx"
```

---

## Task 11: Frontend — index.html

**Files:**
- Modify: `web/static/index.html`

- [ ] **Step 1: Add two new script tags before `app.jsx`**

In `web/static/index.html`, after the line:
```html
  <script type="text/babel" src="/components/AdminSupport.jsx"></script>
```
and before:
```html
  <!-- Root app (last — uses all components) -->
  <script type="text/babel" src="/app.jsx"></script>
```

add:

```html
  <script type="text/babel" src="/components/GuestOrderForm.jsx"></script>
  <script type="text/babel" src="/components/GuestOrderSuccess.jsx"></script>
```

- [ ] **Step 2: Commit**

```bash
git add web/static/index.html
git commit -m "feat(frontend): load GuestOrderForm and GuestOrderSuccess in index.html"
```

---

## Task 12: Frontend — AdminOrders.jsx

**Files:**
- Modify: `web/static/components/AdminOrders.jsx`

- [ ] **Step 1: Add `guestFilter` state and update `load` function**

After the existing state declarations inside `function AdminOrders`, add:
```jsx
  const [guestFilter, setGuestFilter] = useAdmOState(false); // false = regular, true = guest
```

Change the `load` function to:
```jsx
  const load = async (p, sf, gf) => {
    setLoading(true);
    let url = `/api/admin/orders?page=${p}&page_size=20`;
    if (gf) {
      url += '&is_guest=true';
    } else {
      if (sf && sf !== 'all') url += `&status=${sf}`;
    }
    try {
      const data = await api.get(url);
      if (!data.__unauthorized) {
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (_) {} finally { setLoading(false); }
  };
```

Change the `useAdmOEffect` call to:
```jsx
  useAdmOEffect(() => { load(page, statusFilter, guestFilter); }, [page, statusFilter, guestFilter]);
```

- [ ] **Step 2: Add guest filter toggle above the status filters**

Replace the `<div className="orders-filters"...>` block with:

```jsx
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <button
            className={`filter-tab${!guestFilter ? ' active' : ''}`}
            onClick={() => { setGuestFilter(false); setPage(1); }}
          >Обычные</button>
          <button
            className={`filter-tab${guestFilter ? ' active' : ''}`}
            onClick={() => { setGuestFilter(true); setPage(1); }}
          >📞 Гостевые</button>
        </div>

        {!guestFilter && (
          <div className="orders-filters" style={{ marginBottom: 16 }}>
            {['all', ...ADMIN_STATUSES].map(s => (
              <button
                key={s}
                className={`filter-tab${statusFilter === s ? ' active' : ''}`}
                onClick={() => { setStatusFilter(s); setPage(1); }}
              >{s === 'all' ? 'Все' : s}</button>
            ))}
          </div>
        )}
```

- [ ] **Step 3: Update the table row to show guest phone**

Change the `<td>` for user name in the table rows from:
```jsx
                      <td>{o.user_name ? '@' + o.user_name : '#' + o.user_id}</td>
```
to:
```jsx
                      <td>
                        {o.is_guest
                          ? <span style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>📞 {o.guest_phone}</span>
                          : (o.user_name ? '@' + o.user_name : '#' + o.user_id)
                        }
                      </td>
```

- [ ] **Step 4: Hide status dropdown for guest orders**

Change the last `<td>` in the row (the dropdown one) from:
```jsx
                      <td>
                        <select ... >
```
to:
```jsx
                      <td>
                        {o.is_guest ? (
                          <StatusBadge status={o.status} />
                        ) : (
                          <select
                            className="input"
                            value={o.status}
                            onChange={e => setStatus(o.order_id, e.target.value)}
                            disabled={busyId === o.order_id}
                            style={{ padding: '4px 8px', fontSize: '0.8rem', minWidth: 130 }}
                          >
                            {ADMIN_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                          </select>
                        )}
```

Close the `}` before `</td>`:

```jsx
                      </td>
```

- [ ] **Step 5: Commit**

```bash
git add web/static/components/AdminOrders.jsx
git commit -m "feat(admin): add guest orders tab with phone display in AdminOrders"
```

---

## Task 13: Manual Smoke Test

- [ ] **Step 1: Start the app**

```bash
docker compose up
```

- [ ] **Step 1b: Ensure `SITE_URL` is set in `.env`**

`SITE_URL` is used to build the YooKassa `return_url`. Without it the redirect after payment won't work.

```bash
# In .env (or .env.example):
SITE_URL=https://yourdomain.com
```

- [ ] **Step 2: Check landing page**

Open `http://localhost:8000`. Confirm the "⚡ Заказать без регистрации" button appears in the Hero section. Since YooKassa is likely disabled in dev (SHOP_ID=0), the button should appear greyed out and show tooltip on hover.

- [ ] **Step 3: Verify payment-available endpoint**

```bash
curl http://localhost:8000/api/guest-orders/payment-available
# Expected: {"available": false}  (unless SHOP_ID is set)
```

- [ ] **Step 4: Verify admin tab**

Log in as admin, open Admin → Заказы. Confirm the "Обычные / 📞 Гостевые" tab switcher appears. Switch to "Гостевые" — should show empty list initially.

- [ ] **Step 5: Run migration on prod DB (when deploying)**

```bash
python scripts/migrate_guest_orders.py
# Expected: guest_orders table created (or already existed).
```

- [ ] **Step 6: Final full test run**

```bash
docker exec <container> python -m pytest tests/ -v --tb=short
```

Expected: all tests pass.
