# Funnel Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track unique users at each step of the PF Avito order funnel (and future services) and display drop-off as a bar chart in the Telegram admin panel.

**Architecture:** Event-log table `funnel_events` + central `FUNNEL_STEPS` registry in `services/funnel.py`. Each domain handler calls `track_step(user_id, service, step)` at well-defined points. Admin reads aggregates via `get_funnel_stats()` and renders a matplotlib bar chart sent via `answer_photo`.

**Tech Stack:** aiogram 2.25, SQLite (existing schema in `utils/sqlite3.py`), matplotlib 3.10 (already used in `handlers/admin_orders.py`), pytest + `tmp_db` fixture (`tests/conftest.py`).

**Spec:** [docs/superpowers/specs/2026-05-18-funnel-analytics-design.md](../specs/2026-05-18-funnel-analytics-design.md)

---

## Task 1: Add `funnel_events` schema

**Files:**
- Modify: `utils/sqlite3.py` (inside `get_schema_statements()`, after `pending_email_registrations`)
- Test: `tests/unit/test_funnel_schema.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_funnel_schema.py`:

```python
"""Schema test for funnel_events table."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def test_funnel_events_table_exists_with_expected_columns(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(funnel_events)").fetchall()}
    assert cols == {"id", "user_id", "service", "step", "ts"}


def test_funnel_events_indexes_exist(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        idx_names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='funnel_events'"
            ).fetchall()
        }
    assert "idx_funnel_service_ts" in idx_names
    assert "idx_funnel_service_step_user" in idx_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_funnel_schema.py -v`
Expected: FAIL with "no such table: funnel_events" or `PRAGMA` returning empty set.

- [ ] **Step 3: Add table + indexes to `get_schema_statements()`**

In `utils/sqlite3.py`, inside `get_schema_statements()`, after the `pending_email_registrations` tuple (around line 980), add:

```python
        (
            "funnel_events",
            "CREATE TABLE IF NOT EXISTS funnel_events("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "service TEXT NOT NULL,"
            "step TEXT NOT NULL,"
            "ts TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))",
            5,
        ),
```

The `tmp_db` fixture only runs the `CREATE TABLE` statements; indexes won't be created by the existing loop. So we need a separate `CREATE INDEX` step. The simplest approach: add a small helper that the fixture also calls. Update `create_db()` and the `tmp_db` fixture together.

In `utils/sqlite3.py`, **add this new function above `create_db()`** (around line 1010):

```python
def get_index_statements() -> list[str]:
    """Index DDL applied after tables. Idempotent."""
    return [
        "CREATE INDEX IF NOT EXISTS idx_funnel_service_ts "
        "ON funnel_events(service, ts)",
        "CREATE INDEX IF NOT EXISTS idx_funnel_service_step_user "
        "ON funnel_events(service, step, user_id)",
    ]
```

Modify `create_db()` to apply indexes after tables — add this just before the final `apply_phase2_migrations()` call:

```python
        for ddl in get_index_statements():
            con.execute(ddl)
        con.commit()
```

- [ ] **Step 4: Update `tmp_db` fixture to create indexes too**

In `tests/conftest.py`, modify the `tmp_db` fixture (around line 85) to also apply indexes. Change:

```python
    with sqlite3.connect(db_path) as con:
        for _table, ddl, _cols in get_schema_statements():
            con.execute(ddl)
        con.commit()
```

To:

```python
    from utils.sqlite3 import get_index_statements
    with sqlite3.connect(db_path) as con:
        for _table, ddl, _cols in get_schema_statements():
            con.execute(ddl)
        for idx_ddl in get_index_statements():
            con.execute(idx_ddl)
        con.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_funnel_schema.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Run the full test suite to make sure nothing broke**

Run: `pytest -q`
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add utils/sqlite3.py tests/conftest.py tests/unit/test_funnel_schema.py
git commit -m "feat: add funnel_events table + indexes for funnel analytics"
```

---

## Task 2: `services/funnel.py` — registry + `track_step()`

**Files:**
- Create: `services/funnel.py`
- Test: `tests/unit/test_funnel.py` (new)

- [ ] **Step 1: Write failing tests for the registry and `track_step`**

Create `tests/unit/test_funnel.py`:

```python
"""Tests for services.funnel."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_funnel_steps_contains_pf_avito():
    from services.funnel import FUNNEL_STEPS

    assert "pf_avito" in FUNNEL_STEPS
    assert FUNNEL_STEPS["pf_avito"] == [
        "view_tariff",
        "select_period",
        "select_count",
        "links_valid",
        "contact_chosen",
        "order_confirmed",
    ]


def test_track_step_inserts_row(tmp_db: Path):
    from services.funnel import track_step

    track_step(user_id=42, service="pf_avito", step="view_tariff")

    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, service, step, ts FROM funnel_events"
        ).fetchall()
    assert len(rows) == 1
    user_id, service, step, ts = rows[0]
    assert user_id == 42
    assert service == "pf_avito"
    assert step == "view_tariff"
    # ts must parse as ISO UTC
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed).total_seconds() == 0


def test_track_step_invalid_service_raises(tmp_db: Path):
    from services.funnel import track_step

    with pytest.raises(ValueError):
        track_step(user_id=1, service="nonexistent", step="view_tariff")


def test_track_step_invalid_step_raises(tmp_db: Path):
    from services.funnel import track_step

    with pytest.raises(ValueError):
        track_step(user_id=1, service="pf_avito", step="not_a_step")


def test_track_step_multiple_events_same_user(tmp_db: Path):
    from services.funnel import track_step

    track_step(user_id=7, service="pf_avito", step="view_tariff")
    track_step(user_id=7, service="pf_avito", step="view_tariff")
    track_step(user_id=7, service="pf_avito", step="select_period")

    with sqlite3.connect(tmp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM funnel_events").fetchone()[0]
    assert count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_funnel.py -v`
Expected: ImportError / ModuleNotFoundError (no `services.funnel`).

- [ ] **Step 3: Implement `services/funnel.py`**

Create `services/funnel.py`:

```python
"""Universal funnel analytics: event log + step registry.

Pipeline pattern: each user-facing service declares its ordered list of steps
in FUNNEL_STEPS, then domain handlers call track_step(user_id, service, step)
at well-defined progression points. Reads are aggregate-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services.db import connect

# Ordered list of steps for each service. Add a new entry to plug a new
# service into funnel analytics — no schema change required.
FUNNEL_STEPS: dict[str, list[str]] = {
    "pf_avito": [
        "view_tariff",
        "select_period",
        "select_count",
        "links_valid",
        "contact_chosen",
        "order_confirmed",
    ],
}

# Human-readable labels for admin UI. Keys must match FUNNEL_STEPS.
SERVICE_LABELS: dict[str, str] = {
    "pf_avito": "🚀 Накрутка ПФ Авито",
}


def _validate(service: str, step: str | None = None) -> None:
    if service not in FUNNEL_STEPS:
        raise ValueError(f"Unknown service: {service!r}")
    if step is not None and step not in FUNNEL_STEPS[service]:
        raise ValueError(f"Unknown step {step!r} for service {service!r}")


def track_step(user_id: int, service: str, step: str) -> None:
    """Record one funnel event. Never raises on duplicate user/step pair."""
    _validate(service, step)
    ts = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO funnel_events (user_id, service, step, ts) "
            "VALUES (?, ?, ?, ?)",
            (user_id, service, step, ts),
        )
        con.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_funnel.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/funnel.py tests/unit/test_funnel.py
git commit -m "feat(funnel): add FUNNEL_STEPS registry and track_step()"
```

---

## Task 3: `get_funnel_stats()` — aggregation with date filter

**Files:**
- Modify: `services/funnel.py`
- Test: `tests/unit/test_funnel.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_funnel.py`:

```python
from datetime import timedelta


def _insert_event(db_path: Path, user_id: int, service: str, step: str, ts: datetime) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO funnel_events (user_id, service, step, ts) VALUES (?, ?, ?, ?)",
            (user_id, service, step, ts.isoformat()),
        )
        con.commit()


def test_get_funnel_stats_empty(tmp_db: Path):
    from services.funnel import FUNNEL_STEPS, get_funnel_stats

    result = get_funnel_stats("pf_avito")
    assert [r["step"] for r in result] == FUNNEL_STEPS["pf_avito"]
    assert all(r["users"] == 0 for r in result)
    assert result[0]["drop_off_pct"] is None
    assert all(r["drop_off_pct"] is None for r in result)  # prev=0 → None


def test_get_funnel_stats_distinct_users(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    # user 1 reaches view_tariff twice and select_period once
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "select_period", now)
    # user 2 only reaches view_tariff
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)

    result = {r["step"]: r for r in get_funnel_stats("pf_avito")}
    assert result["view_tariff"]["users"] == 2
    assert result["select_period"]["users"] == 1
    assert result["select_count"]["users"] == 0


def test_get_funnel_stats_drop_off_percentages(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    # 10 users at view_tariff, 8 at select_period, 4 at select_count
    for uid in range(1, 11):
        _insert_event(tmp_db, uid, "pf_avito", "view_tariff", now)
    for uid in range(1, 9):
        _insert_event(tmp_db, uid, "pf_avito", "select_period", now)
    for uid in range(1, 5):
        _insert_event(tmp_db, uid, "pf_avito", "select_count", now)

    result = {r["step"]: r for r in get_funnel_stats("pf_avito")}
    assert result["view_tariff"]["drop_off_pct"] is None
    assert result["select_period"]["drop_off_pct"] == 20.0  # (10-8)/10
    assert result["select_count"]["drop_off_pct"] == 50.0   # (8-4)/8


def test_get_funnel_stats_date_filter(tmp_db: Path):
    from services.funnel import get_funnel_stats

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", old)
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)

    # Filter: only events in the last 7 days
    result = {
        r["step"]: r
        for r in get_funnel_stats("pf_avito", from_dt=now - timedelta(days=7), to_dt=now + timedelta(seconds=1))
    }
    assert result["view_tariff"]["users"] == 1


def test_get_funnel_stats_invalid_service(tmp_db: Path):
    from services.funnel import get_funnel_stats

    with pytest.raises(ValueError):
        get_funnel_stats("nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_funnel.py -v`
Expected: failures for the new tests (`get_funnel_stats` not defined).

- [ ] **Step 3: Implement `get_funnel_stats()`**

Append to `services/funnel.py`:

```python
def get_funnel_stats(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[dict]:
    """Aggregate distinct-user counts per step, in FUNNEL_STEPS order.

    Returns: [{"step": str, "users": int, "drop_off_pct": float | None}, ...]
    Steps with no events appear with users=0. drop_off_pct is None for the
    first step and whenever the previous step had 0 users.
    """
    _validate(service)
    sql = "SELECT step, COUNT(DISTINCT user_id) AS users FROM funnel_events WHERE service = ?"
    params: list = [service]
    if from_dt is not None:
        sql += " AND ts >= ?"
        params.append(from_dt.isoformat())
    if to_dt is not None:
        sql += " AND ts <= ?"
        params.append(to_dt.isoformat())
    sql += " GROUP BY step"

    with connect() as con:
        rows = con.execute(sql, params).fetchall()
    counts: dict[str, int] = {row["step"]: int(row["users"]) for row in rows}

    out: list[dict] = []
    prev: int | None = None
    for step in FUNNEL_STEPS[service]:
        users = counts.get(step, 0)
        if prev is None or prev == 0:
            drop_off_pct: float | None = None
        else:
            drop_off_pct = round((prev - users) / prev * 100, 1)
        out.append({"step": step, "users": users, "drop_off_pct": drop_off_pct})
        prev = users
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_funnel.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/funnel.py tests/unit/test_funnel.py
git commit -m "feat(funnel): add get_funnel_stats() with date filter and drop-off"
```

---

## Task 4: `render_chart()` — PNG generation

**Files:**
- Modify: `services/funnel.py`
- Test: `tests/unit/test_funnel.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_funnel.py`:

```python
def test_render_chart_returns_png_bytesio(tmp_db: Path):
    from services.funnel import render_chart

    now = datetime.now(timezone.utc)
    _insert_event(tmp_db, 1, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 2, "pf_avito", "view_tariff", now)
    _insert_event(tmp_db, 1, "pf_avito", "select_period", now)

    buf = render_chart("pf_avito", title="Test funnel")
    head = buf.read(8)
    # PNG magic bytes
    assert head[:4] == b"\x89PNG"
    buf.seek(0)
    # File-like object positioned at the start for downstream callers
    assert buf.tell() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_funnel.py::test_render_chart_returns_png_bytesio -v`
Expected: FAIL with `render_chart` not defined.

- [ ] **Step 3: Implement `render_chart()`**

At the top of `services/funnel.py`, add the import:

```python
import io

import matplotlib

matplotlib.use("Agg")  # headless backend — required when no display is available
import matplotlib.pyplot as plt  # noqa: E402
```

Append to `services/funnel.py`:

```python
def render_chart(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    title: str,
) -> io.BytesIO:
    """Render a horizontal bar chart of the funnel as PNG. Returns a BytesIO
    positioned at offset 0 (ready for aiogram answer_photo)."""
    stats = get_funnel_stats(service, from_dt=from_dt, to_dt=to_dt)
    steps = [r["step"] for r in stats]
    users = [r["users"] for r in stats]

    fig, ax = plt.subplots(figsize=(10, max(3, 0.7 * len(steps) + 1)))
    y = list(range(len(steps)))
    ax.barh(y, users, color="#4a90e2")
    ax.set_yticks(y)
    ax.set_yticklabels(steps)
    ax.invert_yaxis()  # first step on top
    ax.set_xlabel("Уникальных пользователей")
    ax.set_title(title)

    for i, row in enumerate(stats):
        label = str(row["users"])
        if row["drop_off_pct"] is not None:
            label += f"  (-{row['drop_off_pct']}%)"
        ax.text(row["users"], i, "  " + label, va="center")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_funnel.py::test_render_chart_returns_png_bytesio -v`
Expected: PASS.

- [ ] **Step 5: Run full funnel test suite**

Run: `pytest tests/unit/test_funnel.py tests/unit/test_funnel_schema.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/funnel.py tests/unit/test_funnel.py
git commit -m "feat(funnel): render_chart() generates horizontal bar PNG"
```

---

## Task 5: Instrument PF handlers — add `user_id` and `track_step()` calls

**Files:**
- Modify: `handlers/pf_order.py` (6 instrumentation points)

This task is mechanical: add `user_id: int` to handler signatures (middleware injects it) and call `track_step()` at the right moments. No new tests in this task — Task 9 has the smoke test.

- [ ] **Step 1: Add import at the top of `handlers/pf_order.py`**

After the other `from utils...` imports, add:

```python
from services.funnel import track_step
```

- [ ] **Step 2: Instrument `tarif()` — step `view_tariff`**

In `handlers/pf_order.py`, modify `tarif()` (line 39). Change the signature:

```python
async def tarif(call: CallbackQuery, state: FSMContext, user_id: int):
```

Inside the function, after `tarif_name = call.data.split(":")[1]` and before the `if tarif_name == "pf":` block, add:

```python
    if tarif_name in {"pf"}:
        track_step(user_id=user_id, service="pf_avito", step="view_tariff")
```

(The `if tarif_name in {"pf"}` gate keeps the function future-proof: when `tarif_name == "yandex_pf"` etc., tracking only fires for services in the registry.)

- [ ] **Step 3: Instrument `pf()` — `select_period` and `select_count`**

In `pf()` (line 72), change the signature:

```python
async def pf(call: CallbackQuery, state: FSMContext, user_id: int):
```

In the `if call_data[1].isdigit():` branch (line 75), at the start of the branch, add:

```python
        track_step(user_id=user_id, service="pf_avito", step="select_period")
```

In the `else:` branch (line 91, where `total_price` is computed), add this immediately AFTER the `async with state.proxy() as data:` block (i.e. after line 101 `data['total_price'] = ...`):

```python
        track_step(user_id=user_id, service="pf_avito", step="select_count")
```

- [ ] **Step 4: Instrument `enter_period_func()`**

In `enter_period_func()` (line 116), change the signature:

```python
async def enter_period_func(message: types.Message, state: FSMContext, user_id: int):
```

In the `if message.text.isdigit() and int(message.text) >= 1:` branch, after `await state.update_data(days=days)` (line 124), add:

```python
        track_step(user_id=user_id, service="pf_avito", step="select_period")
```

- [ ] **Step 5: Instrument `enter_pf_func()`**

In `enter_pf_func()` (line 131), change the signature:

```python
async def enter_pf_func(message: types.Message, state: FSMContext, user_id: int):
```

In the `if message.text.isdigit() and int(message.text) >= 5:` branch, after the `async with state.proxy() as data:` block closes (after line 143 where `data['total_price'] = ...`), add:

```python
        track_step(user_id=user_id, service="pf_avito", step="select_count")
```

- [ ] **Step 6: Instrument `place_order()` — `links_valid`**

In `place_order()` (line 184), change the signature:

```python
async def place_order(message: Message, state: FSMContext, user_id: int):
```

Inside `if links:` block, after `data['total_price'] *= len(data['links'])` (line 191), add:

```python
        track_step(user_id=user_id, service="pf_avito", step="links_valid")
```

Note: `place_order` is also called from `pf()` (line 106) when `links` is already in state. That call needs the `user_id` arg too:

```python
            await place_order(call.message, state, user_id)
```

- [ ] **Step 7: Instrument `order_contact_set()` — `contact_chosen`**

In `order_contact_set()` (line 206), change the signature:

```python
async def order_contact_set(call: CallbackQuery, state: FSMContext, user_id: int):
```

After `data['contact'] = answer` (line 210), and BEFORE the `if 'total_price' in data:` check, add:

```python
    track_step(user_id=user_id, service="pf_avito", step="contact_chosen")
```

- [ ] **Step 8: Instrument `confirm_order()` — `order_confirmed`**

`confirm_order` (line 222) already has `user_id` in its signature. As the first line of the function body, add:

```python
    track_step(user_id=user_id, service="pf_avito", step="order_confirmed")
```

- [ ] **Step 9: Run full test suite — nothing should have broken**

Run: `pytest -q`
Expected: all existing tests still pass.

- [ ] **Step 10: Commit**

```bash
git add handlers/pf_order.py
git commit -m "feat(funnel): instrument PF order handlers with track_step()"
```

---

## Task 6: Funnel admin keyboards

**Files:**
- Modify: `keyboards/inline_keyboards.py` — add two helpers, add button to `admin()`
- Test: `tests/unit/test_admin_funnel_keyboards.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_admin_funnel_keyboards.py`:

```python
"""Tests for funnel keyboards."""
from __future__ import annotations


def test_funnel_service_kb_has_button_per_service():
    from keyboards.inline_keyboards import funnel_service_kb

    kb = funnel_service_kb()
    flat = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = {b.callback_data for b in flat}
    assert "funnel:pf_avito" in callbacks
    assert any(b.callback_data == "admin_back" for b in flat)


def test_funnel_period_kb_has_four_presets_and_back():
    from keyboards.inline_keyboards import funnel_period_kb

    kb = funnel_period_kb("pf_avito")
    callbacks = {
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    }
    for suffix in ("today", "7d", "30d", "all"):
        assert f"funnel:pf_avito:{suffix}" in callbacks
    assert "funnel_menu" in callbacks  # back to service picker


def test_admin_kb_contains_funnel_button():
    from keyboards.inline_keyboards import admin

    kb = admin()
    callbacks = {
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    }
    assert "funnel_menu" in callbacks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_funnel_keyboards.py -v`
Expected: FAIL — `funnel_service_kb`/`funnel_period_kb` not defined; admin() lacks the button.

- [ ] **Step 3: Add `funnel_service_kb()` and `funnel_period_kb()` to `keyboards/inline_keyboards.py`**

At the end of the file, append:

```python
def funnel_service_kb() -> InlineKeyboardMarkup:
    """Service picker for the funnel admin menu."""
    from services.funnel import FUNNEL_STEPS, SERVICE_LABELS

    kb = InlineKeyboardMarkup()
    for service in FUNNEL_STEPS.keys():
        label = SERVICE_LABELS.get(service, service)
        kb.add(InlineKeyboardButton(text=label, callback_data=f"funnel:{service}"))
    kb.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return kb


def funnel_period_kb(service: str) -> InlineKeyboardMarkup:
    """Period picker for a specific service."""
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="Сегодня", callback_data=f"funnel:{service}:today"),
        InlineKeyboardButton(text="7 дней", callback_data=f"funnel:{service}:7d"),
    )
    kb.row(
        InlineKeyboardButton(text="30 дней", callback_data=f"funnel:{service}:30d"),
        InlineKeyboardButton(text="Всё время", callback_data=f"funnel:{service}:all"),
    )
    kb.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="funnel_menu"))
    return kb
```

- [ ] **Step 4: Add the funnel button to `admin()` in `keyboards/inline_keyboards.py`**

Inside `admin()` (starting at line 446), add a new row after the existing `keyboard.add(...money_by_year...)` block (around line 505). Add:

```python
        keyboard.add(
            InlineKeyboardButton(
                text="📊 Воронка",
                callback_data='funnel_menu'
            )
        )
```

- [ ] **Step 5: Add `admin_back` callback (back-to-admin shortcut) if not present**

Check if a callback `admin_back` is already wired up. Run:

```bash
grep -rn '"admin_back"\|admin_back"' handlers/ keyboards/
```

If `admin_back` callback is NOT handled anywhere in `handlers/`, the back button needs a handler. Add to `handlers/admin_base.py`, after the existing `adminka` handler:

```python
@dp.callback_query_handler(text="admin_back", state='*')
async def admin_back(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    if str(call.from_user.id) in get_admins():
        from keyboards.inline_keyboards import admin
        await call.message.answer("👋 Админ-меню", reply_markup=admin())
        try:
            await call.message.delete()
        except Exception:
            pass
```

If `admin_back` IS already handled, skip this step.

- [ ] **Step 6: Run keyboard tests**

Run: `pytest tests/unit/test_admin_funnel_keyboards.py -v`
Expected: 3 passed.

- [ ] **Step 7: Run full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add keyboards/inline_keyboards.py handlers/admin_base.py tests/unit/test_admin_funnel_keyboards.py
git commit -m "feat(funnel): keyboards + admin menu entry"
```

---

## Task 7: Admin funnel callback handlers

**Files:**
- Create: `handlers/admin_funnel.py`
- Modify: `handlers/__init__.py` — register the new module
- Test: `tests/unit/test_admin_funnel.py` (new)

- [ ] **Step 1: Write failing test for `funnel_menu` (service picker)**

Create `tests/unit/test_admin_funnel.py`:

```python
"""Tests for handlers.admin_funnel."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def _patch_admins(monkeypatch):
    """Make get_admins() return a fixed list inside handlers.admin_funnel."""
    import handlers.admin_funnel as mod  # ensure module loaded before patching

    monkeypatch.setattr(mod, "get_admins", lambda: ["100500"])


@pytest.fixture
def admin_call(_patch_admins):
    call = MagicMock()
    call.from_user.id = 100500
    call.data = "funnel_menu"
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.answer_photo = AsyncMock()
    call.message.delete = AsyncMock()
    return call


@pytest.fixture
def non_admin_call(_patch_admins):
    call = MagicMock()
    call.from_user.id = 999
    call.data = "funnel_menu"
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.answer_photo = AsyncMock()
    return call


@pytest.mark.asyncio
async def test_funnel_menu_shows_service_picker(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_menu

    await funnel_menu(admin_call, state=MagicMock())
    admin_call.message.answer.assert_awaited_once()
    args, kwargs = admin_call.message.answer.call_args
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_funnel_menu_ignores_non_admin(non_admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_menu

    await funnel_menu(non_admin_call, state=MagicMock())
    non_admin_call.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_funnel_service_callback_shows_period_picker(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_service

    admin_call.data = "funnel:pf_avito"
    await funnel_service(admin_call, state=MagicMock())
    admin_call.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_funnel_period_callback_sends_photo(admin_call, tmp_db: Path):
    from handlers.admin_funnel import funnel_period
    from services.funnel import track_step

    # Seed two distinct users, one of them progressing further
    track_step(user_id=1, service="pf_avito", step="view_tariff")
    track_step(user_id=2, service="pf_avito", step="view_tariff")
    track_step(user_id=1, service="pf_avito", step="select_period")

    admin_call.data = "funnel:pf_avito:all"
    await funnel_period(admin_call, state=MagicMock())
    admin_call.message.answer_photo.assert_awaited_once()
    _args, kwargs = admin_call.message.answer_photo.call_args
    caption = kwargs.get("caption", "")
    assert "view_tariff" in caption
    assert "2" in caption  # users at view_tariff
    assert "select_period" in caption
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_admin_funnel.py -v`
Expected: ImportError (no `handlers.admin_funnel`).

- [ ] **Step 3: Implement `handlers/admin_funnel.py`**

Create `handlers/admin_funnel.py`:

```python
"""Admin panel: funnel analytics — service picker + period picker + chart."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery

from data.loader import dp
from keyboards.inline_keyboards import funnel_period_kb, funnel_service_kb
from services.funnel import (
    FUNNEL_STEPS,
    SERVICE_LABELS,
    get_funnel_stats,
    render_chart,
)
from utils.sqlite3 import get_admins

logger = logging.getLogger(__name__)

_PERIOD_LABELS = {
    "today": "сегодня",
    "7d": "7 дней",
    "30d": "30 дней",
    "all": "всё время",
}


def _resolve_period(suffix: str) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    if suffix == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if suffix == "7d":
        return now - timedelta(days=7), now
    if suffix == "30d":
        return now - timedelta(days=30), now
    if suffix == "all":
        return None, None
    raise ValueError(f"Unknown period suffix: {suffix!r}")


def _format_caption(
    service: str,
    period_suffix: str,
    from_dt: datetime | None,
    to_dt: datetime | None,
    stats: list[dict],
) -> str:
    period_label = _PERIOD_LABELS.get(period_suffix, period_suffix)
    if from_dt is not None and to_dt is not None:
        range_str = f"{from_dt.date()} — {to_dt.date()}"
    else:
        range_str = "всё время"
    header = f"{SERVICE_LABELS.get(service, service)} · {period_label} ({range_str})"

    body_lines = []
    width = max(len(r["step"]) for r in stats) + 2
    for r in stats:
        users_str = str(r["users"]).rjust(6)
        line = f"{r['step']:<{width}}{users_str}"
        if r["drop_off_pct"] is not None:
            line += f"  (-{r['drop_off_pct']}%)"
        body_lines.append(line)

    first = stats[0]["users"] if stats else 0
    last = stats[-1]["users"] if stats else 0
    conv_line = ""
    if first > 0:
        conv = round(last / first * 100, 1)
        conv_line = f"\n\nКонверсия в заказ: {conv}%"

    return f"{header}\n\n<pre>{chr(10).join(body_lines)}</pre>{conv_line}"


@dp.callback_query_handler(text="funnel_menu", state='*')
async def funnel_menu(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    await call.message.answer(
        "📊 Воронка — выбери сервис:",
        reply_markup=funnel_service_kb(),
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(
    lambda c: c.data is not None and c.data.startswith("funnel:") and c.data.count(":") == 1,
    state='*',
)
async def funnel_service(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    service = call.data.split(":", 1)[1]
    if service not in FUNNEL_STEPS:
        return
    label = SERVICE_LABELS.get(service, service)
    await call.message.answer(
        f"📊 {label} — выбери период:",
        reply_markup=funnel_period_kb(service),
    )
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")


@dp.callback_query_handler(
    lambda c: c.data is not None and c.data.startswith("funnel:") and c.data.count(":") == 2,
    state='*',
)
async def funnel_period(call: CallbackQuery, state: FSMContext):
    if str(call.from_user.id) not in get_admins():
        return
    _, service, period_suffix = call.data.split(":")
    if service not in FUNNEL_STEPS:
        return
    try:
        from_dt, to_dt = _resolve_period(period_suffix)
    except ValueError:
        return

    stats = get_funnel_stats(service, from_dt=from_dt, to_dt=to_dt)
    period_label = _PERIOD_LABELS.get(period_suffix, period_suffix)
    chart_title = f"Воронка «{SERVICE_LABELS.get(service, service)}» за {period_label}"
    buf = render_chart(service, from_dt=from_dt, to_dt=to_dt, title=chart_title)
    caption = _format_caption(service, period_suffix, from_dt, to_dt, stats)

    await call.message.answer_photo(
        buf,
        caption=caption,
        parse_mode="HTML",
        reply_markup=funnel_period_kb(service),
    )
    buf.close()
    try:
        await call.message.delete()
    except Exception:
        logger.debug("could not delete message")
```

- [ ] **Step 4: Register the new module**

Modify `handlers/__init__.py` to include `admin_funnel`. Change:

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, seo, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings,
    support_web,
    connect,
    commands,  # commands.py has unhandled_callback LAST
)
```

To:

```python
from . import (
    main_start,
    profile, promocodes, pf_order, reviews, seo, refill,
    admin_base, admin_promos, admin_users, admin_broadcast,
    admin_orders, admin_reviews, admin_settings, admin_funnel,
    support_web,
    connect,
    commands,  # commands.py has unhandled_callback LAST
)
```

- [ ] **Step 5: Run admin funnel tests**

Run: `pytest tests/unit/test_admin_funnel.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add handlers/admin_funnel.py handlers/__init__.py tests/unit/test_admin_funnel.py
git commit -m "feat(funnel): admin handlers — service/period pickers + chart"
```

---

## Task 8: Manual smoke check

This is not a code task — it's a verification step. The agent should pause and report back to the user.

- [ ] **Step 1: Verify the bot can start without import errors**

Run: `python -c "import handlers"`
Expected: no errors.

- [ ] **Step 2: Verify schema bootstrap**

Run:

```bash
python -c "from utils.sqlite3 import create_db; create_db()" 2>&1 | tail -5
```

Expected: `database was found (funnel_events | ...)` or `creating...` on first run, no exceptions.

- [ ] **Step 3: Report to user**

Report:

> "Funnel analytics implemented. Verify manually:
> 1. Open admin panel in the bot (`/admin`).
> 2. Click `📊 Воронка`.
> 3. Select `🚀 Накрутка ПФ Авито`.
> 4. Pick a period.
> 5. Expect a PNG bar chart + caption with counts and drop-off %.
>
> If you have any prod traffic that's already gone through the PF flow since these changes deployed, the chart will be non-empty. To smoke-test from scratch: register a test user (with the test data per [project_test_data.md](../../../../../../.claude/projects/-Users-belikov-Documents-pets-bots-telegram-original-avito-pf-bot/memory/project_test_data.md)), walk through the order flow, and confirm rows appear in `funnel_events`."

---

## Self-review notes

- **Spec coverage:** Schema (Task 1), `track_step` + registry (Task 2), `get_funnel_stats` (Task 3), `render_chart` (Task 4), PF instrumentation (Task 5), keyboards (Task 6), admin handlers (Task 7), smoke (Task 8). All seven spec sections covered.
- **Type consistency:** `track_step(user_id, service, step)`, `get_funnel_stats(service, *, from_dt, to_dt)`, `render_chart(service, *, from_dt, to_dt, title)` — names and kwargs identical across all tasks.
- **No placeholders:** every step contains the exact code or command to run.
- **TDD discipline:** tests precede implementation for Tasks 1–4, 6, 7; Task 5 is instrumentation (no behavior change for funnel users, smoke-tested in Task 8); Task 8 is manual.
