"""Email registration / login flow."""
from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from services import identity
from services.auth_password import hash_password, verify_password
from services.exceptions import InvalidCredentials


def normalize_email(email: str) -> str:
    """Валидирует и нормализует email. Бросает InvalidCredentials при неверном формате."""
    try:
        v = validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidCredentials(f"invalid email: {exc}") from exc
    return v.normalized.lower()


def register(email: str, password: str, first_name: str | None = None) -> int:
    """Зарегистрировать нового юзера. Возвращает user_id."""
    email_norm = normalize_email(email)
    cred = hash_password(password)
    return identity.get_or_create_user_by_email(
        email_norm, credential_hash=cred, first_name=first_name
    )


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
