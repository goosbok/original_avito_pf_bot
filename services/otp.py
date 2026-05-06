"""OTP-коды для Telegram-логина и привязки.

Поток:
- request(purpose, telegram_id, user_id_to_link=None) → код (6 цифр), bot снаружи отправляет в Telegram.
- verify(purpose, telegram_id, code) → True/False.

Хранение: code не в открытом виде, а sha256(code+pepper). Pepper — это JWT_SECRET (есть в env).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.db import connect
from services.exceptions import OTPCooldown, OTPExpired, OTPInvalid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    """Хешируем с пеппером, чтобы дамп БД не выдал коды."""
    from data import config
    pepper = getattr(config, "JWT_SECRET", "") or ""
    return hashlib.sha256((code + pepper).encode()).hexdigest()


def _generate_code() -> str:
    """6-значный numeric code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def request_code(
    purpose: str,
    telegram_id: int,
    *,
    user_id_to_link: Optional[int] = None,
    ttl_seconds: int = 300,
    cooldown_seconds: int = 60,
) -> str:
    """Сгенерировать новый код. Если недавно был запрос — OTPCooldown.

    Возвращает plaintext-код. Caller должен отправить его юзеру (через бот).
    """
    if purpose not in ("login", "link"):
        raise ValueError(f"unknown purpose: {purpose}")

    now = _now()
    with connect() as con:
        recent = con.execute(
            "SELECT created_at FROM otp_codes "
            "WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (purpose, telegram_id),
        ).fetchone()
        if recent:
            recent_at = datetime.fromisoformat(recent["created_at"])
            elapsed = (now - recent_at).total_seconds()
            if elapsed < cooldown_seconds:
                raise OTPCooldown(int(cooldown_seconds - elapsed))

        # Инвалидируем все предыдущие unused коды этой цели
        con.execute(
            "UPDATE otp_codes SET consumed_at = ? "
            "WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL",
            (now.isoformat(), purpose, telegram_id),
        )

        code = _generate_code()
        expires = now + timedelta(seconds=ttl_seconds)
        con.execute(
            "INSERT INTO otp_codes(purpose, telegram_id, code_hash, user_id_to_link, "
            "created_at, expires_at, attempts) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (purpose, telegram_id, _hash_code(code), user_id_to_link,
             now.isoformat(), expires.isoformat()),
        )
        con.commit()

    return code


def verify_code(
    purpose: str,
    telegram_id: int,
    code: str,
    *,
    max_attempts: int = 5,
) -> Optional[int]:
    """Проверить код. Возвращает user_id_to_link если purpose='link', иначе None.

    Бросает OTPInvalid / OTPExpired.
    """
    now = _now()
    code_hash = _hash_code(code)

    with connect() as con:
        row = con.execute(
            "SELECT id, code_hash, user_id_to_link, expires_at, attempts "
            "FROM otp_codes WHERE purpose = ? AND telegram_id = ? AND consumed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (purpose, telegram_id),
        ).fetchone()

        if row is None:
            raise OTPInvalid("no active code")

        if datetime.fromisoformat(row["expires_at"]) < now:
            raise OTPExpired()

        if row["attempts"] >= max_attempts:
            con.execute(
                "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            con.commit()
            raise OTPInvalid("max attempts exceeded")

        if row["code_hash"] != code_hash:
            con.execute(
                "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?",
                (row["id"],),
            )
            con.commit()
            raise OTPInvalid("wrong code")

        # Успех: помечаем consumed
        con.execute(
            "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
            (now.isoformat(), row["id"]),
        )
        con.commit()
        return row["user_id_to_link"]
