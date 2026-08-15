# Support Group Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route all admin-facing bot messages (support forwards + system notifications) to a single Telegram group instead of individual private chats, and fix the admin-reply handler so any admin in the list can respond regardless of how their ID is stored.

**Architecture:** Add `SUPPORT_CHAT_ID` env var; replace per-admin loops in `send_admins` and `_forward_to_admins` with a single `bot.send_message` to the group; update the reply handler to gate on `chat.id == SUPPORT_CHAT_ID` and resolve admin IDs to Telegram IDs before comparing.

**Tech Stack:** Python, aiogram 2.x, SQLite, pytest, monkeypatch

---

## File Map

| File | Change |
|---|---|
| `.env.example` | add `SUPPORT_CHAT_ID` |
| `data/config.py` | add `SUPPORT_CHAT_ID` var |
| `tests/conftest.py` | add `stub.SUPPORT_CHAT_ID = 0` |
| `utils/sender.py` | replace `send_admins` loop; remove dead `send_admin` |
| `web/routers/support.py` | replace `_forward_to_admins` loop |
| `handlers/support_web.py` | fix reply handler: chat filter + ID resolution |
| `tests/unit/test_sender.py` | new — `send_admins` sends to group |
| `tests/unit/test_support_reply.py` | new — reply handler acceptance + rejection cases |

---

### Task 1: Add SUPPORT_CHAT_ID config

**Files:**
- Modify: `.env.example`
- Modify: `data/config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add to `.env.example`**

After the `ADMINS=...` line, add:

```
SUPPORT_CHAT_ID=-5046696879
```

- [ ] **Step 2: Add to `data/config.py`**

After the `ADMINS` line:

```python
SUPPORT_CHAT_ID: int = int(os.getenv("SUPPORT_CHAT_ID", "0"))
```

- [ ] **Step 3: Add to conftest config stub**

In `tests/conftest.py`, inside `_make_config_stub()`, after `stub.ADMINS = []`:

```python
stub.SUPPORT_CHAT_ID = 0
```

- [ ] **Step 4: Run existing tests to confirm nothing broke**

```bash
pytest tests/ -q
```

Expected: all tests pass (same count as before).

- [ ] **Step 5: Commit**

```bash
git add .env.example data/config.py tests/conftest.py
git commit -m "feat(config): add SUPPORT_CHAT_ID env var"
```

---

### Task 2: Fix `utils/sender.py` — send to group

**Files:**
- Create: `tests/unit/test_sender.py`
- Modify: `utils/sender.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_sender.py`:

```python
"""Tests for utils/sender.py."""
from __future__ import annotations

from unittest.mock import AsyncMock


async def test_send_admins_sends_to_group(monkeypatch):
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    from utils import sender
    await sender.send_admins("hello group")

    mock_send.assert_called_once_with(
        chat_id=-100500,
        text="hello group",
        disable_web_page_preview=True,
    )


async def test_send_admins_does_not_loop_individuals(monkeypatch):
    """Must call bot.send_message exactly once, regardless of admin list size."""
    import sqlite3
    mock_send = AsyncMock()
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    from utils import sender
    await sender.send_admins("one call only")

    assert mock_send.call_count == 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_sender.py -v
```

Expected: FAILED — `send_admins` currently loops over admin list, `call_count > 1` or chat_id mismatch.

- [ ] **Step 3: Rewrite `utils/sender.py`**

Replace entire file content (removes dead `send_admin` and `send_managers` functions — neither has callers in production code):

```python
import data.config as config
from data.loader import bot


async def send_admins(msg: str):
    await bot.send_message(
        chat_id=config.SUPPORT_CHAT_ID,
        text=msg,
        disable_web_page_preview=True,
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_sender.py -v
```

Expected: PASSED.

- [ ] **Step 5: Run full suite to catch regressions**

```bash
pytest tests/ -q
```

Expected: all tests pass. Any failures from tests that mock `utils.sender.send_admins` still pass because the function signature is unchanged.

- [ ] **Step 6: Commit**

```bash
git add utils/sender.py tests/unit/test_sender.py
git commit -m "feat(sender): route send_admins to support group chat"
```

---

### Task 3: Fix `web/routers/support.py` — forward to group

**Files:**
- Modify: `web/routers/support.py`

- [ ] **Step 1: Write a failing unit test**

Add to `tests/web/test_routers_support.py` (append at end of file):

```python
async def test_forward_to_admins_sends_to_group(monkeypatch, tmp_db):
    import sqlite3
    from unittest.mock import AsyncMock, MagicMock

    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text) "
            "VALUES (5, 10, 'user', 'Help')"
        )
        con.commit()

    sent_mock = MagicMock()
    sent_mock.message_id = 99
    mock_send = AsyncMock(return_value=sent_mock)
    monkeypatch.setattr("data.loader.bot.send_message", mock_send)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    from web.routers.support import _forward_to_admins
    await _forward_to_admins(10, 5, "Help")

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["chat_id"] == -100500

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT tg_message_id FROM support_messages WHERE id = 5"
        ).fetchone()
    assert row[0] == 99
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/web/test_routers_support.py::test_forward_to_admins_sends_to_group -v
```

Expected: FAILED — current code loops over admins, not one call to group.

- [ ] **Step 3: Rewrite `_forward_to_admins` in `web/routers/support.py`**

Replace the entire `_forward_to_admins` function (lines 50-88) with:

```python
async def _forward_to_admins(user_id: int, msg_id: int, text: str) -> None:
    try:
        from data.loader import bot
        import data.config as _cfg
        from services import identity
        from services.db import connect as db_connect

        try:
            u = identity.get_user(user_id)
            user_str = f"@{u.user_name}" if u.user_name else f"ID {user_id}"
        except Exception:
            user_str = f"ID {user_id}"

        fwd_text = (
            f"💬 <b>{_SUPPORT_TAG} #{msg_id}</b>\n"
            f"От: {user_str}\n\n{text}"
        )

        sent = await bot.send_message(
            chat_id=_cfg.SUPPORT_CHAT_ID,
            text=fwd_text,
            parse_mode="HTML",
        )

        with db_connect() as con:
            con.execute(
                "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
                (sent.message_id, msg_id),
            )
            con.commit()
    except Exception:
        logger.exception("_forward_to_admins failed for user_id=%s", user_id)
```

Also remove the now-unused imports at the top of the file. The current file imports nothing at module level (all imports are inside the function), so no top-level changes needed.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/web/test_routers_support.py -v
```

Expected: all pass including the new test.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add web/routers/support.py tests/web/test_routers_support.py
git commit -m "feat(support): forward to group chat, fix tg_message_id save"
```

---

### Task 4: Fix `handlers/support_web.py` — reply handler

**Files:**
- Create: `tests/unit/test_support_reply.py`
- Modify: `handlers/support_web.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_support_reply.py`:

```python
"""Tests for handlers/support_web.py — admin reply handler."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_reply_message(
    from_user_id: int,
    chat_id: int,
    replied_text: str,
    msg_text: str,
) -> MagicMock:
    msg = MagicMock()
    msg.from_user.id = from_user_id
    msg.chat.id = chat_id
    msg.text = msg_text
    msg.message_id = 42
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.text = replied_text
    msg.bot.send_message = AsyncMock()
    return msg


def _stub_httpx(monkeypatch) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_client)
    monkeypatch.setattr("web.config.BOT_TOKEN", "test:token")


def _seed(tmp_db: Path, admin_value: str = "111") -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text) "
            "VALUES (7, 10, 'user', 'Help!')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', ?)",
            (admin_value,),
        )
        con.commit()


async def test_admin_reply_saved(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    _stub_httpx(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=111,
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="Here is your answer",
    )

    from handlers.support_web import admin_reply_to_support
    await admin_reply_to_support(msg)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT direction, text FROM support_messages WHERE direction = 'admin'"
        ).fetchone()
    assert row == ("admin", "Here is your answer")


async def test_reply_from_wrong_chat_ignored(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=111,
        chat_id=99999,  # not the support group
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="answer",
    )

    from handlers.support_web import admin_reply_to_support
    await admin_reply_to_support(msg)

    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT count(*) FROM support_messages WHERE direction = 'admin'"
        ).fetchone()[0]
    assert count == 0


async def test_non_admin_reply_ignored(monkeypatch, tmp_db: Path):
    _seed(tmp_db, admin_value="111")
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=9999,  # not in admin list
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="answer",
    )

    from handlers.support_web import admin_reply_to_support
    await admin_reply_to_support(msg)

    with sqlite3.connect(tmp_db) as con:
        count = con.execute(
            "SELECT count(*) FROM support_messages WHERE direction = 'admin'"
        ).fetchone()[0]
    assert count == 0


async def test_admin_stored_as_internal_id_can_reply(monkeypatch, tmp_db: Path):
    """Regression: admin stored as internal user_id (not TG ID) must still be able to reply."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (10, 'alice', 'Alice', 0, '2026-01-01')"
        )
        con.execute(
            "INSERT INTO support_messages(id, user_id, direction, text) "
            "VALUES (7, 10, 'user', 'Help!')"
        )
        # Admin stored by internal user_id=42; their Telegram ID is 999888777
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier) "
            "VALUES (42, 'telegram', '999888777')"
        )
        con.execute(
            "INSERT INTO settings(parametr, description, value) "
            "VALUES ('admins', 'admins', '42')"
        )
        con.commit()

    _stub_httpx(monkeypatch)
    monkeypatch.setattr("data.config.SUPPORT_CHAT_ID", -100500)

    msg = _make_reply_message(
        from_user_id=999888777,  # Telegram ID, while admin list stores internal ID 42
        chat_id=-100500,
        replied_text="💬 Вопрос из веб #7\nОт: @alice\n\nHelp!",
        msg_text="Fixed!",
    )

    from handlers.support_web import admin_reply_to_support
    await admin_reply_to_support(msg)

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT direction, text FROM support_messages WHERE direction = 'admin'"
        ).fetchone()
    assert row == ("admin", "Fixed!")
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/unit/test_support_reply.py -v
```

Expected: FAILED — current handler lacks chat filter and has ID mismatch bug.

- [ ] **Step 3: Rewrite `handlers/support_web.py`**

Replace entire file:

```python
"""Bot handler: admin reply to a web support message -> stored in support_messages."""
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
    import data.config as _cfg
    if message.chat.id != _cfg.SUPPORT_CHAT_ID:
        return

    from utils.sqlite3 import get_admins, get_tg_id_for_user
    admin_tg_ids = {get_tg_id_for_user(int(a)) or int(a) for a in get_admins()}
    if message.from_user.id not in admin_tg_ids:
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
    create_admin_reply(user_id, message.text, message.message_id)

    tg_id = get_tg_id_for_user(user_id)
    if tg_id:
        try:
            await message.bot.send_message(
                chat_id=tg_id,
                text=f"💬 Ответ поддержки:\n{message.text}",
            )
        except Exception:
            logger.warning("could not notify user_id=%s in TG", user_id)

    try:
        import httpx
        from web.config import BOT_TOKEN
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": message.chat.id,
                "message_id": message.message_id,
                "reaction": [{"type": "emoji", "emoji": "👍"}],
            })
        if resp.status_code != 200:
            logger.warning(
                "setMessageReaction failed: status=%s body=%s",
                resp.status_code, resp.text[:200],
            )
    except Exception:
        logger.exception("could not set 👍 reaction on admin reply")

    logger.info("support reply saved for user_id=%s, msg_id=%s", user_id, msg_id)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_support_reply.py -v
```

Expected: all 4 tests PASSED.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add handlers/support_web.py tests/unit/test_support_reply.py
git commit -m "fix(support): gate reply handler on group chat, fix admin ID resolution"
```

---

## Final verification

- [ ] Run full test suite one last time

```bash
pytest tests/ -v
```

Expected: all tests green.

- [ ] Manually verify in Telegram: send a message from web chat → appears in group → admin replies → user receives notification.
