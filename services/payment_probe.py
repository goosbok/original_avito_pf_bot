"""YooKassa health probe.

Runs probe_yookassa() (sync) on a schedule and fires an admin alert on failure.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from data.config import SHOP_ID, SECRET_KEY
from yookassa import Configuration, Payment

_log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    ok: bool
    error_msg: str | None = None
    latency_ms: float = 0.0


def is_yookassa_enabled() -> bool:
    """Return True if yookassa is configured and enabled in payment methods."""
    from services.payment_methods import is_enabled
    return bool(SHOP_ID and SECRET_KEY and is_enabled("yookassa"))


def probe_yookassa() -> ProbeResult:
    """Create a 1 RUB payment (capture=False) and cancel it immediately.

    Returns ProbeResult.ok=True if both API calls succeed.
    Does not charge anyone — capture=False is a hold-only authorization.
    """
    if not SHOP_ID or not SECRET_KEY:
        return ProbeResult(ok=False, error_msg="SHOP_ID or SECRET_KEY not configured")

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    t0 = time.monotonic()
    payment_id: str | None = None

    try:
        payment = Payment.create(
            {
                "amount": {"value": "1.00", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": "https://example.com"},
                "capture": False,
                "description": "[monitoring probe — не является реальным платежом]",
                "metadata": {"probe": "true"},
            },
            str(uuid.uuid4()),
        )
        payment_id = payment.id
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return ProbeResult(
            ok=False,
            error_msg=f"create failed: {type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )

    try:
        Payment.cancel(payment_id)
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return ProbeResult(
            ok=False,
            error_msg=f"cancel failed: {type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )

    return ProbeResult(ok=True, latency_ms=(time.monotonic() - t0) * 1000)


async def probe_and_alert() -> None:
    """Run the probe and send an admin alert if it fails. Never raises."""
    if not is_yookassa_enabled():
        _log.debug("payment probe: yookassa disabled or not configured, skipping")
        return

    result = probe_yookassa()

    if result.ok:
        _log.info("payment probe: OK (%.0f ms)", result.latency_ms)
        return

    _log.error("payment probe: FAILED — %s (%.0f ms)", result.error_msg, result.latency_ms)

    try:
        from utils.sender import send_admins
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_admins(
            f"🚨 <b>Платёжка не работает!</b>\n\n"
            f"YooKassa не принял тестовый платёж.\n\n"
            f"<b>Ошибка:</b> <code>{(result.error_msg or '')[:400]}</code>\n"
            f"<b>Задержка:</b> {result.latency_ms:.0f} мс\n"
            f"<b>Время:</b> {ts}"
        )
    except Exception as send_exc:
        _log.warning("payment probe: send_admins failed: %s", send_exc)
