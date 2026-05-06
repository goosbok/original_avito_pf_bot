"""CRUD для сторонних приложений и их API-ключей.

API-ключи хранятся как sha256-хеши. На создании возвращаем plaintext один раз — клиент должен сохранить.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services.db import connect
from services.exceptions import ApplicationNotFound


@dataclass(frozen=True)
class Application:
    id: int
    owner_user_id: int
    name: str
    api_key_prefix: str  # для отображения
    created_at: str
    revoked_at: Optional[str]


@dataclass(frozen=True)
class CreatedApplication:
    application: Application
    api_key: str  # plaintext, показать клиенту один раз


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_api_key() -> str:
    """Формат: sk_live_<32 hex chars>."""
    return "sk_live_" + secrets.token_hex(16)


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def create(owner_user_id: int, name: str) -> CreatedApplication:
    if not name.strip():
        raise ValueError("application name cannot be empty")

    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)
    api_key_prefix = api_key[:12]
    now = _now_iso()

    with connect() as con:
        cur = con.execute(
            "INSERT INTO applications(owner_user_id, name, api_key_hash, api_key_prefix, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_user_id, name, api_key_hash, api_key_prefix, now),
        )
        app_id = int(cur.lastrowid)
        con.commit()

    app = Application(
        id=app_id,
        owner_user_id=owner_user_id,
        name=name,
        api_key_prefix=api_key_prefix,
        created_at=now,
        revoked_at=None,
    )
    return CreatedApplication(application=app, api_key=api_key)


def list_for_user(owner_user_id: int) -> list[Application]:
    with connect() as con:
        rows = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE owner_user_id = ? ORDER BY created_at DESC",
            (owner_user_id,),
        ).fetchall()
    return [Application(**dict(r)) for r in rows]


def get(app_id: int) -> Application:
    with connect() as con:
        row = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE id = ?",
            (app_id,),
        ).fetchone()
    if row is None:
        raise ApplicationNotFound(f"application_id={app_id}")
    return Application(**dict(row))


def revoke(app_id: int, owner_user_id: int) -> None:
    """Soft-revoke: запоминаем revoked_at. Только владелец может revoke."""
    app = get(app_id)
    if app.owner_user_id != owner_user_id:
        raise ApplicationNotFound(f"application_id={app_id} (not owned)")
    with connect() as con:
        con.execute(
            "UPDATE applications SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_now_iso(), app_id),
        )
        con.commit()


def find_by_api_key(api_key: str) -> Optional[Application]:
    """Найти приложение по plaintext API-ключу. None если не найдено или revoked."""
    api_key_hash = _hash_api_key(api_key)
    with connect() as con:
        row = con.execute(
            "SELECT id, owner_user_id, name, api_key_prefix, created_at, revoked_at "
            "FROM applications WHERE api_key_hash = ? AND revoked_at IS NULL",
            (api_key_hash,),
        ).fetchone()
    return Application(**dict(row)) if row else None
