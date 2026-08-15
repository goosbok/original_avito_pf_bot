# Payment Gateway Health Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Periodically probe YooKassa by creating a 1 ₽ test payment (capture=False) and immediately cancelling it — if anything fails, alert admins via Telegram with the exact error from the provider.

**Architecture:** `services/payment_probe.py` owns the probe logic: `probe_yookassa() -> ProbeResult` (sync, wraps the SDK calls) and `async probe_and_alert()` (logs result, fires `send_admins` on failure). A `APScheduler AsyncIOScheduler` is started in `__main__.py`'s `on_startup`. The probe skips automatically if YooKassa is disabled in payment methods settings or credentials are absent. Interval is configurable via env var `PAYMENT_PROBE_INTERVAL_MIN` (default 15).

**Tech Stack:** `yookassa.Payment` (create + cancel), `APScheduler==3.11.2` (already in requirements), stdlib `dataclasses`, `time.monotonic` for latency.

---

## File map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `services/payment_probe.py` | `ProbeResult`, `probe_yookassa()`, `probe_and_alert()` |
| Create | `tests/unit/test_payment_probe.py` | Unit tests — all SDK calls mocked |
| Modify | `__main__.py` | Start scheduler in `on_startup` |
| Modify | `.env.example` | Document `PAYMENT_PROBE_INTERVAL_MIN` |

---

## Task 1: `services/payment_probe.py` — probe logic

**Files:**
- Create: `services/payment_probe.py`
- Create: `tests/unit/test_payment_probe.py`

The probe creates a 1 ₽ YooKassa payment with `capture: False` (no charge is made) and cancels it immediately. `probe_yookassa()` is synchronous (the yookassa SDK is blocking). `probe_and_alert()` is async (needs `send_admins`).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_payment_probe.py`:

```python
"""Tests for services/payment_probe.py — YooKassa SDK fully mocked."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _fake_payment(payment_id: str = "test-payment-id") -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    return p


# ── probe_yookassa ─────────────────────────────────────────────────────────────

def test_probe_ok_when_create_and_cancel_succeed():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.return_value = _fake_payment("pid-1")
        mock_payment.cancel.return_value = MagicMock()

        result = probe_yookassa()

    assert result.ok is True
    assert result.error_msg is None
    assert result.latency_ms >= 0
    mock_payment.create.assert_called_once()
    mock_payment.cancel.assert_called_once_with("pid-1")


def test_probe_fails_when_create_raises():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.side_effect = Exception("Unauthorized (401)")

        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "create failed" in result.error_msg
    assert "Unauthorized" in result.error_msg
    mock_payment.cancel.assert_not_called()


def test_probe_fails_when_cancel_raises():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.Payment") as mock_payment, \
         patch("services.payment_probe.SHOP_ID", 12345), \
         patch("services.payment_probe.SECRET_KEY", "test_secret"):
        mock_payment.create.return_value = _fake_payment("pid-2")
        mock_payment.cancel.side_effect = Exception("Payment already captured")

        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "cancel failed" in result.error_msg
    assert "Payment already captured" in result.error_msg


def test_probe_fails_when_credentials_missing():
    from services.payment_probe import probe_yookassa

    with patch("services.payment_probe.SHOP_ID", 0), \
         patch("services.payment_probe.SECRET_KEY", ""):
        result = probe_yookassa()

    assert result.ok is False
    assert result.error_msg is not None
    assert "not configured" in result.error_msg


# ── probe_and_alert ────────────────────────────────────────────────────────────

async def test_probe_and_alert_sends_alert_on_failure():
    from services.payment_probe import probe_and_alert, ProbeResult

    failing = ProbeResult(ok=False, error_msg="create failed: BadRequest: receipt required", latency_ms=42.0)

    with patch("services.payment_probe.probe_yookassa", return_value=failing), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await probe_and_alert()

    mock_send.assert_called_once()
    alert: str = mock_send.call_args[0][0]
    assert "Платёжка" in alert
    assert "receipt required" in alert


async def test_probe_and_alert_no_alert_on_success():
    from services.payment_probe import probe_and_alert, ProbeResult

    ok = ProbeResult(ok=True, latency_ms=120.0)

    with patch("services.payment_probe.probe_yookassa", return_value=ok), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await probe_and_alert()

    mock_send.assert_not_called()


async def test_probe_and_alert_skips_when_yookassa_disabled():
    from services.payment_probe import probe_and_alert

    with patch("services.payment_probe.is_yookassa_enabled", return_value=False), \
         patch("services.payment_probe.probe_yookassa") as mock_probe:
        await probe_and_alert()

    mock_probe.assert_not_called()


async def test_probe_and_alert_survives_send_admins_failure(caplog):
    from services.payment_probe import probe_and_alert, ProbeResult

    failing = ProbeResult(ok=False, error_msg="timeout", latency_ms=5000.0)

    with patch("services.payment_probe.probe_yookassa", return_value=failing), \
         patch("services.payment_probe.is_yookassa_enabled", return_value=True), \
         patch("utils.sender.send_admins", side_effect=Exception("network down")):
        with caplog.at_level(logging.WARNING):
            await probe_and_alert()  # must not raise

    assert any("send_admins" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
docker compose --profile test run --rm \
  -v "/Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot/.claude/worktrees/quirky-burnell-904680:/app" \
  test pytest tests/unit/test_payment_probe.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.payment_probe'`

- [ ] **Step 3: Create `services/payment_probe.py`**

```python
"""YooKassa health probe.

Runs probe_yookassa() (sync) on a schedule and fires an admin alert on failure.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from data.config import SHOP_ID, SECRET_KEY
from yookassa import Configuration, Payment

_log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    ok: bool
    error_msg: str | None = None
    latency_ms: float = 0.0


def is_yookassa_enabled() -> bool:
    """Return True if yookassa is configured and enabled in payment methods."""
    from services.payment_methods import is_enabled
    return bool(SHOP_ID and SECRET_KEY and is_enabled("yookassa"))


def probe_yookassa() -> ProbeResult:
    """Create a 1 RUB payment (capture=False) and cancel it immediately.

    Returns ProbeResult.ok=True if both API calls succeed.
    Does not charge anyone — capture=False is a hold-only authorization.
    """
    if not SHOP_ID or not SECRET_KEY:
        return ProbeResult(ok=False, error_msg="SHOP_ID or SECRET_KEY not configured")

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    t0 = time.monotonic()
    payment_id: str | None = None

    try:
        payment = Payment.create(
            {
                "amount": {"value": "1.00", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": "https://example.com"},
                "capture": False,
                "description": "[monitoring probe — не является реальным платежом]",
                "metadata": {"probe": "true"},
            },
            str(uuid.uuid4()),
        )
        payment_id = payment.id
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return ProbeResult(
            ok=False,
            error_msg=f"create failed: {type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )

    try:
        Payment.cancel(payment_id)
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return ProbeResult(
            ok=False,
            error_msg=f"cancel failed: {type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )

    return ProbeResult(ok=True, latency_ms=(time.monotonic() - t0) * 1000)


async def probe_and_alert() -> None:
    """Run the probe and send an admin alert if it fails. Never raises."""
    if not is_yookassa_enabled():
        _log.debug("payment probe: yookassa disabled or not configured, skipping")
        return

    result = probe_yookassa()

    if result.ok:
        _log.info("payment probe: OK (%.0f ms)", result.latency_ms)
        return

    _log.error("payment probe: FAILED — %s (%.0f ms)", result.error_msg, result.latency_ms)

    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"🚨 <b>Платёжка не работает!</b>\n\n"
            f"YooKassa не принял тестовый платёж.\n\n"
            f"<b>Ошибка:</b> <code>{(result.error_msg or '')[:400]}</code>\n"
            f"<b>Задержка:</b> {result.latency_ms:.0f} мс\n"
            f"<b>Время:</b> {ts}"
        )
    except Exception as send_exc:
        _log.warning("payment probe: send_admins failed: %s", send_exc)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose --profile test run --rm \
  -v "/Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot/.claude/worktrees/quirky-burnell-904680:/app" \
  test pytest tests/unit/test_payment_probe.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Run full suite — no regressions**

```bash
docker compose --profile test run --rm \
  -v "/Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot/.claude/worktrees/quirky-burnell-904680:/app" \
  test pytest tests/unit/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/payment_probe.py tests/unit/test_payment_probe.py
git commit -m "feat: add YooKassa health probe — create+cancel 1 RUB, alert admins on failure"
```

---

## Task 2: Scheduler in `__main__.py` + env config

**Files:**
- Modify: `__main__.py` — `on_startup`
- Modify: `.env.example` — document new var

The probe runs every `PAYMENT_PROBE_INTERVAL_MIN` minutes (default 15, 0 = disabled).

- [ ] **Step 1: Add `PAYMENT_PROBE_INTERVAL_MIN` to `.env.example`**

Find the YooKassa section in `.env.example`:
```
YOOKASSA_SECRET_KEY=
YOOKASSA_TEST=
```
Add after it:
```
# Payment probe: interval in minutes (0 = disabled, default 15)
PAYMENT_PROBE_INTERVAL_MIN=15
```

- [ ] **Step 2: Update `on_startup` in `__main__.py`**

Find `on_startup` and add probe scheduler startup **before** the final `print` line:

```python
async def on_startup(dp: Dispatcher):
    _log.info("Bot startup")
    await dp.bot.delete_webhook(drop_pending_updates=False)
    await dp.bot.get_updates(offset=-1, limit=1, allowed_updates=[
        "message", "callback_query", "inline_query", "chosen_inline_result",
        "shipping_query", "pre_checkout_query", "poll", "poll_answer",
        "my_chat_member", "chat_member",
    ])
    _log.info("Webhook cleared, polling with all update types")

    # ── Payment probe scheduler ───────────────────────────────────────────────
    probe_interval = int(os.getenv("PAYMENT_PROBE_INTERVAL_MIN", "15"))
    if probe_interval > 0:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.payment_probe import probe_and_alert
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(probe_and_alert, "interval", minutes=probe_interval)
        _scheduler.start()
        _log.info("Payment probe scheduler started (interval=%d min)", probe_interval)
    else:
        _log.info("Payment probe disabled (PAYMENT_PROBE_INTERVAL_MIN=0)")

    if os.getenv("START_WEB", "1") != "0":
        asyncio.create_task(serve_web())
    print(Fore.MAGENTA + fig.renderText('launched') + Fore.RESET)
```

Note: `_scheduler` is a local variable intentionally — APScheduler keeps an internal reference to the running scheduler, so garbage collection is not an issue.

- [ ] **Step 3: Verify bot starts without error**

```bash
docker compose build && docker compose up -d && sleep 5 && grep -i "probe" storage/log.txt
```

Expected output contains:
```
Payment probe scheduler started (interval=15 min)
```

- [ ] **Step 4: Commit**

```bash
git add __main__.py .env.example
git commit -m "feat: start payment probe scheduler on bot startup (PAYMENT_PROBE_INTERVAL_MIN)"
```

---

## Self-Review

### Spec coverage

| Requirement | Covered by |
|-------------|-----------|
| Периодически проверять платёжку | Task 2 — APScheduler каждые 15 мин |
| Создать платёж и отменить | Task 1 — `probe_yookassa()` создаёт 1 ₽ с `capture=False`, сразу отменяет |
| Алерт админам при ошибке | Task 1 — `probe_and_alert()` вызывает `send_admins` |
| Инфо об ошибке от провайдера | Task 1 — `result.error_msg` содержит `type(exc).__name__: str(exc)` |
| Не падать если алерт не прошёл | Task 1 — `send_admins` обёрнут в try/except |
| Не запускать если платёжка выключена | Task 1 — `is_yookassa_enabled()` проверяет настройки |

### Placeholder scan — NONE FOUND

### Type consistency

- `ProbeResult` определён в Task 1 и используется в обоих функциях в том же файле.
- `is_yookassa_enabled` определена в Task 1 и замокана в тестах с тем же именем.
- `probe_yookassa` и `probe_and_alert` — имена консистентны во всех тестах и в Task 2.
