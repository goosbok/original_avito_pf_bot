"""Send emails via SMTP. Configured via SMTP_* env vars (see web/config.py / .env)."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from services.exceptions import EmailSendError

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, *, html: bool = False) -> None:
    """Send a plain-text or HTML email. Raises EmailSendError on failure.

    Reads SMTP creds from env at call time so tests can monkeypatch.
    """
    import os

    host = os.getenv("SMTP_HOST", "smtp.yandex.ru")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_name = os.getenv("SMTP_FROM_NAME", "авито.пф")

    if not user or not password:
        raise EmailSendError("SMTP_USER or SMTP_PASSWORD not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    if html:
        msg.set_content("Этот email требует HTML-клиент.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    # The api container disables IPv6 (`disable_ipv6=1` in docker-compose), but
    # smtp.yandex.ru resolves to both A and AAAA records. Passing source_address
    # with an IPv4 placeholder forces socket.create_connection to skip AAAA entries
    # instead of failing with "Cannot assign requested address" (errno 99).
    source_address = ("0.0.0.0", 0)

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(
                host, port, context=context, timeout=20, source_address=source_address
            ) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20, source_address=source_address) as s:
                s.starttls(context=context)
                s.login(user, password)
                s.send_message(msg)
    except Exception as exc:
        logger.exception("email send failed to %s", to)
        raise EmailSendError(f"email send failed: {exc}") from exc
