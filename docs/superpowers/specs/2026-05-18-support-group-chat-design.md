# Support Group Chat Design

**Date:** 2026-05-18

## Problem

Support messages from the web chat are forwarded to each admin's private bot chat individually. Two bugs result:

1. **Reply bug**: `admin_reply_to_support` compares `message.from_user.id` (always a Telegram ID) against `get_admins()` which may store internal DB user IDs. Admins stored as internal IDs receive the forwarded message but cannot reply.
2. **tg_message_id bug**: only the first admin's `message_id` is saved to `support_messages.tg_message_id`; all others are lost.

## Solution

Route all admin-facing messages — support forwards and system notifications — to a single Telegram group chat. One message, all admins see it, any eligible admin can reply.

## Configuration

- Add `SUPPORT_CHAT_ID` to `.env` and `.env.example` (value: `-5046696879`).
- Read in `data/config.py` as `SUPPORT_CHAT_ID: int = int(os.getenv("SUPPORT_CHAT_ID", "0"))`.

## Affected Files

### `utils/sender.py` — `send_admins()`

Replace the per-admin loop with a single `bot.send_message(chat_id=SUPPORT_CHAT_ID, ...)`.

Before:
```python
for admin in get_admins():
    tg_id = get_tg_id_for_user(int(admin)) or int(admin)
    await bot.send_message(chat_id=tg_id, text=msg, ...)
```

After:
```python
await bot.send_message(chat_id=SUPPORT_CHAT_ID, text=msg, ...)
```

`send_admin()` (hardcoded single-admin send) is removed — it has no callers in production code.

### `web/routers/support.py` — `_forward_to_admins()`

Replace the per-admin loop with a single send to `SUPPORT_CHAT_ID`. The returned `message_id` is saved to `support_messages.tg_message_id` (fixes the secondary bug).

```python
sent = await bot.send_message(chat_id=SUPPORT_CHAT_ID, text=fwd_text, parse_mode="HTML")
with db_connect() as con:
    con.execute(
        "UPDATE support_messages SET tg_message_id = ? WHERE id = ?",
        (sent.message_id, msg_id),
    )
```

Imports `get_admins`, `get_spam_exclude`, `get_tg_id_for_user` are removed from this function.

### `handlers/support_web.py` — `admin_reply_to_support()`

Two changes:

1. **Chat filter**: add `message.chat.id == SUPPORT_CHAT_ID` as early guard — only process replies from the admin group, not from any private chat.

2. **Admin ID check**: replace the direct string comparison with a resolved TG-ID set:
   ```python
   from utils.sqlite3 import get_admins, get_tg_id_for_user
   admin_tg_ids = {get_tg_id_for_user(int(a)) or int(a) for a in get_admins()}
   if message.from_user.id not in admin_tg_ids:
       return
   ```
   This mirrors the logic in `_forward_to_admins` so the set of admins who receive messages exactly matches the set who can reply.

3. **👍 reaction**: `chat_id` in `setMessageReaction` is now the group chat ID, not the admin's private chat — no change needed since `message.chat.id` is already used.

## Deployment Notes

- Bot must be an **admin** of the group (already done).
- Remove `ADMINS` env var if it was used as a fallback — `send_admins` no longer reads it.
- `send_admin()` has no production callers — safe to remove without additional changes.

## Out of Scope

- `utils/other_functions.py` has a dead duplicate `send_admins` — not imported anywhere in production code, leave as-is.
- Web admin panel (`web/admin_deps.py`) is unaffected; it already handles the TG-ID vs internal-ID duality correctly.
