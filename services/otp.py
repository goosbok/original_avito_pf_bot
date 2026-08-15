"""OTP-коды для верификации действий пользователя.

Универсальный сервис для двух каналов доставки:
- channel='telegram', destination=str(tg_id) — отправляется через TG-бота.
- channel='sms', destination=E.164-phone — отправляется через SmsGateway
  (см. services/sms.py).

Хранение: `otp_codes(channel, destination, purpose, code_hash, ...)`.
Code хранится как sha256(code + pepper), где pepper = JWT_SECRET. Дамп БД
не выдаёт plaintext-коды.

Caller отвечает за фактическую доставку (через бот / SMS gateway).

API:
- `issue(*, channel, destination, purpose, ttl_seconds, cooldown_seconds, user_id_to_link=None) -> str`
  Генерирует plaintext code, сохраняет hash. Идемпотентность: предыдущие активные
  коды для (channel, destination, purpose) сжигаются. Если последний неконсьюмленый
  код был выдан < cooldown_seconds назад — raise OTPCooldown.
- `verify(*, channel, destination, code, purpose, max_attempts=MAX_ATTEMPTS) -> bool`
  True если код корректен (и помечает его consumed); False во всех остальных
  случаях кроме истечения TTL — `OTPExpired`. Лимит неверных попыток MAX_ATTEMPTS;
  после превышения код сжигается.
- `get_user_id_to_link(*, channel, destination, code, purpose) -> int | None`
  Peek user_id_to_link для verified-кода без consume — для UX, когда caller
  хочет проверить владельца до фактического consume.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from services.db import connect
from services.exceptions import OTPCooldown, OTPExpired

MAX_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    """sha256(code + pepper); pepper = JWT_SECRET. Защита от дампа БД."""
    from data import config
    pepper = getattr(config, "JWT_SECRET", "") or ""
    return hashlib.sha256((code + pepper).encode("utf-8")).hexdigest()


def _generate_code() -> str:
    """6-значный numeric code (компатибельно для Telegram и SMS UX)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def issue(
    *,
    channel: str,
    destination: str,
    purpose: str,
    ttl_seconds: int = 300,
    cooldown_seconds: int = 60,
    user_id_to_link: int | None = None,
) -> str:
    """Выпустить новый OTP. Возвращает plaintext code (для отправки caller'ом).

    Идемпотентность: предыдущие активные коды для (channel, destination, purpose)
    сжигаются (consumed_at <- now).

    Cooldown: если активный код выпущен < cooldown_seconds назад — OTPCooldown.
    Передавайте cooldown_seconds=0 чтобы отключить (нужно в тестах).
    """
    now = _now()
    with connect() as con:
        recent = con.execute(
            "SELECT created_at FROM otp_codes "
            "WHERE channel = ? AND destination = ? AND purpose = ? "
            "  AND consumed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (channel, destination, purpose),
        ).fetchone()
        if recent and cooldown_seconds > 0:
            recent_at = datetime.fromisoformat(recent["created_at"])
            elapsed = (now - recent_at).total_seconds()
            if elapsed < cooldown_seconds:
                raise OTPCooldown(int(cooldown_seconds - elapsed))

        con.execute(
            "UPDATE otp_codes SET consumed_at = ? "
            "WHERE channel = ? AND destination = ? AND purpose = ? "
            "  AND consumed_at IS NULL",
            (now.isoformat(), channel, destination, purpose),
        )

        code = _generate_code()
        expires_at = now + timedelta(seconds=ttl_seconds)
        con.execute(
            "INSERT INTO otp_codes("
            "  purpose, destination, channel, code_hash, "
            "  user_id_to_link, created_at, expires_at, attempts"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (
                purpose, destination, channel, _hash_code(code),
                user_id_to_link, now.isoformat(), expires_at.isoformat(),
            ),
        )
        con.commit()

    return code


def verify(
    *,
    channel: str,
    destination: str,
    code: str,
    purpose: str,
    max_attempts: int = MAX_ATTEMPTS,
) -> bool:
    """Проверить код. True если совпал (код consumed_at <- now).
    False если нет активного кода / неверный / уже consumed / превышен лимит.
    OTPExpired — отдельно, чтобы caller мог отличить "истёк" от "неверный".
    """
    now = _now()
    expected_hash = _hash_code(code)

    with connect() as con:
        row = con.execute(
            "SELECT id, code_hash, expires_at, attempts, consumed_at "
            "FROM otp_codes "
            "WHERE channel = ? AND destination = ? AND purpose = ? "
            "ORDER BY id DESC LIMIT 1",
            (channel, destination, purpose),
        ).fetchone()
        if row is None:
            return False
        if row["consumed_at"] is not None:
            return False
        if datetime.fromisoformat(row["expires_at"]) < now:
            raise OTPExpired()
        if row["attempts"] >= max_attempts:
            con.execute(
                "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            con.commit()
            return False
        if row["code_hash"] == expected_hash:
            con.execute(
                "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            con.commit()
            return True
        # неверный код — инкремент attempts и (если достиг порога) burn
        new_attempts = row["attempts"] + 1
        if new_attempts >= max_attempts:
            con.execute(
                "UPDATE otp_codes SET attempts = ?, consumed_at = ? WHERE id = ?",
                (new_attempts, now.isoformat(), row["id"]),
            )
        else:
            con.execute(
                "UPDATE otp_codes SET attempts = ? WHERE id = ?",
                (new_attempts, row["id"]),
            )
        con.commit()
        return False


def get_user_id_to_link(
    *,
    channel: str,
    destination: str,
    code: str,
    purpose: str,
) -> int | None:
    """Peek user_id_to_link если code валиден (не consume).
    None если no active / expired / consumed / wrong code / max attempts."""
    now = _now()
    expected_hash = _hash_code(code)

    with connect() as con:
        row = con.execute(
            "SELECT user_id_to_link, code_hash, expires_at, attempts, consumed_at "
            "FROM otp_codes "
            "WHERE channel = ? AND destination = ? AND purpose = ? "
            "ORDER BY id DESC LIMIT 1",
            (channel, destination, purpose),
        ).fetchone()
        if row is None or row["consumed_at"] is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < now:
            return None
        if row["attempts"] >= MAX_ATTEMPTS:
            return None
        if row["code_hash"] != expected_hash:
            return None
        return row["user_id_to_link"]
