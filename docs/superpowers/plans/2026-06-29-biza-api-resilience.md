# biza API Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the biza executor-API integration storm-proof: global 60/min rate limit, circuit breaker with cooldown on 429/500, and a per-link attempt cap (2 → manual).

**Architecture:** Two new stateless-ish in-process singletons — a token-bucket `RateLimiter` (consulted inside `submit_link`, so every caller is paced) and a `CircuitBreaker` (held by the dispatcher; opens after N consecutive API errors, blocks the pass during a cooldown). A new `order_links.dispatch_attempts` column persists per-link retry counts; the dispatcher flips a link to `manual` once it reaches `BIZA_MAX_ATTEMPTS`. The candidate query is tightened so `manual` links are excluded (otherwise the cap is bypassed).

**Tech Stack:** Python 3, SQLite (`utils/sqlite3.py` schema + `apply_phase2_migrations`), `requests`, pytest. Tests run in Docker.

**Spec:** `docs/superpowers/specs/2026-06-29-biza-api-resilience-design.md`

**Test command (Docker):**
- Full suite: `make test`
- Targeted file: `docker compose --profile test run --rm test pytest tests/unit/<file>.py -v`

**Commit conventions:** Conventional Commits, English, **no** `Co-Authored-By` trailer, no tool watermark (team convention, skill `octopus:git-conventions`).

---

## File Structure

- Create `services/rate_limiter.py` — token-bucket limiter + module singleton + `acquire()`/`reset()`.
- Create `services/circuit_breaker.py` — `CircuitBreaker` class.
- Modify `data/config.py` — 4 new env-driven settings.
- Modify `tests/conftest.py` — mirror the 4 settings in the config stub.
- Modify `utils/sqlite3.py` — add `dispatch_attempts` to `order_links` DDL + idempotent migration.
- Modify `services/pf_executor_api.py` — `rate_limiter.acquire()` before the POST.
- Modify `services/order_links_dispatcher.py` — attempt-cap + circuit-breaker wiring; tighten candidate query.
- Create `tests/unit/test_rate_limiter.py`, `tests/unit/test_circuit_breaker.py`, `tests/unit/test_dispatcher_attempt_cap.py`, `tests/unit/test_dispatcher_circuit_breaker.py`.

---

## Task 1: Config settings + test stub

**Files:**
- Modify: `data/config.py` (after `PF_DEFAULT_START_HOUR` block, ~line 116-118)
- Modify: `tests/conftest.py` (`_make_config_stub`, after `stub.PF_DEFAULT_START_HOUR = 0`, ~line 77)

- [ ] **Step 1: Add settings to `data/config.py`**

Append after the `PF_DEFAULT_START_HOUR` assignment:

```python
# === biza API resilience (rate limit / circuit breaker / attempt cap) ===
# biza режет при >60 req/min (HTTP 429). Лимитер не даёт превысить.
BIZA_MAX_PER_MIN: int = max(1, int(os.getenv("BIZA_MAX_PER_MIN", "60")))
# Стоп-кран: сколько ошибок подряд (429/500/сеть) до открытия.
BIZA_BREAKER_ERRORS: int = max(1, int(os.getenv("BIZA_BREAKER_ERRORS", "3")))
# Сколько минут не трогать biza после открытия стоп-крана.
BIZA_COOLDOWN_MIN: int = max(1, int(os.getenv("BIZA_COOLDOWN_MIN", "30")))
# Потолок попыток авто-отправки на ссылку; дальше → manual.
BIZA_MAX_ATTEMPTS: int = max(1, int(os.getenv("BIZA_MAX_ATTEMPTS", "2")))
```

- [ ] **Step 2: Mirror in the test config stub**

In `tests/conftest.py`, inside `_make_config_stub()`, add after `stub.PF_DEFAULT_START_HOUR = 0`:

```python
    stub.BIZA_MAX_PER_MIN = 60
    stub.BIZA_BREAKER_ERRORS = 3
    stub.BIZA_COOLDOWN_MIN = 30
    stub.BIZA_MAX_ATTEMPTS = 2
```

- [ ] **Step 3: Add an autouse fixture that resets the biza singletons**

The rate limiter and circuit breaker are module-level singletons; without resetting, state leaks between tests. Append to `tests/conftest.py` (module level, after the `tmp_db` fixture). Imports are lazy + guarded so this is a no-op until those modules exist (Tasks 3/6):

```python
@pytest.fixture(autouse=True)
def _reset_biza_singletons():
    """Сбрасывает rate limiter и circuit breaker до и после каждого теста."""
    def _do():
        try:
            from services.order_links_dispatcher import _breaker
            _breaker.reset()
        except Exception:
            pass
        try:
            from services import rate_limiter
            rate_limiter.reset()
        except Exception:
            pass
    _do()
    yield
    _do()
```

- [ ] **Step 4: Sanity-check import**

Run: `docker compose --profile test run --rm test python -c "from data import config; print(config.BIZA_MAX_PER_MIN, config.BIZA_BREAKER_ERRORS, config.BIZA_COOLDOWN_MIN, config.BIZA_MAX_ATTEMPTS)"`
Expected: `60 3 30 2`

- [ ] **Step 5: Commit**

```bash
git add data/config.py tests/conftest.py
git commit -m "feat(biza): add rate-limit/breaker/attempt-cap config knobs"
```

---

## Task 2: `dispatch_attempts` column + migration

**Files:**
- Modify: `utils/sqlite3.py` — `order_links` DDL in `get_schema_statements()` (~line 956-972) and `apply_phase2_migrations()` (~line 1038, near the `orders` block)
- Test: `tests/unit/test_dispatcher_attempt_cap.py` (migration assertion lives here too)

- [ ] **Step 1: Write the failing migration test**

Create `tests/unit/test_dispatcher_attempt_cap.py`:

```python
"""Потолок попыток авто-отправки: 2 неудачи → manual; + миграция колонки."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso


def test_order_links_has_dispatch_attempts_column(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(order_links)").fetchall()}
    assert "dispatch_attempts" in cols
```

- [ ] **Step 2: Run it to verify it fails**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_attempt_cap.py::test_order_links_has_dispatch_attempts_column -v`
Expected: FAIL — `dispatch_attempts` not in cols.

- [ ] **Step 3: Add the column to the schema DDL**

In `utils/sqlite3.py`, in `get_schema_statements()`, the `order_links` entry — add `dispatch_attempts` after `created_at` and bump the column count `12` → `13`:

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
            "dispatch_attempts INTEGER NOT NULL DEFAULT 0,"
            "FOREIGN KEY (order_id) REFERENCES orders(increment))",
            13,
        ),
```

- [ ] **Step 4: Add the idempotent migration**

In `apply_phase2_migrations()`, after the `orders` column block (after the `start_date` block, before the `auth_providers.verified` block), add:

```python
        # === order_links.dispatch_attempts (per-link auto retry counter) ===
        existing_ol = {row['name'] for row in con.execute("PRAGMA table_info(order_links)").fetchall()}
        if 'dispatch_attempts' not in existing_ol:
            con.execute("ALTER TABLE order_links ADD COLUMN dispatch_attempts INTEGER NOT NULL DEFAULT 0")
            print("order_links.dispatch_attempts added (existing rows defaulted to 0)")
```

- [ ] **Step 5: Run the migration test to verify it passes**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_attempt_cap.py::test_order_links_has_dispatch_attempts_column -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_dispatcher_attempt_cap.py
git commit -m "feat(db): add order_links.dispatch_attempts column + migration"
```

---

## Task 3: RateLimiter component

**Files:**
- Create: `services/rate_limiter.py`
- Test: `tests/unit/test_rate_limiter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rate_limiter.py`:

```python
"""Token-bucket RateLimiter: не выдаёт больше ёмкости за окно, распределяет во времени."""
from services.rate_limiter import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, dur):
        # эмулируем течение времени вместо реального ожидания
        self.slept += dur
        self.t += dur


def test_initial_burst_up_to_capacity_is_instant():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    assert clk.slept == 0.0  # стартовый бакет полон → первые 60 мгновенно


def test_over_capacity_waits_for_refill():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    rl.acquire()  # 61-й — должен подождать ~1с (60/мин = 1 токен/сек)
    assert abs(clk.slept - 1.0) < 1e-6


def test_reset_refills_bucket():
    clk = FakeClock()
    rl = RateLimiter(60, monotonic=clk.monotonic, sleep=clk.sleep)
    for _ in range(60):
        rl.acquire()
    rl.reset()
    rl.acquire()  # снова мгновенно
    assert clk.slept == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_rate_limiter.py -v`
Expected: FAIL — `No module named 'services.rate_limiter'`.

- [ ] **Step 3: Implement `services/rate_limiter.py`**

```python
"""Глобальный ограничитель темпа отправок в biza (token bucket).

biza режет при >60 запросов/мин (HTTP 429). Лимитер раздаёт «слоты» с
постоянной скоростью; acquire() блокирует вызывающего, пока слот не освободится.
Один процесс-синглтон — общий для диспетчера, force_dispatch и ручных прогонов.
Часы/сон инъектируются для тестов.
"""
from __future__ import annotations

import threading
import time

from data import config


class RateLimiter:
    def __init__(self, max_per_minute: int, *, monotonic=time.monotonic, sleep=time.sleep):
        self._capacity = float(max(1, int(max_per_minute)))
        self._refill_per_sec = self._capacity / 60.0
        self._tokens = self._capacity
        self._monotonic = monotonic
        self._sleep = sleep
        self._last = monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._last) * self._refill_per_sec,
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._refill_per_sec
            self._sleep(wait)

    def reset(self) -> None:
        with self._lock:
            self._tokens = self._capacity
            self._last = self._monotonic()


_limiter = RateLimiter(config.BIZA_MAX_PER_MIN)


def acquire() -> None:
    _limiter.acquire()


def reset() -> None:
    _limiter.reset()
```

- [ ] **Step 4: Run to verify they pass**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_rate_limiter.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/rate_limiter.py tests/unit/test_rate_limiter.py
git commit -m "feat(biza): add token-bucket rate limiter"
```

---

## Task 4: CircuitBreaker component

**Files:**
- Create: `services/circuit_breaker.py`
- Test: `tests/unit/test_circuit_breaker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_circuit_breaker.py`:

```python
"""CircuitBreaker: открывается после N ошибок подряд, держит cooldown, успех закрывает."""
from services.circuit_breaker import CircuitBreaker


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


def test_opens_after_max_consecutive_errors():
    clk = FakeClock()
    cb = CircuitBreaker(3, cooldown_seconds=100, monotonic=clk.monotonic)
    assert cb.allow() is True
    cb.record_error(); cb.record_error()
    assert cb.allow() is True            # 2 < 3 — ещё закрыт
    cb.record_error()                    # 3-я → открывается
    assert cb.allow() is False


def test_cooldown_expires():
    clk = FakeClock()
    cb = CircuitBreaker(1, cooldown_seconds=100, monotonic=clk.monotonic)
    cb.record_error()                    # открылся в t=0 до t=100
    assert cb.allow() is False
    clk.t = 100.0
    assert cb.allow() is True            # cooldown истёк


def test_success_resets_consecutive():
    clk = FakeClock()
    cb = CircuitBreaker(3, cooldown_seconds=100, monotonic=clk.monotonic)
    cb.record_error(); cb.record_error()
    cb.record_success()                  # сброс
    cb.record_error(); cb.record_error()
    assert cb.allow() is True            # снова только 2 подряд
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_circuit_breaker.py -v`
Expected: FAIL — `No module named 'services.circuit_breaker'`.

- [ ] **Step 3: Implement `services/circuit_breaker.py`**

```python
"""Стоп-кран для отправок в biza.

Считает ошибки подряд; после max_consecutive_errors открывается и держит
cooldown (allow()==False). Любой успех закрывает. Состояние in-process —
при рестарте сбрасывается (допустимо). Часы инъектируются для тестов.
"""
from __future__ import annotations

import threading
import time


class CircuitBreaker:
    def __init__(self, max_consecutive_errors: int, cooldown_seconds: float,
                 *, monotonic=time.monotonic):
        self._max = max(1, int(max_consecutive_errors))
        self._cooldown = float(cooldown_seconds)
        self._monotonic = monotonic
        self._consecutive = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            return self._monotonic() >= self._open_until

    def record_error(self) -> None:
        with self._lock:
            self._consecutive += 1
            if self._consecutive >= self._max:
                self._open_until = self._monotonic() + self._cooldown

    def record_success(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0

    def reset(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0
```

- [ ] **Step 4: Run to verify they pass**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_circuit_breaker.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/circuit_breaker.py tests/unit/test_circuit_breaker.py
git commit -m "feat(biza): add circuit breaker"
```

---

## Task 5: Wire rate limiter into `submit_link`

**Files:**
- Modify: `services/pf_executor_api.py` (imports ~line 11-14; inside `submit_link`, just before `_session.post`, ~line 71-73)
- Test: `tests/unit/test_submit_link_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_submit_link_rate_limit.py`:

```python
"""submit_link зовёт rate_limiter.acquire() перед POST."""
from unittest.mock import patch

from services.pf_executor_api import submit_link


def test_submit_link_acquires_rate_limit_before_post():
    order = {"increment": 1, "position_name": "3/10", "start_date": None}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"success": True, "data": {"task_ids": ["ext-1"]}}

    with patch("services.pf_executor_api.config.BIZA_API_KEY", "k"), \
         patch("services.pf_executor_api.rate_limiter.acquire") as acq, \
         patch("services.pf_executor_api._session.post", return_value=FakeResp()) as post:
        ext = submit_link("https://avito.ru/x_1", order, search_phrase="q")

    assert ext == "ext-1"
    acq.assert_called_once()
    # acquire должен сработать ДО POST
    assert acq.call_count == 1 and post.call_count == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_submit_link_rate_limit.py -v`
Expected: FAIL — `module 'services.pf_executor_api' has no attribute 'rate_limiter'`.

- [ ] **Step 3: Implement the wiring**

In `services/pf_executor_api.py`, add to imports (after `from services.exceptions import ...`):

```python
from services import rate_limiter
```

Inside `submit_link`, immediately before the `try:`/`_session.post` block (after `headers = {...}`), add:

```python
    # Глобальный лимит 60/мин — не превышаем, иначе biza отвечает 429.
    rate_limiter.acquire()
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_submit_link_rate_limit.py -v`
Expected: PASS

- [ ] **Step 5: Regression — existing executor tests still green**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_pf_executor_payload_cutoff.py tests/unit/test_pf_executor_api_real.py -v`
Expected: PASS (limiter starts full → no added latency)

- [ ] **Step 6: Commit**

```bash
git add services/pf_executor_api.py tests/unit/test_submit_link_rate_limit.py
git commit -m "feat(biza): pace submit_link through the rate limiter"
```

---

## Task 6: Per-link attempt cap → manual (dispatcher)

**Files:**
- Modify: `services/order_links_dispatcher.py` — `dispatch_pending_links` candidate query (~line 46-50); `_dispatch_one` `except ExecutorAPIError` branch (~line 111-120)
- Test: `tests/unit/test_dispatcher_attempt_cap.py` (extend from Task 2)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_dispatcher_attempt_cap.py`:

```python
def _seed(tmp_db, n=1):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/10', 'paid', ?)", (now_iso(),))
        oid = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=oid, urls=[f"u{i}" for i in range(n)])
        con.commit()
    return oid


def test_first_api_error_keeps_pending_auto_increments_attempts(tmp_db):
    oid = _seed(tmp_db, 1)
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    link = list_links(oid)[0]
    assert link["status"] == "pending"
    assert link["delivery_mode"] == "auto"
    assert link["dispatch_attempts"] == 1


def test_second_api_error_flips_to_manual(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import dispatch_pending_links
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        dispatch_pending_links(oid)   # attempts -> 1
        dispatch_pending_links(oid)   # attempts -> 2 → manual
    link = list_links(oid)[0]
    assert link["status"] == "pending"
    assert link["delivery_mode"] == "manual"
    assert link["dispatch_attempts"] == 2


def test_capped_manual_link_not_redispatched(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import dispatch_pending_links
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")):
        dispatch_pending_links(oid)
        dispatch_pending_links(oid)   # → manual (attempts=2)
        with patch("services.order_links_dispatcher.submit_link") as submit3:
            dispatch_pending_links(oid)   # уже manual — не должен сабмититься
            submit3.assert_not_called()
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_attempt_cap.py -v`
Expected: FAIL — `dispatch_attempts` stays 0 (no increment) / link not flipped to manual.

- [ ] **Step 3: Tighten the candidate query**

In `services/order_links_dispatcher.py`, in `dispatch_pending_links`, change the candidate SELECT to exclude `manual` (so capped→manual links are not re-picked, honoring the module docstring):

```python
        rows = con.execute(
            "SELECT id FROM order_links "
            "WHERE order_id=? AND status='pending' "
            "AND (delivery_mode IS NULL OR delivery_mode='auto')",
            (order_id,),
        ).fetchall()
        candidates = [r["id"] for r in rows]
```

- [ ] **Step 4: Implement the attempt-cap branch**

In `_dispatch_one`, replace the `except ExecutorAPIError:` block (the one that currently sets `delivery_mode='auto'` for retry) with a call to a new helper:

```python
    except ExecutorAPIError:
        # Временный сбой biza (429/500/сеть). Считаем попытку: после
        # BIZA_MAX_ATTEMPTS уводим ссылку в manual, иначе оставляем pending+auto.
        _breaker.record_error()
        _bump_attempts_or_manual(link_id)
        return
```

Add the import near the top (after the existing imports):

```python
from data import config
from services.circuit_breaker import CircuitBreaker
```

Add the module-level breaker + helper (place after `logger = logging.getLogger(__name__)`):

```python
_breaker = CircuitBreaker(
    config.BIZA_BREAKER_ERRORS, config.BIZA_COOLDOWN_MIN * 60
)


def _bump_attempts_or_manual(link_id: int) -> None:
    """+1 к dispatch_attempts; при достижении BIZA_MAX_ATTEMPTS → manual."""
    with connect() as con:
        row = con.execute(
            "SELECT dispatch_attempts FROM order_links "
            "WHERE id=? AND status='pending'",
            (link_id,),
        ).fetchone()
        if row is None:
            return  # уже не pending — гонка
        attempts = (row["dispatch_attempts"] or 0) + 1
        mode = "manual" if attempts >= config.BIZA_MAX_ATTEMPTS else "auto"
        con.execute(
            "UPDATE order_links SET dispatch_attempts=?, delivery_mode=? "
            "WHERE id=? AND status='pending'",
            (attempts, mode, link_id),
        )
        con.commit()
```

Also add `record_success()` on the success path: in `_dispatch_one`, right after `external_id = submit_link(...)` succeeds and before `mark_in_work` (i.e., at the start of the success block), add:

```python
    _breaker.record_success()
```

- [ ] **Step 5: Run the attempt-cap tests**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_attempt_cap.py -v`
Expected: PASS (4 passed — incl. migration test from Task 2)

- [ ] **Step 6: Regression — existing dispatcher tests still green**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_order_links_dispatcher.py tests/unit/test_order_links_dispatcher_auto.py tests/unit/test_order_links_dispatcher_retry.py -v`
Expected: PASS. (`test_dispatch_classifier_auto_api_error_keeps_pending_for_retry` still passes: first error → attempts=1 < 2 → pending+auto.)

- [ ] **Step 7: Commit**

```bash
git add services/order_links_dispatcher.py tests/unit/test_dispatcher_attempt_cap.py
git commit -m "feat(biza): cap per-link auto retries at 2, then fall back to manual"
```

---

## Task 7: Circuit-breaker integration in the dispatcher

**Files:**
- Modify: `services/order_links_dispatcher.py` — `dispatch_pending_links` loop (~line 53-59), `dispatch_for_paid_orders` (~line 132-153)
- Test: `tests/unit/test_dispatcher_circuit_breaker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_dispatcher_circuit_breaker.py`:

```python
"""Стоп-кран в диспетчере: после N ошибок подряд проход прерывается; cooldown пропускает тики."""
import sqlite3
from unittest.mock import patch

from services.db import connect
from services.order_links import create_links, list_links
from services.exceptions import ExecutorAPIError
from utils.dates import now_iso

# Сброс _breaker/rate_limiter между тестами обеспечивает autouse-фикстура
# _reset_biza_singletons из conftest.py (Task 1).


def _seed(tmp_db, n):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/10', 'paid', ?)", (now_iso(),))
        oid = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=oid, urls=[f"u{i}" for i in range(n)])
        con.commit()
    return oid


def test_breaker_aborts_pass_after_consecutive_errors(tmp_db):
    # 5 ссылок, submit_link всегда падает. Брейкер открывается на 3-й → проход
    # прерывается, submit вызван ровно BIZA_BREAKER_ERRORS (3) раз.
    oid = _seed(tmp_db, 5)
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               side_effect=ExecutorAPIError("500")) as submit:
        from services.order_links_dispatcher import dispatch_pending_links
        dispatch_pending_links(oid)
    assert submit.call_count == 3


def test_dispatch_for_paid_orders_skips_when_breaker_open(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import _breaker, dispatch_for_paid_orders
    # вручную открываем брейкер
    for _ in range(3):
        _breaker.record_error()
    assert _breaker.allow() is False
    with patch("services.order_links_dispatcher.dispatch_pending_links") as dpl:
        handled = dispatch_for_paid_orders()
    assert handled == 0
    dpl.assert_not_called()


def test_success_resets_breaker(tmp_db):
    oid = _seed(tmp_db, 1)
    from services.order_links_dispatcher import _breaker, dispatch_pending_links
    _breaker.record_error(); _breaker.record_error()
    with patch("services.order_links_dispatcher.classify",
               return_value=("auto", "q")), \
         patch("services.order_links_dispatcher.submit_link",
               return_value="ext-9"):
        dispatch_pending_links(oid)
    assert _breaker.allow() is True
    # счётчик обнулён: 2 новые ошибки не открывают (нужно 3 подряд)
    _breaker.record_error(); _breaker.record_error()
    assert _breaker.allow() is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_circuit_breaker.py -v`
Expected: FAIL — pass not aborted (submit called 5×); `dispatch_for_paid_orders` still calls `dispatch_pending_links`.

- [ ] **Step 3: Guard `dispatch_pending_links` loop with the breaker**

In `services/order_links_dispatcher.py`, in `dispatch_pending_links`, change the candidate loop to bail when the breaker opens:

```python
    for link_id in candidates:
        if not _breaker.allow():
            logger.warning(
                "dispatch_pending_links: circuit open, abort order %s", order_id
            )
            return
        try:
            _dispatch_one(link_id, order_d)
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "dispatch_pending_links: link %s failed", link_id
            )
```

- [ ] **Step 4: Guard `dispatch_for_paid_orders` with the breaker**

Replace the body of `dispatch_for_paid_orders()` order loop with a breaker check at the top and between orders:

```python
def dispatch_for_paid_orders() -> int:
    """Найти все paid-заказы с pending-ссылками и прогнать dispatcher.

    Используется cron'ом — добивает заказы, чей dispatch при оплате упал
    или прошёл частично (например, API временно не доступен).
    Возвращает количество обработанных заказов.
    """
    if not _breaker.allow():
        logger.info("dispatch_for_paid_orders: circuit open, skip pass")
        return 0
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT o.increment "
            "FROM orders o JOIN order_links ol ON ol.order_id = o.increment "
            "WHERE o.status='paid' AND ol.status='pending' "
            "AND (ol.delivery_mode IS NULL OR ol.delivery_mode='auto')"
        ).fetchall()
    order_ids = [int(r["increment"]) for r in rows]
    handled = 0
    for order_id in order_ids:
        if not _breaker.allow():
            logger.warning(
                "dispatch_for_paid_orders: circuit opened mid-pass, aborting"
            )
            break
        try:
            dispatch_pending_links(order_id)
            handled += 1
        except Exception:  # noqa: BLE001
            logger.exception(
                "dispatch_for_paid_orders: order %s failed", order_id
            )
    return handled
```

- [ ] **Step 5: Run the circuit-breaker tests**

Run: `docker compose --profile test run --rm test pytest tests/unit/test_dispatcher_circuit_breaker.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add services/order_links_dispatcher.py tests/unit/test_dispatcher_circuit_breaker.py
git commit -m "feat(biza): circuit-breaker skips/aborts dispatch passes on sustained errors"
```

---

## Task 8: Full suite green

**Files:** none (verification)

- [ ] **Step 1: Run the whole suite**

Run: `make test`
Expected: all green. If anything in `tests/unit/test_force_dispatch.py` / `test_admin_test_auto_dispatch.py` / `test_pf_executor_api_real.py` fails, inspect — `force_dispatch` is a separate path (no breaker/cap) and must remain unchanged; the rate limiter starts full so adds no latency.

- [ ] **Step 2: If a pre-existing test asserts the old "stays pending+auto forever" semantics**

The only such test is `tests/unit/test_order_links_dispatcher.py::test_dispatch_classifier_auto_api_error_keeps_pending_for_retry`. It performs a SINGLE dispatch → attempts becomes 1 (< 2) → link stays `pending+auto`. It must still pass unchanged. If it does not, the attempt-cap logic is wrong (the FIRST error must not flip to manual) — fix `_bump_attempts_or_manual` (the `>=` comparison), do not weaken the test.

- [ ] **Step 3: Final commit (if any incidental fixes were needed)**

```bash
git add -A
git commit -m "test(biza): keep dispatcher suite green after resilience changes"
```

---

## Deploy notes (not a code task)

- `dispatch_attempts` migration applies automatically on api start (`apply_phase2_migrations`).
- `PF_AUTO_DISPATCH_ENABLED` stays `false` until biza confirms the 500 is fixed. Re-enable only after that — the new safeguards then prevent a repeat storm.
- Optional safety margin: set `BIZA_MAX_PER_MIN=55` in prod `.env` to stay comfortably under biza's 60/min.
