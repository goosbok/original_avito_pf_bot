"""Send emails via SMTP. Configured via SMTP_* env vars (see web/config.py / .env)."""
from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr

from services.exceptions import EmailSendError

logger = logging.getLogger(__name__)


@contextmanager
def _ipv4_only_dns():
    """Filter socket.getaddrinfo to AF_INET only for the duration of this block.

    The api container disables IPv6 at the kernel level (`disable_ipv6=1` in
    docker-compose). With AF_UNSPEC the kernel refuses to handle AAAA results
    and getaddrinfo returns EAI_FAMILY (errno -9). Forcing AF_INET sidesteps
    the whole IPv6 codepath. Scoped via context manager so unrelated callers
    are unaffected.
    """
    real = socket.getaddrinfo

    def ipv4_only(host, port, family=0, *args, **kwargs):
        return real(host, port, socket.AF_INET, *args, **kwargs)

    socket.getaddrinfo = ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = real


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

    try:
        context = ssl.create_default_context()
        with _ipv4_only_dns():
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as s:
                    s.login(user, password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=20) as s:
                    s.starttls(context=context)
                    s.login(user, password)
                    s.send_message(msg)
    except Exception as exc:
        logger.exception("email send failed to %s", to)
        raise EmailSendError(f"email send failed: {exc}") from exc
