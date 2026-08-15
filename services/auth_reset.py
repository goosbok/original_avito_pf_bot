"""Password reset via OTP codes (channel='email', purpose='password_reset')."""
from __future__ import annotations

RESET_TTL_SECONDS = 600       # 10 minutes
RESET_COOLDOWN_SECONDS = 60


def forgot_password(email: str) -> None:
    """Issue OTP and send code. Always silent if email is unknown/invalid.

    Raises OTPCooldown if a code was issued < RESET_COOLDOWN_SECONDS ago
    (callers that want "always 200" should swallow it).
    """
    from services.auth_email import normalize_email
    from services.exceptions import InvalidCredentials

    try:
        email_norm = normalize_email(email)
    except InvalidCredentials:
        return

    from services import identity
    if identity.find_user_id_by_provider("email", email_norm) is None:
        return

    from services import otp
    code = otp.issue(
        channel="email",
        destination=email_norm,
        purpose="password_reset",
        ttl_seconds=RESET_TTL_SECONDS,
        cooldown_seconds=RESET_COOLDOWN_SECONDS,
    )

    from services.email_sender import send_email
    subject = "Сброс пароля"
    body = (
        f"Ваш код для сброса пароля: {code}\n\n"
        f"Код действителен {RESET_TTL_SECONDS // 60} минут.\n\n"
        f"Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
    )
    send_email(email_norm, subject, body)


def reset_password_by_otp(email: str, code: str, new_password: str) -> None:
    """Verify OTP code and set new password.

    Raises:
      - OTPInvalid: invalid email format, wrong code, no active code, or max attempts exceeded
      - OTPExpired: code TTL passed
      - ValueError: new_password too short (from hash_password)
    """
    from services.auth_email import normalize_email
    from services.exceptions import InvalidCredentials, OTPInvalid

    try:
        email_norm = normalize_email(email)
    except InvalidCredentials:
        raise OTPInvalid("Неверный код") from None

    from services import otp
    ok = otp.verify(
        channel="email",
        destination=email_norm,
        purpose="password_reset",
        code=code,
    )
    if not ok:
        raise OTPInvalid("Неверный код")

    from services.auth_password import hash_password
    new_hash = hash_password(new_password)

    from services.db import connect
    with connect() as con:
        cur = con.execute(
            "UPDATE auth_providers SET credential_hash = ? "
            "WHERE provider = 'email' AND identifier = ?",
            (new_hash, email_norm),
        )
        if cur.rowcount == 0:
            raise OTPInvalid("Неверный код")
        con.commit()
