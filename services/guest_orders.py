"""Guest order service — DB ops and YooKassa payment creation."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from services.db import connect
from services.exceptions import PaymentError


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")


def create_guest_order(
    phone: str,
    links: list[str],
    days: int,
    fix_count: int,
    contacts: bool,
    price: int,
    price_per_unit: int,
) -> int:
    """Insert a pending_payment guest order, return its id."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO guest_orders"
            "(phone, links, days, fix_count, contacts, price, price_per_unit, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_payment', ?)",
            (
                phone,
                json.dumps(links),
                days,
                fix_count,
                int(contacts),
                price,
                price_per_unit,
                _now(),
            ),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def get_guest_order(guest_order_id: int) -> dict | None:
    """Return the guest_orders row as dict, or None if not found."""
    with connect() as con:
        return con.execute(
            "SELECT * FROM guest_orders WHERE id = ?", (guest_order_id,)
        ).fetchone()


def set_payment_id(guest_order_id: int, payment_id: str) -> None:
    """Store the YooKassa payment_id on the order."""
    with connect() as con:
        con.execute(
            "UPDATE guest_orders SET payment_id = ? WHERE id = ?",
            (payment_id, guest_order_id),
        )
        con.commit()


def update_status(guest_order_id: int, status: str) -> None:
    """Set status to 'paid' or 'failed'."""
    with connect() as con:
        con.execute(
            "UPDATE guest_orders SET status = ? WHERE id = ?",
            (status, guest_order_id),
        )
        con.commit()


def create_payment(guest_order_id: int, amount: int, phone: str) -> tuple[str, str]:
    """Create a YooKassa payment. Returns (payment_url, payment_id).

    Raises PaymentError if the YooKassa call fails.
    """
    from data.config import SHOP_ID, SECRET_KEY, SITE_URL
    from yookassa import Configuration, Payment

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    return_url = f"{SITE_URL}/?guest_order_id={guest_order_id}"

    try:
        payment = Payment.create(
            {
                "amount": {"value": f"{amount}.00", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": return_url},
                "capture": True,
                "description": f"Авито ПФ (гостевой заказ #{guest_order_id})",
                "receipt": {
                    "phone": phone,
                    "items": [
                        {
                            "description": f"Авито ПФ #{guest_order_id}",
                            "quantity": 1,
                            "amount": {"value": f"{amount}.00", "currency": "RUB"},
                            "vat_code": 1,
                            "payment_mode": "full_prepayment",
                            "payment_subject": "service",
                        }
                    ],
                    "tax_system_code": 1,
                },
            },
            str(uuid.uuid4()),
        )
        data = json.loads(payment.json())
        return data["confirmation"]["confirmation_url"], data["id"]
    except Exception as exc:
        raise PaymentError(f"yookassa create failed: {exc}") from exc
