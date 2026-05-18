"""Password reset via secure URL tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

RESET_TOKEN_TTL_HOURS = 1


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def forgot_password(email: str) -> None:
    """Generate reset token and send link. Always silent if email is unknown or invalid."""
    from services.auth_email import normalize_email
    from services.exceptions import InvalidCredentials

    try:
        email_norm = normalize_email(email)
    except InvalidCredentials:
        return

    from services import identity

    if identity.find_user_id_by_provider("email", email_norm) is None:
        return

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=RESET_TOKEN_TTL_HOURS)

    from services.db import connect

    with connect() as con:
        con.execute("DELETE FROM password_reset_tokens WHERE email = ?", (email_norm,))
        con.execute(
            "INSERT INTO password_reset_tokens(token_hash, email, expires_at, created_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, email_norm, expires_at.isoformat(), now.isoformat()),
        )
        con.commit()

    from data import config as bot_config

    site_url = getattr(bot_config, "SITE_URL", "")
    reset_url = f"{site_url}/reset-password?token={raw_token}"

    from services.email_sender import send_email

    subject = "ProBoost — сброс пароля"
    body = (
        f"Для сброса пароля перейдите по ссылке:\n{reset_url}\n\n"
        f"Ссылка действительна {RESET_TOKEN_TTL_HOURS} час.\n\n"
        f"Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
    )
    send_email(email_norm, subject, body)


def reset_password(raw_token: str, new_password: str) -> None:
    """Validate token, update credential_hash, mark token used.

    Raises:
      - ValueError: token not found, expired, or already used
      - ValueError: new_password too short (from hash_password)
    """
    from services.auth_password import hash_password

    new_hash = hash_password(new_password)

    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    from services.db import connect

    with connect() as con:
        row = con.execute(
            "SELECT email, expires_at, used_at FROM password_reset_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()

        if row is None:
            raise ValueError("invalid or expired token")
        if row["used_at"] is not None:
            raise ValueError("token already used")

        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            raise ValueError("invalid or expired token")

        email = row["email"]

        con.execute(
            "UPDATE auth_providers SET credential_hash = ? "
            "WHERE provider = 'email' AND identifier = ?",
            (new_hash, email),
        )
        con.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
            (now.isoformat(), token_hash),
        )
        con.commit()
