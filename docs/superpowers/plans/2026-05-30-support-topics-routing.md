# Support Topics Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route bot admin notifications across four forum topics in the support group (questions, orders, errors, new_users), lock the support-reply handler to the questions topic, and bump the landing "completed orders" counter from 50 000+ to 100 000+.

**Architecture:** Add four `SUPPORT_THREAD_*` int env vars in `data/config.py`. Refactor `utils/sender.py:send_admins` to accept a `category` literal and forward `message_thread_id` to `bot.send_message`. Update all six call sites to pass the right category. Refactor `web/routers/support.py` to use `send_admins` and grab `message_id` from its return value. Add a startup validator in `__main__.py` that fails fast if `SUPPORT_THREAD_ERRORS` is unset and warns into the errors topic for any other unset category. Add a topic-id guard at the top of `handlers/support_web.py:admin_reply_to_support`.

**Tech Stack:** Python 3, aiogram 2.x, FastAPI (for the web routers), SQLite, pytest. Tests run via `docker compose --profile test run --rm test` (NEVER local python3 — see memory `feedback_docker_tests.md`).

**Spec:** [docs/superpowers/specs/2026-05-30-support-topics-routing-design.md](../specs/2026-05-30-support-topics-routing-design.md)

---

## File Map

**Modify:**
- `web/static/components/Landing.jsx` — counter literal
- `data/config.py` — four new module-level int constants
- `tests/conftest.py` — stub the four new constants for unit tests
- `utils/sender.py` — extend signature, route by category, return `Message`
- `web/routers/support.py` — replace direct `bot.send_message` with `send_admins`
- `web/routers/orders.py` — pass `"orders"` category
- `web/routers/guest_orders.py` — pass `"orders"` category
- `web/routers/refill.py` — pass `"orders"` category
- `handlers/reviews.py` — pass `"orders"` category (2 call sites)
- `utils/error_handler.py` — pass `"errors"` category
- `middlewares/exists_user.py` — pass `"new_users"` category
- `handlers/support_web.py` — drop reply when `message.message_thread_id != SUPPORT_THREAD_QUESTIONS`
- `__main__.py` — call `validate_support_topics()` from `on_startup` before everything else
- `tests/unit/test_sender.py` — adapt to new signature, add category + missing-thread tests
- `tests/unit/test_support_reply.py` — set `message_thread_id` in helper, add wrong-topic test

**Create:**
- `tests/unit/test_startup_validation.py` — covers `validate_support_topics`

---

## Task 1: Landing counter 50 000+ → 100 000+

**Files:**
- Modify: `web/static/components/Landing.jsx:132`

No test — it's a static string. We will eyeball it in the browser after merge.

- [ ] **Step 1: Find current line**

Run: `grep -n "50 000+" web/static/components/Landing.jsx`
Expected: `132:            { num: '50 000+', label: 'Выполненных заказов', color: '#0088cc' },`

- [ ] **Step 2: Edit the literal**

Replace:
```jsx
{ num: '50 000+', label: 'Выполненных заказов', color: '#0088cc' },
```
With:
```jsx
{ num: '100 000+', label: 'Выполненных заказов', color: '#0088cc' },
```

- [ ] **Step 3: Verify nothing else uses 50 000**

Run: `grep -rn "50 000\|50000\|50_000" web/static/ web/`
Expected: only the changed line should appear in the diff context (no other matches in app text).

- [ ] **Step 4: Commit**

```bash
git add web/static/components/Landing.jsx
git commit -m "feat(web): bump completed-orders counter to 100 000+"
```

---

## Task 2: Add four SUPPORT_THREAD_* env vars to config

**Files:**
- Modify: `data/config.py:16-17` (insert four lines after `SUPPORT_CHAT_ID`)
- Modify: `tests/conftest.py:29` (insert four lines after `stub.SUPPORT_CHAT_ID = 0`)

- [ ] **Step 1: Add constants to `data/config.py`**

Insert after the `SUPPORT_CHAT_ID` line:
```python
SUPPORT_CHAT_ID: int = int(os.getenv("SUPPORT_CHAT_ID", "0"))
SUPPORT_THREAD_QUESTIONS: int = int(os.getenv("SUPPORT_THREAD_QUESTIONS", "0"))
SUPPORT_THREAD_ORDERS:    int = int(os.getenv("SUPPORT_THREAD_ORDERS", "0"))
SUPPORT_THREAD_ERRORS:    int = int(os.getenv("SUPPORT_THREAD_ERRORS", "0"))
SUPPORT_THREAD_NEW_USERS: int = int(os.getenv("SUPPORT_THREAD_NEW_USERS", "0"))
```

- [ ] **Step 2: Mirror in `tests/conftest.py` config stub**

Insert after `stub.SUPPORT_CHAT_ID = 0`:
```python
    stub.SUPPORT_CHAT_ID = 0
    stub.SUPPORT_THREAD_QUESTIONS = 0
    stub.SUPPORT_THREAD_ORDERS = 0
    stub.SUPPORT_THREAD_ERRORS = 0
    stub.SUPPORT_THREAD_NEW_USERS = 0
```

- [ ] **Step 3: Run unit tests to make sure stub still imports**

Run: `docker compose --profile test run --rm test`
Expected: same pass/fail counts as before (no new failures; no new tests yet).

- [ ] **Step 4: Commit**

```bash
git add data/config.py tests/conftest.py
git commit -m "feat(config): add SUPPORT_THREAD_* env vars for forum routing"
```

---

## Task 3: Refactor `utils/sender.py` — TDD for category routing

**Files:**
- Modify: `tests/unit/test_sender.py` (rewrite to new API + add new cases)
- Modify: `utils/sender.py` (extend signature)

### Step 3.1: Replace existing tests with category-aware versions

- [ ] **Write the new test file**

Overwrite `tests/unit/test_sender.py` with:

```python
"""Tests for utils/sender.py — category-routed admin notifications."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


def _patch_common(monkeypatch):
    """Reset the bot mock and chat id for every test."""
    mock_send = AsyncMock(return_value="sent-message-sentinel")
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    return mock_send


def test_send_admins_routes_questions_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)

    from utils import sender
    result = asyncio.run(sender.send_admins("hi", "questions"))

    mock_send.assert_called_once_with(
        chat_id=-100500,
        text="hi",
        message_thread_id=3,
        parse_mode=None,
        disable_web_page_preview=True,
    )
    assert result == "sent-message-sentinel"


def test_send_admins_routes_orders_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)

    from utils import sender
    asyncio.run(sender.send_admins("order!", "orders"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 5


def test_send_admins_routes_errors_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)

    from utils import sender
    asyncio.run(sender.send_admins("boom", "errors"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 7


def test_send_admins_routes_new_users_to_thread(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils import sender
    asyncio.run(sender.send_admins("hello new user", "new_users"))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["message_thread_id"] == 9


def test_send_admins_drops_when_thread_unset(monkeypatch):
    """If the category's thread id == 0, do not call bot.send_message at all."""
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)

    from utils import sender
    result = asyncio.run(sender.send_admins("orphan", "questions"))

    assert result is None
    mock_send.assert_not_called()


def test_send_admins_forwards_parse_mode(monkeypatch):
    mock_send = _patch_common(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)

    from utils import sender
    asyncio.run(sender.send_admins("<b>x</b>", "questions", parse_mode="HTML"))

    assert mock_send.call_args.kwargs["parse_mode"] == "HTML"


def test_send_admins_rejects_unknown_category(monkeypatch):
    _patch_common(monkeypatch)

    from utils import sender
    with pytest.raises(ValueError, match="unknown category"):
        asyncio.run(sender.send_admins("nope", "not_a_category"))  # type: ignore[arg-type]
```

- [ ] **Step 3.2: Run tests — they should all fail (function signature mismatch)**

Run: `docker compose --profile test run --rm test tests/unit/test_sender.py -v`
Expected: every test FAILs with `TypeError: send_admins() takes 1 positional argument but 2 were given` (or similar).

### Step 3.3: Rewrite `utils/sender.py`

- [ ] **Implement the new sender**

Replace the entire contents of `utils/sender.py` with:

```python
"""Send admin notifications routed by category to forum topics."""
from __future__ import annotations

from typing import Literal, Optional

from aiogram.types import Message

import data.config as config
from data.loader import bot

Category = Literal["questions", "orders", "errors", "new_users"]

_CATEGORY_TO_CONFIG_ATTR: dict[str, str] = {
    "questions": "SUPPORT_THREAD_QUESTIONS",
    "orders":    "SUPPORT_THREAD_ORDERS",
    "errors":    "SUPPORT_THREAD_ERRORS",
    "new_users": "SUPPORT_THREAD_NEW_USERS",
}


def _resolve_thread_id(category: str) -> int:
    attr = _CATEGORY_TO_CONFIG_ATTR.get(category)
    if attr is None:
        raise ValueError(f"unknown category: {category!r}")
    return int(getattr(config, attr, 0) or 0)


async def send_admins(
    msg: str,
    category: Category,
    *,
    parse_mode: Optional[str] = None,
) -> Optional[Message]:
    """Send `msg` to the support group's forum topic for `category`.

    Returns the sent Message, or None if the topic is not configured
    (so callers like support.py can decide whether to persist message_id).
    """
    thread_id = _resolve_thread_id(category)
    if thread_id == 0:
        return None
    return await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=msg,
        message_thread_id=thread_id,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
```

- [ ] **Step 3.4: Re-run the sender tests**

Run: `docker compose --profile test run --rm test tests/unit/test_sender.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 3.5: Run the full suite to catch regressions in callers**

Run: `docker compose --profile test run --rm test`
Expected: tests in `test_payment_probe.py` and `test_error_handler.py` still pass (they patch `send_admins` with `AsyncMock`, which accepts any signature). If something fails there, do NOT relax the new signature — adjust the test patch instead.

- [ ] **Step 3.6: Commit**

```bash
git add utils/sender.py tests/unit/test_sender.py
git commit -m "feat(sender): route send_admins by category to forum topics"
```

---

## Task 4: Update non-support call sites to pass category

The five call sites that already use `send_admins` need only a positional argument added. None of their existing tests assert on the call signature beyond patching it, so behaviour stays the same; the new arg only matters when the env vars are set in production.

**Files:**
- Modify: `web/routers/orders.py:139`
- Modify: `web/routers/guest_orders.py:134`
- Modify: `web/routers/refill.py:65`
- Modify: `handlers/reviews.py:148, 209`
- Modify: `utils/error_handler.py:63`
- Modify: `middlewares/exists_user.py:47`

- [ ] **Step 1: `web/routers/orders.py:139`**

Change:
```python
await send_admins(adm_msg)
```
To:
```python
await send_admins(adm_msg, "orders")
```

- [ ] **Step 2: `web/routers/guest_orders.py:134`**

Change:
```python
await send_admins(msg)
```
To:
```python
await send_admins(msg, "orders")
```

- [ ] **Step 3: `web/routers/refill.py:65`**

Change:
```python
await send_admins(msg)
```
To:
```python
await send_admins(msg, "orders")
```

- [ ] **Step 4: `handlers/reviews.py:148`**

Change:
```python
await send_admins(MSG)
```
To:
```python
await send_admins(MSG, "orders")
```

- [ ] **Step 5: `handlers/reviews.py:209`**

Change:
```python
await send_admins(MSG)
```
To:
```python
await send_admins(MSG, "orders")
```

(Both lines are inside different handlers, do not use `replace_all` on the file — verify by reading lines 148 and 209.)

- [ ] **Step 6: `utils/error_handler.py:63`**

Change:
```python
await send_admins(alert)
```
To:
```python
await send_admins(alert, "errors")
```

- [ ] **Step 7: `middlewares/exists_user.py:47`**

Current (multi-line, indented inside `try:` block at depth 4×4=16 spaces):
```python
                await send_admins(
                    f"<b>💎 Зарегистрирован новый пользователь @{user_name} "
                    f"(<a href='tg://user?id={user_id}'>{user_id}</a>)</b>"
                )
```
Change to:
```python
                await send_admins(
                    f"<b>💎 Зарегистрирован новый пользователь @{user_name} "
                    f"(<a href='tg://user?id={user_id}'>{user_id}</a>)</b>",
                    "new_users",
                )
```

(Note: `data.loader.bot` is constructed with `parse_mode=types.ParseMode.HTML` as default, so passing `parse_mode=None` through `send_admins` still renders HTML — no behavior change.)

- [ ] **Step 8: Run the full test suite**

Run: `docker compose --profile test run --rm test`
Expected: same pass/fail counts as after Task 3. AsyncMock-patched `send_admins` calls absorb the extra arg silently.

- [ ] **Step 9: Commit**

```bash
git add web/routers/orders.py web/routers/guest_orders.py web/routers/refill.py \
        handlers/reviews.py utils/error_handler.py middlewares/exists_user.py
git commit -m "feat(notify): tag send_admins calls with forum-topic categories"
```

---

## Task 5: Refactor `web/routers/support.py` to use `send_admins`

`support.py` currently calls `bot.send_message` directly because it needs the returned `message_id` to persist into `support_messages.tg_message_id`. Now that `send_admins` returns the Message, we can route via it.

**Files:**
- Modify: `web/routers/support.py:50-82` (`_forward_to_admins`)

- [ ] **Step 1: Read the current implementation**

Read `web/routers/support.py` lines 1-82 to confirm the imports (especially `_SUPPORT_TAG`).

- [ ] **Step 2: Replace `_forward_to_admins`**

Replace the body of `_forward_to_admins` (lines 50-82) with:

```python
async def _forward_to_admins(user_id: int, msg_id: int, text: str) -> None:
    try:
        from services import identity
        from services.db import connect as db_connect
        from utils.sender import send_admins

        try:
            u = identity.get_user(user_id)
            user_str = f"@{u.user_name}" if u.user_name else f"ID {user_id}"
        except Exception:
            user_str = f"ID {user_id}"

        fwd_text = (
            f"💬 <b>{_SUPPORT_TAG} #{msg_id}</b>\n"
            f"От: {user_str}\n\n{text}"
        )

        sent = await send_admins(fwd_text, "questions", parse_mode="HTML")
        if sent is None:
            logger.warning(
                "support: SUPPORT_THREAD_QUESTIONS unset — message %s for user %s not delivered to admins",
                msg_id, user_id,
            )
            return

        with db_connect() as con:
            con.execute(
                "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
                (sent.message_id, msg_id),
            )
            con.commit()
    except Exception:
        logger.exception("_forward_to_admins failed for user_id=%s", user_id)
```

- [ ] **Step 3: Remove now-unused imports**

Inside the old function body the imports `from data.loader import bot` and `import data.config as _cfg` were only used here. Check the top of the file — if they are not used elsewhere, leave them (they may be used by other handlers in the same module). If they are local to `_forward_to_admins`, they were inside the `try:` block and are already gone with the rewrite.

- [ ] **Step 4: Run the suite**

Run: `docker compose --profile test run --rm test`
Expected: no new failures. (No dedicated test for `_forward_to_admins` exists; the smoke check is the integration test after deploy.)

- [ ] **Step 5: Commit**

```bash
git add web/routers/support.py
git commit -m "refactor(support): forward via send_admins, route to questions topic"
```

---

## Task 6: Topic guard in `handlers/support_web.py` — TDD

**Files:**
- Modify: `tests/unit/test_support_reply.py` — extend `_make_reply_message`, add wrong-topic test, set `SUPPORT_THREAD_QUESTIONS` in existing tests
- Modify: `handlers/support_web.py:21-29` — add thread guard before the existing chat-id check

### Step 6.1: Extend the test helper to set message_thread_id

- [ ] **Update `_make_reply_message`**

In `tests/unit/test_support_reply.py`, change the helper signature and body:

```python
def _make_reply_message(
    from_user_id: int,
    chat_id: int,
    replied_text: str,
    msg_text: str,
    message_thread_id: int | None = 3,
) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = from_user_id
    msg.chat.id = chat_id
    msg.text = msg_text
    msg.message_id = 42
    msg.message_thread_id = message_thread_id
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.text = replied_text
    msg.bot.send_message = AsyncMock()
    return msg
```

Default `3` matches the topic id we'll set in `data.config.SUPPORT_THREAD_QUESTIONS` for all the existing positive tests.

- [ ] **Step 6.2: Set `SUPPORT_THREAD_QUESTIONS = 3` in the three existing tests**

In `test_admin_reply_saved`, `test_non_admin_reply_ignored`, and `test_admin_stored_as_internal_id_can_reply`, add the monkeypatch right after the existing `SUPPORT_CHAT_ID` monkeypatch:

```python
monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
```

`test_reply_from_wrong_chat_ignored` doesn't need it (the chat_id check returns early), but add it anyway for symmetry.

- [ ] **Step 6.3: Add the new wrong-topic test at the end of the file**

```python
def test_reply_in_wrong_topic_ignored(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)

    msg = _make_reply_message(
        from_user_id=111,
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="answer",
        message_thread_id=99,  # admin replied in some other topic
    )

    from handlers.support_web import admin_reply_to_support
    asyncio.run(admin_reply_to_support(msg))

    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT count(*) FROM support_messages WHERE direction = 'admin'"
        ).fetchone()[0]
    assert count == 0
```

- [ ] **Step 6.4: Run the suite — wrong-topic test should fail, others should still pass**

Run: `docker compose --profile test run --rm test tests/unit/test_support_reply.py -v`
Expected: `test_reply_in_wrong_topic_ignored` FAILs (handler currently doesn't check thread id, so it processes and inserts an admin reply, breaking the assertion). All other four tests PASS.

### Step 6.5: Add the guard in `handlers/support_web.py`

- [ ] **Edit `admin_reply_to_support`**

Insert a new thread check immediately after the chat-id check at lines 21-23:

```python
@dp.message_handler(
    lambda m: m.reply_to_message is not None and m.reply_to_message.text is not None,
    content_types=["text"],
    state="*",
)
async def admin_reply_to_support(message: Message) -> None:
    import data.config as _cfg
    if message.chat.id != _cfg.SUPPORT_CHAT_ID:
        return
    if message.message_thread_id != _cfg.SUPPORT_THREAD_QUESTIONS:
        return
```

The rest of the function stays as-is.

- [ ] **Step 6.6: Re-run the suite**

Run: `docker compose --profile test run --rm test tests/unit/test_support_reply.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6.7: Run the full suite**

Run: `docker compose --profile test run --rm test`
Expected: no regressions.

- [ ] **Step 6.8: Commit**

```bash
git add tests/unit/test_support_reply.py handlers/support_web.py
git commit -m "feat(support): ignore admin replies outside the questions topic"
```

---

## Task 7: Startup validation — TDD

`validate_support_topics()` lives in `utils/sender.py` (so it's near the routing logic) and is called from `__main__.py:on_startup`.

**Files:**
- Create: `tests/unit/test_startup_validation.py`
- Modify: `utils/sender.py` — add `validate_support_topics`
- Modify: `__main__.py:on_startup` — call it first

### Step 7.1: Write the failing tests

- [ ] **Create `tests/unit/test_startup_validation.py`**

```python
"""Tests for utils.sender.validate_support_topics()."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


def test_fails_fast_when_errors_topic_missing(monkeypatch):
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import validate_support_topics
    with pytest.raises(SystemExit, match="SUPPORT_THREAD_ERRORS"):
        asyncio.run(validate_support_topics())


def test_passes_when_only_errors_topic_set(monkeypatch):
    """Errors topic alone is enough to start; warnings for missing categories go to it."""
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 0)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 0)

    from utils.sender import validate_support_topics
    asyncio.run(validate_support_topics())

    # Three warning sends (one per missing non-errors category), all into the errors thread.
    assert mock_send.call_count == 3
    for call in mock_send.call_args_list:
        assert call.kwargs["message_thread_id"] == 7
        assert "⚠️" in call.kwargs["text"]


def test_no_warnings_when_all_topics_set(monkeypatch):
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_QUESTIONS", 3)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ORDERS", 5)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_ERRORS", 7)
    monkeypatch.setattr("data.config.SUPPORT_THREAD_NEW_USERS", 9)

    from utils.sender import validate_support_topics
    asyncio.run(validate_support_topics())

    mock_send.assert_not_called()
```

- [ ] **Step 7.2: Run the new tests — all should fail**

Run: `docker compose --profile test run --rm test tests/unit/test_startup_validation.py -v`
Expected: all three tests FAIL with `ImportError: cannot import name 'validate_support_topics'`.

### Step 7.3: Implement `validate_support_topics`

- [ ] **Append to `utils/sender.py`**

After the `send_admins` definition, add:

```python
async def validate_support_topics() -> None:
    """Validate forum-topic configuration at bot startup.

    Raises SystemExit if SUPPORT_THREAD_ERRORS is unset — without it we have no
    place to surface other misconfiguration alerts. For any other unset category,
    emit a single ⚠️ warning into the errors topic and continue: the corresponding
    send_admins() calls will then be silent no-ops.
    """
    errors_thread = int(getattr(config, "SUPPORT_THREAD_ERRORS", 0) or 0)
    if errors_thread == 0:
        raise SystemExit(
            "SUPPORT_THREAD_ERRORS must be configured (forum topic id) — "
            "without it the bot has no channel for runtime alerts."
        )

    for category, attr in _CATEGORY_TO_CONFIG_ATTR.items():
        if category == "errors":
            continue
        if int(getattr(config, attr, 0) or 0) == 0:
            await send_admins(
                f"⚠️ <b>{attr} не задан</b>\n"
                f"Сообщения категории {category} не будут отправляться в группу.",
                "errors",
                parse_mode="HTML",
            )
```

- [ ] **Step 7.4: Re-run the validation tests**

Run: `docker compose --profile test run --rm test tests/unit/test_startup_validation.py -v`
Expected: all 3 PASS.

### Step 7.5: Wire it into `__main__.py:on_startup`

- [ ] **Edit `__main__.py`**

In `on_startup` (lines 88-118), insert the validation call as the very first line of the function body (before `_log.info("Bot startup")` is fine; the order doesn't matter as long as it's before `start_polling` returns):

```python
async def on_startup(dp: Dispatcher):
    from utils.sender import validate_support_topics
    await validate_support_topics()

    _log.info("Bot startup")
    # ... existing body unchanged
```

The import is lazy so test environments that don't need bot startup aren't forced to import sender at module load.

- [ ] **Step 7.6: Run the full suite**

Run: `docker compose --profile test run --rm test`
Expected: no regressions; the three new tests pass; sender tests still pass.

- [ ] **Step 7.7: Commit**

```bash
git add utils/sender.py tests/unit/test_startup_validation.py __main__.py
git commit -m "feat(startup): validate SUPPORT_THREAD_* env vars on bot boot"
```

---

## Task 8: Final verification before handoff

- [ ] **Step 1: Run the entire test suite one last time**

Run: `docker compose --profile test run --rm test`
Expected: all tests pass. Note the count for the PR description.

- [ ] **Step 2: Build the bot/api images to catch any syntax/import errors**

Run: `docker compose build bot api`
Expected: both images build cleanly.

- [ ] **Step 3: Sanity-check the diff against the spec**

Run: `git diff main --stat`
Expected: changes only in the files listed in the File Map.

Run: `git log main..HEAD --oneline`
Expected: 7 commits (Tasks 1, 2, 3, 4, 5, 6, 7).

- [ ] **Step 4: Confirm there are no leftover references to the old `send_admins(msg)` single-arg call**

Run: `grep -rn "send_admins([^,)]*)" --include="*.py" | grep -v tests/`
Expected: no matches (every production call now has a category arg). If anything turns up, fix it and amend the relevant commit.

- [ ] **Step 5: Confirm `.env.example` mentions the new vars (if it exists)**

Run: `ls -la .env.example 2>/dev/null && grep SUPPORT .env.example 2>/dev/null`
If the file exists and doesn't include the new vars, append:
```
SUPPORT_THREAD_QUESTIONS=3
SUPPORT_THREAD_ORDERS=5
SUPPORT_THREAD_ERRORS=7
SUPPORT_THREAD_NEW_USERS=9
```
and commit as `chore(env): document SUPPORT_THREAD_* example values`.

---

## Deploy Notes (post-merge — outside the scope of these tasks)

1. SSH `root@185.106.93.71`, edit `/opt/<app>/.env`, append:
   ```
   SUPPORT_THREAD_QUESTIONS=3
   SUPPORT_THREAD_ORDERS=5
   SUPPORT_THREAD_ERRORS=7
   SUPPORT_THREAD_NEW_USERS=9
   ```
2. `git pull dev && docker compose build api bot && docker compose up -d`
3. Verify bot is admin in group `-1003927517516` with right to write in topics.
4. Smoke check: trigger one of each category and confirm it lands in the correct topic.
