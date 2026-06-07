"""Identity layer — управление пользователями и привязанными способами входа.

Один user_id → много auth_providers. user_id всегда внутренний (auto-increment в users).
После миграции Phase 4 все пользователи имеют запись в auth_providers; legacy-путь
users.id == telegram_id удалён.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services.db import connect
from services.exceptions import (
    AccountMergeConflict,
    ProviderAlreadyLinked,
    UserNotFound,
)


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


def _find_legacy_user_by_id(uid: int) -> dict | None:
    """SELECT id FROM users WHERE id=uid. Returns dict or None.
    Used as fallback in get_or_create_user_by_telegram — legacy bot
    stored users.id == tg_id without auth_providers table."""
    with connect() as con:
        row = con.execute(
            "SELECT id FROM users WHERE id = ?", (int(uid),)
        ).fetchone()
    return dict(row) if row else None


def get_or_create_user_by_telegram(
    tg_id: int,
    *,
    user_name: Optional[str] = None,
    first_name: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> int:
    """Главный entry-point для бота.

    Если для tg_id есть auth_providers(provider='telegram') — возвращаем user_id.
    Иначе создаём нового юзера и привязываем telegram.
    """
    user_id = find_user_id_by_provider("telegram", str(tg_id))
    if user_id is not None:
        return user_id

    # Legacy-safety: legacy bot stored users.id == tg_id without auth_providers.
    # If such a row exists in `users` (e.g. backfill hasn't run, or DB was
    # restored from an older backup), claim it instead of creating a duplicate.
    legacy = _find_legacy_user_by_id(tg_id)
    if legacy is not None:
        link_provider(int(legacy["id"]), "telegram", str(tg_id))
        # Also update user_name / first_name if newer info available
        if user_name or first_name:
            from utils.sqlite3 import update_user
            kwargs = {}
            if user_name:
                kwargs["user_name"] = user_name
            if first_name:
                kwargs["first_name"] = first_name
            if kwargs:
                update_user(int(legacy["id"]), **kwargs)
        return int(legacy["id"])

    # Genuinely new user
    new_id = _create_user(user_name=user_name, first_name=first_name, ref_id=ref_id)
    link_provider(new_id, "telegram", str(tg_id))
    return new_id


def find_or_create_user_by_phone(phone: str, *, verified: bool = False) -> int:
    """Вернуть user_id, к которому привязан phone-provider.

    Если phone-провайдер не привязан — создать нового user'а и привязать phone
    (verified=0 по умолчанию: значит "введён в форме, ещё не подтверждён"; передавайте
    verified=True после успешной SMS-OTP-верификации).

    Не используется для merge-сценариев — для них есть `link_phone_provider`.
    """
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            (phone,),
        ).fetchone()
        if row:
            return int(row["user_id"])
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date) "
            "VALUES (NULL, NULL, 0, ?)",
            (_now_iso(),),
        )
        new_user_id = int(cur.lastrowid)
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (?, 'phone', ?, ?, ?)",
            (new_user_id, phone, _now_iso(), 1 if verified else 0),
        )
        con.commit()
        return new_user_id


def _is_phone_only_user(con, user_id: int) -> bool:
    """User считается phone-only, если у него ровно один provider — 'phone' с
    verified=0. То есть запись, созданная в `find_or_create_user_by_phone` для
    быстрого заказа, и больше ничего к нему не привязано. Такого user'а можно
    безопасно мерджить в полноценный аккаунт без потери смысла.
    """
    rows = con.execute(
        "SELECT provider, verified FROM auth_providers WHERE user_id=?",
        (user_id,),
    ).fetchall()
    return (
        len(rows) == 1
        and rows[0]["provider"] == "phone"
        and int(rows[0]["verified"] or 0) == 0
    )


def _merge_phone_only_into(
    con, *, source_user_id: int, target_user_id: int, set_verified: bool
) -> None:
    """Перенести orders/refills/notifications/balance с phone-only-source на
    реальный target. phone-provider пере-привязывается. Source-user удаляется.

    Вспомогательные таблицы (refills, notifications) переносим под try — если
    их в схеме нет (например, разные деплои / тесты), молча пропускаем.
    """
    con.execute(
        "UPDATE orders SET user_id=? WHERE user_id=?",
        (target_user_id, source_user_id),
    )
    try:
        con.execute(
            "UPDATE refills SET user_id=? WHERE user_id=?",
            (target_user_id, source_user_id),
        )
    except Exception:
        pass
    try:
        con.execute(
            "UPDATE notifications SET user_id=? WHERE user_id=?",
            (target_user_id, source_user_id),
        )
    except Exception:
        pass
    # phone-provider source → target, выставляем verified
    con.execute(
        "UPDATE auth_providers SET user_id=?, verified=? "
        "WHERE provider='phone' AND user_id=?",
        (target_user_id, 1 if set_verified else 0, source_user_id),
    )
    # Баланс source приклеиваем к target
    src_row = con.execute(
        "SELECT balance FROM users WHERE id=?", (source_user_id,)
    ).fetchone()
    if src_row:
        con.execute(
            "UPDATE users SET balance = balance + ? WHERE id=?",
            (int(src_row["balance"] or 0), target_user_id),
        )
    # Удаляем source
    con.execute("DELETE FROM users WHERE id=?", (source_user_id,))


def link_phone_provider(
    target_user_id: int,
    phone: str,
    *,
    set_verified: bool = False,
) -> None:
    """Привязать phone к target_user_id, резолвя коллизию по UNIQUE(provider,identifier).

    Правила:
    - phone не привязан → INSERT.
    - phone уже у target_user_id → no-op (опционально проставить verified=1).
    - phone у другого user'а, который **phone-only** (verified=0, единственный
      provider) → мерджим того user'а в target (orders/refills/notifications/balance).
    - В остальных случаях (другой user полноценный или phone у него verified=1)
      → `AccountMergeConflict`.
    """
    with connect() as con:
        existing = con.execute(
            "SELECT id, user_id, verified FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            (phone,),
        ).fetchone()

        if existing is None:
            con.execute(
                "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
                "VALUES (?, 'phone', ?, ?, ?)",
                (target_user_id, phone, _now_iso(), 1 if set_verified else 0),
            )
            con.commit()
            return

        if int(existing["user_id"]) == target_user_id:
            if set_verified and not int(existing["verified"] or 0):
                con.execute(
                    "UPDATE auth_providers SET verified=1 WHERE id=?",
                    (existing["id"],),
                )
                con.commit()
            return

        other_user_id = int(existing["user_id"])
        if _is_phone_only_user(con, other_user_id):
            _merge_phone_only_into(
                con,
                source_user_id=other_user_id,
                target_user_id=target_user_id,
                set_verified=set_verified,
            )
            con.commit()
            return

        raise AccountMergeConflict(other_user_id, target_user_id, phone)


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
