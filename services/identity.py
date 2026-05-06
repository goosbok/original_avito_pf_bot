"""Identity layer — управление пользователями и привязанными способами входа.

Один user_id → много auth_providers. user_id всегда внутренний (auto-increment в users).
Существующие telegram-юзеры остались с users.id == telegram_id (исторический artifact),
но обращаться к ним нужно через identity.get_user_id_by_telegram(tg_id), не напрямую.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services.db import connect
from services.exceptions import ProviderAlreadyLinked, UserNotFound


@dataclass(frozen=True)
class User:
    id: int
    user_name: Optional[str]
    first_name: Optional[str]
    balance: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user(user_id: int) -> User:
    with connect() as con:
        row = con.execute(
            "SELECT id, user_name, first_name, balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise UserNotFound(f"user_id={user_id}")
    return User(
        id=row["id"],
        user_name=row["user_name"],
        first_name=row["first_name"],
        balance=int(row["balance"] or 0),
    )


def find_user_id_by_provider(provider: str, identifier: str) -> Optional[int]:
    """Вернёт user_id, если provider+identifier привязан, иначе None."""
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM auth_providers WHERE provider = ? AND identifier = ?",
            (provider, identifier),
        ).fetchone()
    return int(row["user_id"]) if row else None


def list_providers(user_id: int) -> list[dict]:
    """Список привязанных провайдеров. credential_hash не возвращаем."""
    with connect() as con:
        rows = con.execute(
            "SELECT provider, identifier, created_at, last_used_at "
            "FROM auth_providers WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _create_user(
    *,
    user_name: Optional[str] = None,
    first_name: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> int:
    """Низкоуровневая функция создания записи в users. Возвращает новый user_id."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date, ref_id) "
            "VALUES (?, ?, 0, ?, ?)",
            (user_name, first_name, _now_iso(), ref_id),
        )
        con.commit()
        return int(cur.lastrowid)


def link_provider(
    user_id: int,
    provider: str,
    identifier: str,
    credential_hash: Optional[str] = None,
) -> None:
    """Привязать новый способ входа к существующему юзеру.

    Если provider+identifier уже занят другим юзером — ProviderAlreadyLinked.
    Если этим же юзером — no-op (идемпотентно).
    """
    existing = find_user_id_by_provider(provider, identifier)
    if existing is not None:
        if existing == user_id:
            return
        raise ProviderAlreadyLinked(provider, identifier, existing)

    with connect() as con:
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, credential_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, provider, identifier, credential_hash, _now_iso()),
        )
        con.commit()


def unlink_provider(user_id: int, provider: str, identifier: str) -> None:
    """Удалить привязку. Не запрещаем удалить последнюю — это решение слоя выше."""
    with connect() as con:
        con.execute(
            "DELETE FROM auth_providers WHERE user_id = ? AND provider = ? AND identifier = ?",
            (user_id, provider, identifier),
        )
        con.commit()


def touch_provider(provider: str, identifier: str) -> None:
    """Обновить last_used_at — вызывать после успешного логина."""
    with connect() as con:
        con.execute(
            "UPDATE auth_providers SET last_used_at = ? WHERE provider = ? AND identifier = ?",
            (_now_iso(), provider, identifier),
        )
        con.commit()


def get_or_create_user_by_telegram(
    tg_id: int,
    *,
    user_name: Optional[str] = None,
    first_name: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> int:
    """Главный entry-point для бота.

    Если для tg_id есть auth_providers(provider='telegram') — возвращаем user_id.
    Иначе создаём нового юзера (или находим legacy-запись с users.id == tg_id, если есть)
    и привязываем telegram.
    """
    user_id = find_user_id_by_provider("telegram", str(tg_id))
    if user_id is not None:
        return user_id

    # Legacy fallback: возможно, существует запись users(id=tg_id) ещё с до-Phase-2 времён,
    # но миграция её не пропустила (rare). Переиспользуем.
    with connect() as con:
        row = con.execute("SELECT id FROM users WHERE id = ?", (tg_id,)).fetchone()
    if row is not None:
        link_provider(tg_id, "telegram", str(tg_id))
        return tg_id

    # Создаём нового
    new_id = _create_user(user_name=user_name, first_name=first_name, ref_id=ref_id)
    link_provider(new_id, "telegram", str(tg_id))
    return new_id


def get_or_create_user_by_email(
    email_normalized: str,
    *,
    credential_hash: str,
    first_name: Optional[str] = None,
) -> int:
    """Зарегистрировать нового юзера через email. Если email уже есть — EmailAlreadyRegistered."""
    from services.exceptions import EmailAlreadyRegistered

    existing = find_user_id_by_provider("email", email_normalized)
    if existing is not None:
        raise EmailAlreadyRegistered(email_normalized)

    new_id = _create_user(first_name=first_name)
    link_provider(new_id, "email", email_normalized, credential_hash=credential_hash)
    return new_id
