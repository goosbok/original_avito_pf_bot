# Admin User Search — TG ID Support & Multi-Result Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all four admin user flows (balance, delete, VIP+, VIP−) find users by system ID, Telegram ID, or username — and show paginated results when multiple matches exist.

**Architecture:** Extend `find_user()` to return `list[dict]` searching both `users.id` and `auth_providers` (via existing `get_user_by_tg_id`). Add a shared `handle_user_input()` helper that routes to next state (1 match) or pagination FSM (`Admin.select_user`, multiple matches). Add one keyboard function `user_select_kb()`.

**Tech Stack:** Python 3, aiogram 2.x FSM, SQLite via `utils/sqlite3.py`, pytest + pytest-asyncio

---

## File Map

| File | Change |
|---|---|
| `handlers/admin_base.py` | `find_user()` → `list[dict]`; add `Admin.select_user` state |
| `handlers/admin_users.py` | Add `handle_user_input()`, `_proceed()`, `_show_candidate()`; adapt 4 handlers; add pagination callback handler |
| `keyboards/inline_keyboards.py` | Add `user_select_kb(page, total)` |
| `tests/unit/test_admin_find_user.py` | New — unit tests for `find_user()` logic |
| `tests/unit/test_admin_user_select_kb.py` | New — unit tests for `user_select_kb()` |

---

## Task 1: Add `user_select_kb()` to keyboards

**Files:**
- Modify: `keyboards/inline_keyboards.py` (append after last function)
- Create: `tests/unit/test_admin_user_select_kb.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_admin_user_select_kb.py`:

```python
"""Tests for user_select_kb keyboard."""
from __future__ import annotations
import pytest


@pytest.fixture(autouse=True)
def _tmp(tmp_db):
    """Ensure schema is loaded before importing keyboards."""


def test_single_result_no_nav_arrows(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=0, total=1)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" not in cb_data
    assert "usel:next" not in cb_data
    assert "usel:pick" in cb_data
    assert "usel:cancel" in cb_data


def test_middle_page_has_both_arrows(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=1, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" in cb_data
    assert "usel:next" in cb_data


def test_first_page_no_prev(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=0, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" not in cb_data
    assert "usel:next" in cb_data


def test_last_page_no_next(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=2, total=3)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    cb_data = {b.callback_data for b in all_buttons}
    assert "usel:prev" in cb_data
    assert "usel:next" not in cb_data


def test_counter_button_text(tmp_db):
    from keyboards.inline_keyboards import user_select_kb
    kb = user_select_kb(page=1, total=5)
    nav_row = kb.inline_keyboard[0]
    texts = [b.text for b in nav_row]
    assert "2/5" in texts
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/test_admin_user_select_kb.py -v 2>&1 | tail -20
```

Expected: ImportError or AttributeError — `user_select_kb` not defined yet.

- [ ] **Step 3: Add `user_select_kb` to keyboards**

In `keyboards/inline_keyboards.py`, append at the end of the file:

```python
def user_select_kb(page: int, total: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("←", callback_data="usel:prev"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total}", callback_data="usel:noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("→", callback_data="usel:next"))
    kb.row(*nav)
    kb.add(InlineKeyboardButton("✅ Выбрать этого", callback_data="usel:pick"))
    kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="usel:cancel"))
    return kb
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/test_admin_user_select_kb.py -v 2>&1 | tail -20
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add keyboards/inline_keyboards.py tests/unit/test_admin_user_select_kb.py
git commit -m "feat(admin): add user_select_kb pagination keyboard"
```

---

## Task 2: Extend `find_user()` to return list and search by TG ID

**Files:**
- Modify: `handlers/admin_base.py`
- Create: `tests/unit/test_admin_find_user.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_admin_find_user.py`:

```python
"""Tests for find_user() in handlers.admin_base."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _seed(tmp_db: Path):
    with sqlite3.connect(tmp_db) as con:
        # Legacy user: id == tg_id (old schema style)
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (111, 'legacy_user', 'Лёша', 0, '2026-01-01')"
        )
        # New user: id is a large random number, tg_id in auth_providers
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (8794553795, '', 'Андрей', 0, '2026-07-01')"
        )
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, verified) "
            "VALUES (8794553795, 'telegram', '385609378', 1)"
        )
        # Another user found only by username
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (222, 'alice', 'Alice', 0, '2026-03-01')"
        )
        con.execute("INSERT INTO settings(parametr, description, value) VALUES ('admins','admins','1')")
        con.commit()


@pytest.mark.asyncio
async def test_find_by_system_id_returns_list(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("111")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == 111


@pytest.mark.asyncio
async def test_find_by_tg_id_returns_user(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("385609378")
    assert len(result) == 1
    assert result[0]["id"] == 8794553795


@pytest.mark.asyncio
async def test_find_by_username_without_at(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("alice")
    assert len(result) == 1
    assert result[0]["user_name"] == "alice"


@pytest.mark.asyncio
async def test_find_by_username_with_at(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("@alice")
    assert len(result) == 1
    assert result[0]["user_name"] == "alice"


@pytest.mark.asyncio
async def test_not_found_returns_empty_list(tmp_db: Path):
    _seed(tmp_db)
    from handlers.admin_base import find_user
    result = await find_user("999999")
    assert result == []


@pytest.mark.asyncio
async def test_dedup_when_id_equals_tg_id(tmp_db: Path):
    """Legacy user whose users.id == their TG ID → found by both paths → dedup to 1."""
    _seed(tmp_db)
    # Give legacy user a matching auth_providers entry
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, verified) "
            "VALUES (111, 'telegram', '111', 1)"
        )
        con.commit()
    from handlers.admin_base import find_user
    result = await find_user("111")
    assert len(result) == 1
    assert result[0]["id"] == 111
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/test_admin_find_user.py -v 2>&1 | tail -20
```

Expected: failures because `find_user` currently returns `dict | None`, not `list`.

- [ ] **Step 3: Update `find_user()` in `handlers/admin_base.py`**

Replace the import line at the top of `handlers/admin_base.py`:
```python
from utils.sqlite3 import get_admins, get_user, get_order, delete_order
```
with:
```python
from utils.sqlite3 import get_admins, get_user, get_order, delete_order, get_user_by_tg_id
```

Replace the entire `find_user` function (lines 38–52):
```python
async def find_user(param: str) -> list[dict]:
    results = []
    stripped = param.lstrip('@')
    if stripped.isdigit():
        by_id = get_user(id=stripped)
        by_tg = get_user_by_tg_id(stripped)
        seen: set = set()
        for u in [by_id, by_tg]:
            if u and u['id'] not in seen:
                seen.add(u['id'])
                results.append(u)
    else:
        u = get_user(user_name=stripped)
        if u:
            results.append(u)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/test_admin_find_user.py -v 2>&1 | tail -20
```

Expected: 6 passed.

- [ ] **Step 5: Add `Admin.select_user` state to StatesGroup in `handlers/admin_base.py`**

In the `Admin(StatesGroup)` class, add `select_user`:
```python
class Admin(StatesGroup):
    del_promik = State()
    new_promik = State()
    new_promik_price = State()
    del_user = State()
    user_info = State()
    select_user = State()   # ← add this line
```

- [ ] **Step 6: Run full unit tests to check no regressions**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all pass (new tests + no regressions).

- [ ] **Step 7: Commit**

```bash
git add handlers/admin_base.py tests/unit/test_admin_find_user.py
git commit -m "feat(admin): extend find_user to return list, search by TG ID via auth_providers"
```

---

## Task 3: Add shared helpers and pagination handler to `handlers/admin_users.py`

**Files:**
- Modify: `handlers/admin_users.py`

This task adds the three private helpers and the pagination callback handler. The four existing handlers are adapted in Task 4.

- [ ] **Step 1: Add imports to `handlers/admin_users.py`**

Replace the existing imports block at the top of the file:

```python
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile
from aiogram.dispatcher.filters.state import State, StatesGroup

from data.loader import dp, bot
from utils.sqlite3 import (
    get_user, update_user, delete_user, all_users, get_all_vip, get_tg_id_for_user,
    get_all_telegram_ids,
)
from utils.other import get_user_string_without_first_name
from keyboards.inline_keyboards import admin_back_kb, user_select_kb
from .admin_base import Admin, find_user
```

- [ ] **Step 2: Add helpers and pagination handler**

After the imports (before `class balance(StatesGroup)`), insert:

```python
async def _show_candidate(target, state: FSMContext) -> None:
    """Send current candidate card with pagination keyboard."""
    data = await state.get_data()
    candidates = data["candidates"]
    page = data["page"]
    usr = candidates[page]
    usr_str = await get_user_string_without_first_name(usr)
    text = f"🔍 Найдено {len(candidates)} пользователей. Выберите нужного:\n\n🐹 {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>"
    kb = user_select_kb(page, len(candidates))
    # target can be types.Message or types.CallbackQuery
    msg = target.message if hasattr(target, "message") else target
    await msg.answer(text, reply_markup=kb)


async def _proceed(target, state: FSMContext, usr: dict, action: str) -> None:
    """Route to the appropriate next step for the given action."""
    if action == "balance":
        usr_str = await get_user_string_without_first_name(usr)
        msg = target.message if hasattr(target, "message") else target
        await msg.answer(f"Выбран\n🐹 Пользователь {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>")
        await state.update_data(usr=usr)
        await balance.change_balance.set()
        await msg.answer("💳 Введите новый баланс:")
    elif action == "del":
        usr_str = await get_user_string_without_first_name(usr)
        msg = target.message if hasattr(target, "message") else target
        try:
            delete_user(usr['id'])
            await msg.answer(f"✅ Пользователь {usr_str} успешно удален!", reply_markup=admin_back_kb('users_man'))
        except Exception as e:
            logger.exception("handler error")
            await msg.answer(f"❎ Ошибка удаления пользователя!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif action == "vip_set":
        usr_str = await get_user_string_without_first_name(usr)
        # target is types.Message or types.CallbackQuery — get admin tg id from either
        adm_tg_id = target.from_user.id if hasattr(target, "from_user") else None
        adm_usr = get_user(id=adm_tg_id) if adm_tg_id else None
        msg = target.message if hasattr(target, "message") else target
        if usr['is_vip'] != 1:
            update_user(id=usr['id'], is_vip=1)
            await msg.answer(f"🐹 Пользователь {usr_str} получил 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id and adm_usr:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} установил Вам 💎VIP-статус!")
        else:
            await msg.answer(f"🐹 Пользователь {usr_str} уже имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif action == "vip_unset":
        usr_str = await get_user_string_without_first_name(usr)
        adm_tg_id = target.from_user.id if hasattr(target, "from_user") else None
        adm_usr = get_user(id=adm_tg_id) if adm_tg_id else None
        msg = target.message if hasattr(target, "message") else target
        if usr['is_vip'] != 0:
            update_user(id=usr['id'], is_vip=0)
            await msg.answer(f"🐹 Пользователь {usr_str} потерял 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id and adm_usr:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} отменил Вам 💎VIP-статус!")
        else:
            await msg.answer(f"🐹 Пользователь {usr_str} не имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()


async def handle_user_input(message: types.Message, state: FSMContext, action: str) -> None:
    """Shared entry point for all four admin user flows."""
    users = await find_user(message.text)
    if len(users) == 0:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    elif len(users) == 1:
        await _proceed(message, state, users[0], action)
    else:
        await state.update_data(candidates=users, page=0, pending_action=action)
        await Admin.select_user.set()
        await _show_candidate(message, state)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("usel:"), state=Admin.select_user)
async def usel_nav(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split(":")[1]
    if action == "noop":
        await call.answer()
        return
    if action == "cancel":
        await call.answer()
        await state.finish()
        await call.message.answer("❌ Отменено.", reply_markup=admin_back_kb('users_man'))
        return
    data = await state.get_data()
    candidates = data["candidates"]
    page = data["page"]
    if action == "prev":
        page = max(0, page - 1)
    elif action == "next":
        page = min(len(candidates) - 1, page + 1)
    elif action == "pick":
        pending = data["pending_action"]
        await call.answer()
        try:
            await call.message.delete()
        except Exception:
            pass
        await _proceed(call, state, candidates[page], pending)
        return
    await state.update_data(page=page)
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_candidate(call.message, state)
```

- [ ] **Step 3: Run unit tests (no regressions)**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add handlers/admin_users.py
git commit -m "feat(admin): add handle_user_input, _proceed, _show_candidate helpers and usel pagination handler"
```

---

## Task 4: Adapt the four existing admin handlers to use `handle_user_input`

**Files:**
- Modify: `handlers/admin_users.py`

- [ ] **Step 1: Replace `usr_sel` (balance flow)**

Find and replace the entire `usr_sel` handler:

Old code:
```python
@dp.message_handler(state=balance.select_user)
async def usr_sel(message: types.Message, state: FSMContext):
    usr = await find_user(message.text)
    if not usr:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
        return
    try:
        usr_str = await get_user_string_without_first_name(usr)
        await message.answer(f"Выбран\n🐹 Пользователь {usr_str}\n💳 Баланс: <b>{usr['balance']}</b>")
        await state.update_data(usr=usr)
        await balance.change_balance.set()
        await message.answer("💳 Введите новый баланс:")
    except Exception as e:
        logger.exception("handler error")
        await message.answer(f"⚠️ Ошибка!:\n{e}")
        await state.finish()
```

New code:
```python
@dp.message_handler(state=balance.select_user)
async def usr_sel(message: types.Message, state: FSMContext):
    await handle_user_input(message, state, "balance")
```

- [ ] **Step 2: Replace `del_usr` (delete flow)**

Find and replace:

Old code:
```python
@dp.message_handler(state=Admin.del_user)
async def del_usr(message: types.Message, state: FSMContext):
    delUser = await find_user(message.text)
    if not delUser:
        await message.answer(f"⚠️ Пользователь {message.text} не найден!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
        return
    usr_str = await get_user_string_without_first_name(delUser)
    try:
        delete_user(delUser['id'])
        await message.answer(f"✅ Пользователь {usr_str} успешно удален!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        logger.exception("handler error")
        await message.answer(f"❎ Ошибка удаления пользователя!\n{e}", reply_markup=admin_back_kb('users_man'))
        await state.finish()
```

New code:
```python
@dp.message_handler(state=Admin.del_user)
async def del_usr(message: types.Message, state: FSMContext):
    await handle_user_input(message, state, "del")
```

- [ ] **Step 3: Replace `vip_set` (VIP+ flow)**

Find and replace:

Old code:
```python
@dp.message_handler(state=vip.set_status)
async def vip_set(message: types.Message, state: FSMContext, user_id: int):
    try:
        usr = await find_user(message.text)
        adm_usr = get_user(id=user_id)
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 1:
            update_user(id=usr['id'], is_vip=1)
            await message.answer(f"🐹 Пользователь {usr_str} получил 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} установил Вам 💎VIP-статус!")
        else:
            await message.answer(f"🐹 Пользователь {usr_str} уже имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()
```

New code:
```python
@dp.message_handler(state=vip.set_status)
async def vip_set(message: types.Message, state: FSMContext):
    await handle_user_input(message, state, "vip_set")
```

- [ ] **Step 4: Replace `vip_unset` (VIP− flow)**

Find and replace:

Old code:
```python
@dp.message_handler(state=vip.unset_status)
async def vip_unset(message: types.Message, state: FSMContext, user_id: int):
    try:
        usr = await find_user(message.text)
        adm_usr = get_user(id=user_id)
        usr_str = await get_user_string_without_first_name(usr)
        if usr['is_vip'] != 0:
            update_user(id=usr['id'], is_vip=0)
            await message.answer(f"🐹 Пользователь {usr_str} потерял 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
            tg_id = get_tg_id_for_user(usr['id'])
            if tg_id:
                await bot.send_message(chat_id=tg_id, text=f"🤖 Пользователь @{adm_usr['user_name']} отменил Вам 💎VIP-статус!")
        else:
            await message.answer(f"🐹 Пользователь {usr_str} не имеет 💎VIP-статус!", reply_markup=admin_back_kb('users_man'))
        await state.finish()
    except Exception as e:
        await message.answer(f"⚠️ Ошибка!\n{e}")
    await state.finish()
```

New code:
```python
@dp.message_handler(state=vip.unset_status)
async def vip_unset(message: types.Message, state: FSMContext):
    await handle_user_input(message, state, "vip_unset")
```

- [ ] **Step 5: Run full unit tests**

```bash
docker exec original_avito_pf_bot-bot-1 python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add handlers/admin_users.py
git commit -m "feat(admin): adapt balance/delete/VIP handlers to use handle_user_input"
```

---

## Task 5: Smoke test on production bot

- [ ] **Step 1: Deploy to prod**

```bash
ssh -o ProxyJump=root@139.28.222.146 root@167.233.52.85 'cd /root/projects/original_avito_pf_bot && \
  git pull origin dev --ff-only && \
  docker compose build bot && \
  docker compose up -d --force-recreate bot && \
  sleep 5 && docker logs original_avito_pf_bot-bot-1 --tail 20'
```

- [ ] **Step 2: Manual smoke test**

In the admin bot:
1. Open admin panel → Управление пользователями → Изменить баланс
2. Enter `385609378` (a TG ID of a new-schema user)
3. Expected: bot finds "Андрей" (internal id 8794553795) and shows balance prompt
4. Enter `111` (if a legacy user with that system ID exists) — verify found by system ID
5. Enter a non-existent number — verify "не найден" response
6. If you can manufacture two matches: verify ← / → pagination appears

- [ ] **Step 3: Check logs for errors**

```bash
ssh -o ProxyJump=root@139.28.222.146 root@167.233.52.85 \
  'docker logs original_avito_pf_bot-bot-1 --since "5m" 2>&1 | grep -i "ERROR\|exception\|traceback" | head -20'
```

Expected: no errors.
