"""Email registration / login flow."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email

from services import identity
from services.auth_password import hash_password, verify_password
from services.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OTPCooldown,
    OTPExpired,
    OTPInvalid,
)

CODE_TTL_MINUTES = 10
CODE_RESEND_COOLDOWN_SECONDS = 60


def normalize_email(email: str) -> str:
    """Валидирует и нормализует email. Бросает InvalidCredentials при неверном формате."""
    try:
        v = validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidCredentials(f"invalid email: {exc}") from exc
    return v.normalized.lower()


def _generate_code() -> str:
    """6-digit numeric code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def register(email: str, password: str, first_name: str | None = None) -> int:
    """Зарегистрировать нового юзера. Возвращает user_id.

    Legacy: immediate registration without email verification.
    Сохраняется ради обратной совместимости (старые тесты + старый /register endpoint).
    """
    email_norm = normalize_email(email)
    cred = hash_password(password)
    return identity.get_or_create_user_by_email(
        email_norm, credential_hash=cred, first_name=first_name
    )


def register_request(email: str, password: str, first_name: str | None = None) -> None:
    """Step 1 of email registration. Validates, stores pending row, sends code via email.

    Raises:
      - InvalidCredentials: invalid email
      - EmailAlreadyRegistered: email уже принадлежит реальному юзеру
      - OTPCooldown: предыдущий код запрошен < CODE_RESEND_COOLDOWN_SECONDS назад
      - EmailSendError: SMTP send failed
      - ValueError: пароль слишком короткий (поднимается hash_password / выше по стеку)
    """
    email_norm = normalize_email(email)

    # Already a real user?
    if identity.find_user_id_by_provider("email", email_norm) is not None:
        raise EmailAlreadyRegistered(f"email already registered: {email_norm}")

    cred = hash_password(password)

    from services.db import connect

    now = datetime.now(timezone.utc)
    with connect() as con:
        # Cooldown check
        row = con.execute(
            "SELECT created_at FROM pending_email_registrations WHERE email = ?",
            (email_norm,),
        ).fetchone()
        if row is not None:
            try:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                elapsed = (now - created).total_seconds()
                if elapsed < CODE_RESEND_COOLDOWN_SECONDS:
                    raise OTPCooldown(int(CODE_RESEND_COOLDOWN_SECONDS - elapsed))
            except (ValueError, KeyError):
                # malformed timestamp — overwrite below
                pass

        code = _generate_code()
        expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)

        con.execute(
            "INSERT INTO pending_email_registrations"
            "(email, password_hash, first_name, code, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET "
            "password_hash = excluded.password_hash, "
            "first_name = excluded.first_name, "
            "code = excluded.code, "
            "expires_at = excluded.expires_at, "
            "created_at = excluded.created_at",
            (email_norm, cred, first_name, code, expires_at.isoformat(), now.isoformat()),
        )
        con.commit()

    # Send email outside the DB transaction.
    from services.email_sender import send_email

    subject = "ProBoost — код подтверждения"
    body = (
        f"Ваш код подтверждения регистрации: {code}\n\n"
        f"Код действителен {CODE_TTL_MINUTES} минут.\n\n"
        f"Если вы не запрашивали регистрацию, просто проигнорируйте это письмо."
    )
    send_email(email_norm, subject, body)


def register_verify(email: str, code: str) -> int:
    """Step 2: verify code, create user, return user_id. Удаляет pending-строку.

    Raises:
      - OTPExpired: код истёк
      - OTPInvalid: неверный код или нет pending-строки
    """
    email_norm = normalize_email(email)

    from services.db import connect

    now = datetime.now(timezone.utc)
    with connect() as con:
        row = con.execute(
            "SELECT password_hash, first_name, code, expires_at "
            "FROM pending_email_registrations WHERE email = ?",
            (email_norm,),
        ).fetchone()
        if row is None:
            raise OTPInvalid("Запросите код заново")
        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            raise OTPExpired("Код истёк, запросите новый")
        if str(row["code"]) != str(code).strip():
            raise OTPInvalid("Неверный код")

        password_hash = row["password_hash"]
        first_name = row["first_name"]

        # Cleanup
        con.execute(
            "DELETE FROM pending_email_registrations WHERE email = ?",
            (email_norm,),
        )
        con.commit()

    # Create the user outside the connection (identity opens its own).
    user_id = identity.get_or_create_user_by_email(
        email_norm,
        credential_hash=password_hash,
        first_name=first_name,
    )
    return user_id


def login(email: str, password: str) -> int:
    """Проверить email/пароль. Возвращает user_id или бросает InvalidCredentials."""
    email_norm = normalize_email(email)
    user_id = identity.find_user_id_by_provider("email", email_norm)
    if user_id is None:
        raise InvalidCredentials("email not registered")

    from services.db import connect
    with connect() as con:
        row = con.execute(
            "SELECT credential_hash FROM auth_providers "
            "WHERE provider = 'email' AND identifier = ?",
            (email_norm,),
        ).fetchone()
    if row is None or not verify_password(password, row["credential_hash"] or ""):
        raise InvalidCredentials("wrong password")

    identity.touch_provider("email", email_norm)
    return user_id
