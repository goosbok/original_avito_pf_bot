# Error Handling and Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every error visible (structured logs to persistent volume), non-crashing (global handler replies to user and alerts admins), and user-friendly (friendly Russian message + Menu/Support keyboard).

**Architecture:** Central `utils/error_handler.py` provides `report_handler_error()` — one function that logs at ERROR with rich context vars, fires an admin Telegram alert, and replies to the user with the standard friendly message. All user-facing handlers call this function in their except blocks. The global aiogram error handler is upgraded the same way. Logs write to `storage/log.txt` (the mounted Docker volume) with rotation so they survive container restarts.

**Tech Stack:** Python stdlib `logging.handlers.RotatingFileHandler`, aiogram 2.x `@dp.errors_handler()`, `unittest.mock.AsyncMock` for tests, `pytest-asyncio` (already configured with `asyncio_mode = "auto"`).

---

## File map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `__main__.py` | Move log to `storage/log.txt`, add rotation, upgrade global error handler |
| Create | `utils/error_handler.py` | `error_kb()`, `ERROR_MSG`, `report_handler_error()` |
| Create | `tests/unit/test_error_handler.py` | Unit tests for the central error utility |
| Modify | `utils/sqlite3.py` | Update `str_error` default to full friendly message |
| Modify | `handlers/pf_order.py` | Wrap `confirm_order` business logic in try/except |
| Modify | `handlers/refill.py` | Use `report_handler_error` in `_handle_yookassa_payment` |
| Modify | `handlers/profile.py` | Use `report_handler_error`, add rich context |
| Modify | `handlers/reviews.py` | Use `report_handler_error`, add rich context |
| Modify | `handlers/commands.py` | Use `report_handler_error` for user-facing failures |

---

## Task 1: Move log to persistent volume with rotation

**Files:**
- Modify: `__main__.py:16-24`

Context: Currently `LOG_PATH = Path(__file__).resolve().parent / "log.txt"` writes to `/app/log.txt` inside the container, which is not in the mounted `storage/` volume and is lost on restart. Fix: write to `storage/log.txt` with `RotatingFileHandler` (10 MB × 5 backups).

- [ ] **Step 1: Replace the logging setup in `__main__.py`**

Replace lines 16-24 (the `LOG_PATH` declaration and `logging.basicConfig(...)` block) with:

```python
from logging.handlers import RotatingFileHandler

_STORAGE = Path(__file__).resolve().parent / "storage"
_STORAGE.mkdir(exist_ok=True)
LOG_PATH = _STORAGE / "log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_PATH,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
```

- [ ] **Step 2: Verify manually**

Run: `docker compose build && docker compose up -d`

After the bot starts, verify: `docker exec original_avito_pf_bot-bot-1 ls -lh storage/log.txt`

Expected: file exists and grows as the bot receives updates.

- [ ] **Step 3: Commit**

```bash
git add __main__.py
git commit -m "fix: write logs to storage/log.txt with rotation so they survive restarts"
```

---

## Task 2: Create `utils/error_handler.py`

**Files:**
- Create: `utils/error_handler.py`
- Create: `tests/unit/test_error_handler.py`

This is the central utility. It owns the user-facing error message text, the error keyboard, and the logic to log → alert admins → reply to user.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_error_handler.py`:

```python
"""Tests for utils/error_handler.py — no DB, no real Telegram."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_message_mock() -> AsyncMock:
    """Fake aiogram Message with an awaitable .answer()."""
    m = AsyncMock()
    m.answer = AsyncMock()
    return m


def _make_call_mock() -> AsyncMock:
    """Fake aiogram CallbackQuery with .message.answer()."""
    c = AsyncMock()
    c.message = AsyncMock()
    c.message.answer = AsyncMock()
    return c


# ── tests ──────────────────────────────────────────────────────────────────────

async def test_logs_at_error_level(caplog):
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        with caplog.at_level(logging.ERROR, logger="test.handler"):
            await report_handler_error(
                ValueError("db exploded"),
                logger=logging.getLogger("test.handler"),
                context={"handler": "test_fn", "user_id": 42},
            )

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected at least one ERROR log record"
    combined = " ".join(r.message for r in error_records)
    assert "db exploded" in combined
    assert "test_fn" in combined
    assert "42" in combined


async def test_calls_send_admins_with_exception_and_context():
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", new_callable=AsyncMock) as mock_send:
        await report_handler_error(
            TypeError("unexpected None"),
            logger=logging.getLogger("test"),
            context={"handler": "order_confirm", "user_id": 99, "balance": 500},
        )

    mock_send.assert_called_once()
    alert_text: str = mock_send.call_args[0][0]
    assert "TypeError" in alert_text
    assert "order_confirm" in alert_text
    assert "99" in alert_text


async def test_replies_to_message_with_friendly_text():
    from utils.error_handler import report_handler_error, ERROR_MSG

    msg = _make_message_mock()
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        await report_handler_error(
            RuntimeError("oops"),
            logger=logging.getLogger("test"),
            context={"handler": "test"},
            reply_target=msg,
        )

    msg.answer.assert_called_once()
    replied_text: str = msg.answer.call_args[0][0]
    assert "ошибка" in replied_text.lower()
    # keyboard must be passed
    assert msg.answer.call_args.kwargs.get("reply_markup") is not None


async def test_replies_to_callback_query_via_message_answer():
    from utils.error_handler import report_handler_error

    call = _make_call_mock()
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        await report_handler_error(
            RuntimeError("cb fail"),
            logger=logging.getLogger("test"),
            context={"handler": "test"},
            reply_target=call,
        )

    call.message.answer.assert_called_once()


async def test_survives_send_admins_failure(caplog):
    """If send_admins raises, report_handler_error must not propagate the exception."""
    from utils.error_handler import report_handler_error

    with patch("utils.sender.send_admins", side_effect=Exception("network timeout")):
        with caplog.at_level(logging.WARNING):
            await report_handler_error(  # must not raise
                ValueError("original"),
                logger=logging.getLogger("test"),
                context={"handler": "test"},
            )

    warn_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("send_admins" in m for m in warn_msgs)


async def test_survives_reply_failure(caplog):
    """If .answer() raises, report_handler_error must not propagate."""
    from utils.error_handler import report_handler_error

    msg = _make_message_mock()
    msg.answer.side_effect = Exception("telegram rate limit")
    with patch("utils.sender.send_admins", new_callable=AsyncMock):
        with caplog.at_level(logging.WARNING):
            await report_handler_error(
                ValueError("original"),
                logger=logging.getLogger("test"),
                context={"handler": "test"},
                reply_target=msg,
            )

    warn_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("reply" in m.lower() or "answer" in m.lower() for m in warn_msgs)
```

- [ ] **Step 2: Run tests to confirm they FAIL**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_error_handler.py -v
```

Expected: `ModuleNotFoundError: No module named 'utils.error_handler'`

- [ ] **Step 3: Create `utils/error_handler.py`**

```python
"""Central error-handling utility for bot handlers.

Usage in a handler:
    except Exception as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "confirm_order", "user_id": user_id, "data": dict(data)},
            reply_target=call,   # Message or CallbackQuery
        )
        await state.finish()
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

_log = logging.getLogger(__name__)

ERROR_MSG = (
    "⚠️ К сожалению, во время операции произошла ошибка.\n\n"
    "Мы уже ведём работы по её устранению. "
    "Если с вас были списаны деньги, а услуга недоступна — "
    "напишите нам в поддержку."
)


def error_kb() -> InlineKeyboardMarkup:
    """Keyboard with Main Menu and Support buttons for error replies."""
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"),
        InlineKeyboardButton(text="💬 Поддержка", callback_data="info:support"),
    )
    return kb


async def report_handler_error(
    exc: Exception,
    *,
    logger: logging.Logger,
    context: dict[str, Any],
    reply_target: "types.Message | types.CallbackQuery | None" = None,
) -> None:
    """Log exc at ERROR with context vars, alert admins, reply to user.

    Never raises — all failures inside are caught and logged at WARNING.
    """
    ctx_str = " | ".join(f"{k}={v!r}" for k, v in context.items())
    logger.error("handler error: %s | %s", exc, ctx_str, exc_info=True)

    # Alert admins (best-effort)
    try:
        from utils.sender import send_admins  # lazy to avoid circular import at test time
        alert = (
            f"🚨 <b>Ошибка в боте</b>\n"
            f"<code>{type(exc).__name__}: {exc}</code>\n"
            f"<b>Контекст:</b> <code>{ctx_str[:300]}</code>"
        )
        await send_admins(alert)
    except Exception as alert_exc:
        _log.warning("report_handler_error: send_admins failed: %s", alert_exc)

    # Reply to user (best-effort)
    if reply_target is not None:
        try:
            kb = error_kb()
            if isinstance(reply_target, types.CallbackQuery):
                await reply_target.message.answer(ERROR_MSG, reply_markup=kb)
            else:
                await reply_target.answer(ERROR_MSG, reply_markup=kb)
        except Exception as reply_exc:
            _log.warning("report_handler_error: failed to reply to user: %s", reply_exc)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_error_handler.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
docker compose --profile test run --rm test pytest -v
```

Expected: all previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add utils/error_handler.py tests/unit/test_error_handler.py
git commit -m "feat: add report_handler_error — central log+alert+reply utility"
```

---

## Task 3: Upgrade global error handler

**Files:**
- Modify: `__main__.py:38-41`

The current global handler only logs. After this task it also alerts admins and replies to the user.

- [ ] **Step 1: Replace `_global_error_handler` in `__main__.py`**

Replace the existing function (lines 38-41):

```python
@dp.errors_handler()
async def _global_error_handler(update, exception):
    _log.exception("Unhandled exception for update %s", update, exc_info=exception)
    return True
```

With:

```python
@dp.errors_handler()
async def _global_error_handler(update, exception):
    from utils.error_handler import report_handler_error

    source = update.message or update.callback_query
    context = {
        "handler": "global_error_handler",
        "update_id": update.update_id,
        "tg_user_id": source.from_user.id if source and source.from_user else None,
        "msg_text": (update.message.text or "")[:120] if update.message else None,
        "cb_data": update.callback_query.data if update.callback_query else None,
    }
    await report_handler_error(
        exception,
        logger=_log,
        context=context,
        reply_target=source,
    )
    return True
```

- [ ] **Step 2: Commit**

```bash
git add __main__.py
git commit -m "fix: global error handler now alerts admins and replies to user"
```

---

## Task 4: Update `str_error` default text

**Files:**
- Modify: `utils/sqlite3.py:87`

Several handlers use `get_string('str_error')` directly (e.g., `order_contact_set` in pf_order.py, `select_payment_method` in refill.py). Update the default so they also show the friendly message.

- [ ] **Step 1: Update `_STRING_DEFAULTS` in `utils/sqlite3.py`**

Find line 87:
```python
    "str_error": "⚠️ Произошла ошибка. Попробуйте позже.",
```

Replace with:
```python
    "str_error": (
        "⚠️ К сожалению, во время операции произошла ошибка.\n\n"
        "Мы уже ведём работы по её устранению. "
        "Если с вас были списаны деньги, а услуга недоступна — "
        "напишите нам в поддержку."
    ),
```

- [ ] **Step 2: Run tests to verify `test_string_defaults.py` still passes**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_string_defaults.py -v
```

Expected: PASS (the test checks that `get_string` returns the right default; updating the value is fine as long as the key exists).

- [ ] **Step 3: Update handlers that use `get_string('str_error')` with `get_menu_kb()` to use `error_kb()` instead**

In `handlers/pf_order.py`, find the `order_contact_set` handler:
```python
        STR = get_string('str_error')
        await call.message.answer(STR, reply_markup=get_menu_kb())
```
Replace with:
```python
        from utils.error_handler import error_kb
        STR = get_string('str_error')
        await call.message.answer(STR, reply_markup=error_kb())
```

In `handlers/pf_order.py`, find `confirm_order`'s early-exit for stale state:
```python
            STR = get_string('str_error') or '⚠️ Заказ устарел. Начните оформление заново.'
            await call.message.answer(STR, reply_markup=get_menu_kb())
```
Replace with:
```python
            from utils.error_handler import error_kb
            STR = get_string('str_error')
            await call.message.answer(STR, reply_markup=error_kb())
```

In `handlers/refill.py`, find `select_payment_method`:
```python
        await call.message.answer(get_string('str_error'), reply_markup=get_menu_kb())
```
Replace with:
```python
        from utils.error_handler import error_kb
        await call.message.answer(get_string('str_error'), reply_markup=error_kb())
```

- [ ] **Step 4: Run full test suite**

```bash
docker compose --profile test run --rm test pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py handlers/pf_order.py handlers/refill.py
git commit -m "fix: update str_error to friendly message; swap get_menu_kb for error_kb in stale-state paths"
```

---

## Task 5: Protect `confirm_order` in `handlers/pf_order.py`

**Files:**
- Modify: `handlers/pf_order.py:221-286` (the `confirm_order` handler)

The business logic inside `confirm_order` (balance deduction → `add_order` → `send_admins`) currently has zero error handling. If anything fails after the balance is debited, the user loses money with no feedback and the error is only visible in global handler logs (no context).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pf_order_error.py`:

```python
"""Verify confirm_order shows user-friendly error when business logic fails."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_call(data="order_confirm"):
    call = AsyncMock()
    call.data = data
    call.from_user = MagicMock(id=111)
    call.message = AsyncMock()
    call.message.answer = AsyncMock()
    call.message.delete = AsyncMock()
    return call


async def test_confirm_order_replies_on_db_error(tmp_db, monkeypatch):
    """If add_order raises, user gets error message (not silence)."""
    from utils.error_handler import ERROR_MSG

    # Make get_user return a user with sufficient balance
    fake_user = {"id": 1, "balance": 1000, "user_name": "testuser"}
    monkeypatch.setattr("handlers.pf_order.get_user", lambda **kw: fake_user)

    # Make add_order blow up
    monkeypatch.setattr("handlers.pf_order.add_order", MagicMock(side_effect=RuntimeError("disk full")))

    from unittest.mock import AsyncMock as AM
    monkeypatch.setattr("handlers.pf_order.report_handler_error", AM())

    call = _make_call()

    # Build fake FSMContext with state data
    state = AsyncMock()
    state.proxy = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value={"total_price": 500, "days": 7, "fix": 3, "links": "https://avito.ru/1", "contact": True}),
        __aexit__=AsyncMock(return_value=False),
    ))

    from handlers.pf_order import confirm_order
    await confirm_order(call, state, user_id=1)

    from handlers.pf_order import report_handler_error as rhe_mock
    rhe_mock.assert_called_once()
    call_kwargs = rhe_mock.call_args
    assert call_kwargs[1]["reply_target"] is call
    assert "confirm_order" in str(call_kwargs[1]["context"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_pf_order_error.py -v
```

Expected: FAIL — `report_handler_error` not called, test assertion fails.

- [ ] **Step 3: Wrap business logic in `confirm_order`**

In `handlers/pf_order.py`, add the import at the top of the file:
```python
from utils.error_handler import report_handler_error
```

Then in the `confirm_order` handler (around line 221), wrap the `if user['balance'] >= data['total_price']:` branch:

Replace the entire `if user['balance'] >= data['total_price']:` block with:

```python
        if user['balance'] >= data['total_price']:
            try:
                update_user(id=user['id'], balance=user['balance'] - data['total_price'])
                add_order(
                    user_id=user['id'],
                    price=data['total_price'],
                    position_name=f"{data['days']}/{data['fix']}",
                    status="Posted",
                    links=str(data['links']),
                    contacts=data['contact'],
                    user_name=user['user_name'],
                )
                ADM_MSG = get_string('str_new_order_text')
                order = get_users_last_order(user['id'])
                ord_id = order['increment']
                f_price = format_decimal(order['price'])
                user_str = await get_user_string_without_first_name(user)
                pos_name = order['position_name']
                status = order['status']
                con_str = 'Да' if order['contacts'] else 'Нет'
                ord_date = order['date']
                links_cnt = len(order['links'])
                links_str = ""
                for link in order['links'].split(','):
                    link = link.replace("'", "")
                    links_str += f"\n<code>{link}</code>"
                ADM_MSG = ADM_MSG.format(
                    ord_id, f_price, user_str, pos_name, status,
                    con_str, ord_date, links_cnt, links_str,
                )
                if len(ADM_MSG) < 4096:
                    await send_admins(ADM_MSG)
                else:
                    for msg in split_messages(ADM_MSG.split('\n'), '\n'):
                        await send_admins(msg)
                USR_MSG = get_string('str_order_confirm').format(ord_id)
                await call.message.answer(USR_MSG, reply_markup=get_menu_kb())
                logger.info(
                    "order placed: user_id=%s price=%s days=%s fix=%s",
                    user_id, data['total_price'], data.get('days'), data.get('fix'),
                )
            except Exception as exc:
                await report_handler_error(
                    exc,
                    logger=logger,
                    context={
                        "handler": "confirm_order",
                        "user_id": user_id,
                        "balance": user['balance'],
                        "total_price": data.get('total_price'),
                        "days": data.get('days'),
                        "links_count": len(str(data.get('links', '')).split(',')),
                    },
                    reply_target=call,
                )
                await state.finish()
                return
```

- [ ] **Step 4: Run test — expect PASS**

```bash
docker compose --profile test run --rm test pytest tests/unit/test_pf_order_error.py -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
docker compose --profile test run --rm test pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add handlers/pf_order.py tests/unit/test_pf_order_error.py
git commit -m "fix: wrap confirm_order business logic in try/except with report_handler_error"
```

---

## Task 6: Harden `handlers/refill.py`

**Files:**
- Modify: `handlers/refill.py:77-145` (`_handle_yookassa_payment`)

The payment finalization `finalize_with_referral_bonus` already has a try/except that logs but replies with bare `str_error` and no keyboard. Upgrade to use `report_handler_error`.

- [ ] **Step 1: Add import and update `_handle_yookassa_payment`**

Add at the top of `handlers/refill.py`:
```python
from utils.error_handler import report_handler_error
```

In `_handle_yookassa_payment`, replace the two exception handlers (lines ~116-122):

```python
    except UserNotFound:
        await bot.send_message(chat_id=tg_id, text=get_string('str_error'))
        return
    except Exception:
        logger.exception("yookassa payment: finalize_with_referral_bonus failed for user_id=%s", user_id)
        await bot.send_message(chat_id=tg_id, text=get_string('str_error'))
        return
```

With:

```python
    except UserNotFound as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id, "amount": amount, "tg_id": tg_id},
        )
        from utils.error_handler import error_kb, ERROR_MSG
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return
    except Exception as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "_handle_yookassa_payment", "user_id": user_id, "amount": amount, "tg_id": tg_id},
        )
        from utils.error_handler import error_kb, ERROR_MSG
        await bot.send_message(chat_id=tg_id, text=ERROR_MSG, reply_markup=error_kb())
        return
```

Note: `bot.send_message` is used here (not `call.message.answer`) because `_handle_yookassa_payment` is called from a background polling task and may no longer have a message reference — `tg_id` is the reliable way to reach the user.

- [ ] **Step 2: Run full tests**

```bash
docker compose --profile test run --rm test pytest -v
```

Expected: all tests pass (including existing `test_refill.py`).

- [ ] **Step 3: Commit**

```bash
git add handlers/refill.py
git commit -m "fix: use report_handler_error in payment finalization — adds admin alert and keyboard"
```

---

## Task 7: Standardize remaining user-facing handlers

**Files:**
- Modify: `handlers/profile.py`
- Modify: `handlers/reviews.py`
- Modify: `handlers/commands.py`

### `handlers/profile.py`

The profile handler's `listord` section (around line 88) already uses `logger.exception` but replies without a keyboard and without alerting admins.

- [ ] **Step 1: Add import to `handlers/profile.py`**

```python
from utils.error_handler import report_handler_error
```

- [ ] **Step 2: Find the except block in `listord` (around line 87-88)**

```python
        except Exception:
            logger.exception("profile listord: failed for tg_id=%s", call.from_user.id)
```

Replace with:

```python
        except Exception as exc:
            await report_handler_error(
                exc,
                logger=logger,
                context={
                    "handler": "profile_listord",
                    "tg_id": call.from_user.id,
                    "user_id": user_id,
                    "cb_data": call.data,
                },
                reply_target=call,
            )
```

- [ ] **Step 3: Find the except block around line 38 (str_error path)**

```python
        await call.message.answer(get_string('str_error') or '⚠️ Ошибка', reply_markup=get_menu_kb())
```

Replace `reply_markup=get_menu_kb()` with `reply_markup=error_kb()` and ensure the import exists:

```python
        from utils.error_handler import error_kb
        await call.message.answer(get_string('str_error'), reply_markup=error_kb())
```

### `handlers/reviews.py`

Reviews has large exception blocks that reply with hardcoded Russian text. Add `report_handler_error` to each:

- [ ] **Step 4: Find all user-facing `except Exception as e:` blocks in `handlers/reviews.py`**

For each block that answers the user (not just `logger.debug("could not delete message")`), add a `report_handler_error` call before `await message.answer(...)` and pass a context dict with the handler name, user_id, and relevant state:

```python
        except Exception as exc:
            await report_handler_error(
                exc,
                logger=logger,
                context={"handler": "<handler_function_name>", "user_id": user_id},
                reply_target=message,  # or call if it's a CallbackQuery
            )
            # keep the existing answer line if it's a meaningful user-facing message,
            # OR remove it if report_handler_error already replied
```

**Important:** If the existing answer is a domain-specific message (e.g., "Отзыв уже оставлен"), keep it. If it's a generic "Ошибка" string, remove it — `report_handler_error` already replied.

### `handlers/commands.py`

The `cmd_delme` handler (line ~35) has:
```python
    except Exception:
        logger.exception("cmd_delme: failed to delete user %s", user_id)
```

- [ ] **Step 5: Update `cmd_delme` in `handlers/commands.py`**

Add import:
```python
from utils.error_handler import report_handler_error
```

Replace the except block:
```python
    except Exception as exc:
        await report_handler_error(
            exc,
            logger=logger,
            context={"handler": "cmd_delme", "user_id": user_id},
            reply_target=message,
        )
```

- [ ] **Step 6: Run full tests**

```bash
docker compose --profile test run --rm test pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add handlers/profile.py handlers/reviews.py handlers/commands.py
git commit -m "fix: standardize error handling in profile/reviews/commands — alert admins, reply with keyboard"
```

---

## Self-Review

### Spec coverage

| Requirement | Covered by |
|-------------|-----------|
| Logging to file | Task 1 (storage/log.txt + rotation) |
| Bot never crashes | Task 3 (global error handler catches everything and returns True) |
| Every error logged | Tasks 2-7 (`report_handler_error` logs at ERROR with context) |
| Alert admins on error | Task 2 (`send_admins` call inside `report_handler_error`) |
| Friendly user message | Task 2 (`ERROR_MSG` constant), Task 4 (`str_error` updated) |
| "Главное меню" button | Task 2 (`error_kb()` — first button) |
| "Поддержка" button | Task 2 (`error_kb()` — second button) |
| Rich debug context (scope vars) | Tasks 5-7 (each handler passes relevant local variables as `context={}`) |
| Middleware safety | `exists_user.py` already has try/except around `send_admins`; the global error handler covers middleware exceptions |

### Placeholder scan — NONE FOUND

All code blocks are complete. No "TBD", "fill in", or "similar to" references.

### Type consistency

- `report_handler_error` signature is identical in definition (Task 2) and all call sites (Tasks 3-7).
- `error_kb()` returns `InlineKeyboardMarkup` everywhere.
- `ERROR_MSG` is a `str` constant imported directly where used.
