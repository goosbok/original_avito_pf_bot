# Admin User Search — TG ID Support & Multi-Result Pagination

**Date:** 2026-07-02  
**Status:** Approved

## Problem

`find_user()` in `handlers/admin_base.py` searches only by `users.id` (internal PK) and `user_name`. After the 2026-06-07 migration, new users have `users.id ≠ Telegram ID` (TG ID lives in `auth_providers`). Entering a TG ID like `385609378` returns nothing, even though the user exists.

## Goal

All four admin user flows (balance change, delete, VIP set, VIP unset) should find users by **system internal ID**, **Telegram ID**, or **username** — whichever the admin enters.

## Scope

- `handlers/admin_base.py` — `find_user()` signature change
- `handlers/admin_users.py` — four handlers adapted + new pagination handler
- `keyboards/inline_keyboards.py` — one new keyboard function

No new DB functions needed; `get_user_by_tg_id()` already exists in `utils/sqlite3.py`.

---

## Architecture

### 1. `find_user(param)` → `list[dict]`

**File:** `handlers/admin_base.py`

Changes signature from `dict | None` to `list[dict]`.

```python
async def find_user(param: str) -> list[dict]:
    results = []
    if param.lstrip('@').isdigit():
        num = param.lstrip('@')
        by_id = get_user(id=num)
        by_tg = get_user_by_tg_id(num)
        seen = set()
        for u in [by_id, by_tg]:
            if u and u['id'] not in seen:
                seen.add(u['id'])
                results.append(u)
    else:
        name = param.lstrip('@')
        u = get_user(user_name=name)
        if u:
            results.append(u)
    return results
```

Import `get_user_by_tg_id` added to the imports from `utils.sqlite3`.

### 2. Shared input handler `handle_user_input()`

**File:** `handlers/admin_users.py`

A coroutine called by all four entry-point message handlers:

```python
async def handle_user_input(message, state, action: str):
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
```

`_proceed(message, state, usr, action)` — routes to the appropriate next state / logic based on `action`.

`_show_candidate(message_or_call, state)` — reads `candidates[page]` from state, formats user info with `get_user_string_without_first_name`, sends with `user_select_kb(page, total)`.

### 3. `Admin.select_user` FSM state

**File:** `handlers/admin_base.py` — added to `Admin` StatesGroup.

FSM state data keys:
| Key | Type | Description |
|---|---|---|
| `candidates` | `list[dict]` | All matched users |
| `page` | `int` | Current index (0-based) |
| `pending_action` | `str` | `"balance"` / `"del"` / `"vip_set"` / `"vip_unset"` |

### 4. Pagination callback handler

**File:** `handlers/admin_users.py`

Single handler for `callback_data` prefix `usel:`:

- `usel:prev` — decrement page, redisplay
- `usel:next` — increment page, redisplay
- `usel:pick` — read `candidates[page]`, call `_proceed()`
- `usel:cancel` — `state.finish()`, show back button
- `usel:noop` — answer callback only (counter button, no action)

### 5. `user_select_kb(page, total)` keyboard

**File:** `keyboards/inline_keyboards.py`

```python
def user_select_kb(page: int, total: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("←", callback_data="usel:prev"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="usel:noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("→", callback_data="usel:next"))
    kb.row(*nav)
    kb.add(InlineKeyboardButton("✅ Выбрать этого", callback_data="usel:pick"))
    kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="usel:cancel"))
    return kb
```

---

## Data Flow

```
Admin inputs ID/username
        │
        ▼
   find_user(param)
   ┌─────────────┬──────────────────┐
   │  0 results  │   1 result       │  >1 results
   │             │                  │
   ▼             ▼                  ▼
not found    proceed to        store candidates
  + finish   next state        page=0 in FSM
                                    │
                              show card + nav kb
                                    │
                              ←/→ to flip pages
                                    │
                              ✅ pick → proceed
```

---

## Four admin flows after adaptation

| Flow | Entry state | After single match / pick | Next state |
|---|---|---|---|
| Balance | `balance.select_user` | show current balance | `balance.change_balance` |
| Delete | `Admin.del_user` | confirm + delete | finish |
| VIP set | `vip.set_status` | set is_vip=1 | finish |
| VIP unset | `vip.unset_status` | set is_vip=0 | finish |

Delete and VIP flows act immediately on selection (no extra input needed). Balance flow stores the selected user and advances to `balance.change_balance` for amount input.

---

## Error handling

- Numeric input matches same user via both paths → deduplicated by `users.id`
- `get_user_by_tg_id` returns `None` → skipped silently
- Pagination bounds: `←` hidden on page 0, `→` hidden on last page
- `usel:*` callbacks only handled in `Admin.select_user` state — stale buttons from old messages do nothing outside that state
