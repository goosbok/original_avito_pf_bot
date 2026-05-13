"""FastAPI dep + helper that gates /api/admin/* on Telegram-admin membership.

The "admin list" is shared with the bot via the legacy settings table read
through `utils.sqlite3.get_admins()`. A caller is admin if either:
  - their internal `users.id` is in the admin list (legacy bot users whose
    `users.id` IS their Telegram ID), or
  - their `auth_providers(provider='telegram')` identifier is in the admin
    list (modern web-registered users whose TG ID is decoupled from id).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from web.deps import require_user


def is_admin(user_id: int) -> bool:
    from utils.sqlite3 import get_admins, get_tg_id_for_user

    admin_tg_ids = {int(a) for a in get_admins()}
    if not admin_tg_ids:
        return False
    if int(user_id) in admin_tg_ids:
        return True
    tg_id = get_tg_id_for_user(int(user_id))
    return tg_id is not None and int(tg_id) in admin_tg_ids


async def require_admin(user_id: int = Depends(require_user)) -> int:
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="admin only")
    return user_id
