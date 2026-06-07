"""Business logic для unpaid → paid flow заказов.

Жизненный цикл order.status:

    create_unpaid  ─►  unpaid
                        │
       ┌────────────────┼─────────────────────────────────┐
       ▼                ▼                                 ▼
  pay_with_balance  pay_with_yookassa                  expire-job
       │                │                                 │
       ▼                ▼ (webhook / status poll)         ▼
      paid           paid (mark_paid)              payment_failed

Дальше — terminal статусы: `done` (накрутка выполнена), `failed` (накрутка
не выполнена), `cancelled` (отменён до или после оплаты).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from services.db import connect
from services.exceptions import (
    InsufficientBalance,
    OrderNotFound,
    OrderStatusConflict,
    PaymentError,
    PaymentExpired,
    UserNotFound,
)
from services.order_links_dispatcher import dispatch_pending_links
from utils.sqlite3 import (
    get_price,
    user_orders_count,
    user_orders_paginated,
)

logger = logging.getLogger(__name__)


# TTL до истечения unpaid-заказа (в минутах).
# - NO_METHOD: юзер ещё не выбрал способ оплаты.
# - YOOKASSA: после выбора yookassa (короткий — payment redirect живёт ~10 мин).
# - BALANCE: после выбора balance (длинный — авторизация уже есть).
TTL_NO_METHOD_MINUTES = 60
TTL_YOOKASSA_MINUTES = 10
TTL_BALANCE_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def get_pf_price_per_unit() -> int:
    raw = get_price("price_avito_pf")
    return int(raw) if raw is not None else 1


def _price_for(links: list[str], days: int, fix_count: int) -> int:
    return get_pf_price_per_unit() * fix_count * days * len(links)


# === Новый flow ===


def create_unpaid(
    *,
    user_id: int,
    links: list[str],
    days: int,
    fix_count: int,
    contacts: bool,
    phone: str | None,
    start_date: str | None = None,
) -> int:
    """Создать заказ со status='unpaid'. payment_method/payment_id ещё NULL.

    payment_expires_at выставляется на TTL_NO_METHOD_MINUTES вперёд — если юзер
    не выберет способ за этот срок, expiry-job переведёт его в payment_failed.

    start_date — ISO дата "YYYY-MM-DD" когда юзер хочет начать накрутку.
    None → исполнитель начинает сразу после оплаты.

    Returns: order_id (== orders.increment).
    """
    from services.order_links import create_links as _create_order_links

    price = _price_for(links, days, fix_count)
    expires_at = (_now() + timedelta(minutes=TTL_NO_METHOD_MINUTES)).isoformat()
    with connect() as con:
        cur = con.execute(
            "INSERT INTO orders("
            "  user_id, price, position_name, status, links, contacts, "
            "  user_name, payment_method, payment_expires_at, payment_id, "
            "  phone, start_date, date"
            ") VALUES (?, ?, ?, 'unpaid', NULL, ?, NULL, NULL, ?, NULL, ?, ?, ?)",
            (
                user_id, price, f"{days}/{fix_count}",
                int(contacts),
                expires_at, phone, start_date, _now_iso(),
            ),
        )
        order_id = int(cur.lastrowid)
        _create_order_links(con, order_id=order_id, urls=list(links))
        con.commit()
        return order_id


def get_order(order_id: int) -> dict:
    """Прочитать order по id. Raises OrderNotFound."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
    if row is None:
        raise OrderNotFound(f"order_id={order_id}")
    return dict(row)


def _set_payment_method(
    con, *, order_id: int, method: str
) -> str:
    """Атомарно проставить payment_method и обновить payment_expires_at если order
    ещё в 'unpaid'. Возвращает новый expires_at ISO. Raises OrderStatusConflict
    если уже не unpaid."""
    ttl_min = TTL_YOOKASSA_MINUTES if method == "yookassa" else TTL_BALANCE_MINUTES
    expires_at = (_now() + timedelta(minutes=ttl_min)).isoformat()
    cur = con.execute(
        "UPDATE orders SET payment_method=?, payment_expires_at=? "
        "WHERE increment=? AND status='unpaid'",
        (method, expires_at, order_id),
    )
    if cur.rowcount == 0:
        raise OrderStatusConflict(f"order {order_id} не в unpaid")
    return expires_at


def _check_expires(order: dict) -> None:
    """Если payment_expires_at < now — raise PaymentExpired."""
    exp = order.get("payment_expires_at")
    if not exp:
        return
    if datetime.fromisoformat(exp) < _now():
        raise PaymentExpired(f"order {order.get('increment')} expired at {exp}")


def pay_with_balance(*, order_id: int, user_id: int) -> None:
    """Атомарно списать price с user.balance и перевести order в 'paid'.

    Raises:
        OrderNotFound — order не существует или принадлежит другому юзеру.
        OrderStatusConflict — order не в unpaid.
        InsufficientBalance — на балансе не хватает.
        PaymentExpired — TTL истёк (expiry-job ещё не пробежал).
    """
    with connect() as con:
        order = con.execute(
            "SELECT * FROM orders WHERE increment=? AND user_id=?",
            (order_id, user_id),
        ).fetchone()
        if order is None:
            raise OrderNotFound(f"order {order_id} for user {user_id}")
        if order["status"] != "unpaid":
            raise OrderStatusConflict(
                f"order {order_id} в статусе {order['status']}, не unpaid"
            )
        order_d = dict(order)
        _check_expires(order_d)

        bal_row = con.execute(
            "SELECT balance FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if bal_row is None:
            raise UserNotFound(f"user_id={user_id}")
        bal = int(bal_row["balance"] or 0)
        price = int(order["price"] or 0)
        if bal < price:
            raise InsufficientBalance(user_id=user_id, available=bal, required=price)

        _set_payment_method(con, order_id=order_id, method="balance")
        con.execute(
            "UPDATE users SET balance = balance - ? WHERE id=?",
            (price, user_id),
        )
        con.execute(
            "UPDATE orders SET status='paid' WHERE increment=? AND status='unpaid'",
            (order_id,),
        )
        con.commit()
    try:
        dispatch_pending_links(order_id)
    except Exception:  # noqa: BLE001 — best-effort; cron добьёт
        logger.exception("pay_with_balance: dispatch_pending_links failed for %s", order_id)


def pay_with_yookassa(*, order_id: int, return_url: str) -> tuple[str, str]:
    """Создать YooKassa Payment, проставить payment_method='yookassa' + payment_id.

    Order остаётся в 'unpaid'; в `paid` его переводит webhook / status-poll
    через `mark_paid`.

    Returns: (confirmation_url, payment_id).

    Raises:
        OrderNotFound, OrderStatusConflict, PaymentExpired, PaymentError.
    """
    with connect() as con:
        row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if row is None:
            raise OrderNotFound(f"order {order_id}")
        if row["status"] != "unpaid":
            raise OrderStatusConflict(
                f"order {order_id} в статусе {row['status']}, не unpaid"
            )
        order_d = dict(row)
        _check_expires(order_d)
        _set_payment_method(con, order_id=order_id, method="yookassa")
        con.commit()

    price = int(order_d["price"] or 0)
    try:
        from data.config import SECRET_KEY, SHOP_ID
        from yookassa import Configuration, Payment

        Configuration.account_id = SHOP_ID
        Configuration.secret_key = SECRET_KEY
        payment = Payment.create({
            "amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": f"Заказ #{order_id}",
            "metadata": {"order_id": str(order_id)},
        })
    except Exception as exc:
        raise PaymentError(str(exc)) from exc

    with connect() as con:
        con.execute(
            "UPDATE orders SET payment_id=? WHERE increment=?",
            (payment.id, order_id),
        )
        con.commit()

    return payment.confirmation.confirmation_url, payment.id


def mark_paid(order_id: int) -> None:
    """Идемпотентно перевести unpaid → paid. Используется YooKassa webhook'ом
    и status-pollers. Если статус уже не unpaid — no-op (двойной webhook
    не должен ломать систему). После перехода в paid запускается dispatcher
    ссылок."""
    with connect() as con:
        cur = con.execute(
            "UPDATE orders SET status='paid' WHERE increment=? AND status='unpaid'",
            (order_id,),
        )
        con.commit()
        changed = cur.rowcount > 0
    if changed:
        try:
            dispatch_pending_links(order_id)
        except Exception:  # noqa: BLE001 — best-effort; cron добьёт
            logger.exception("mark_paid: dispatch_pending_links failed for %s", order_id)


def mark_payment_failed(order_id: int) -> None:
    """Перевести unpaid → payment_failed (expiry или явный refusal).

    Best-effort: если у заказа есть payment_id (yookassa), пробуем `Payment.cancel`,
    чтобы юзеру не списало деньги. Ошибки cancel не валим — order уже в БД помечен.

    Если order не в unpaid — no-op (защита от гонок с webhook).
    """
    with connect() as con:
        row = con.execute(
            "SELECT payment_method, payment_id FROM orders "
            "WHERE increment=? AND status='unpaid'",
            (order_id,),
        ).fetchone()
        if row is None:
            return
        method, payment_id = row["payment_method"], row["payment_id"]
        con.execute(
            "UPDATE orders SET status='payment_failed' "
            "WHERE increment=? AND status='unpaid'",
            (order_id,),
        )
        con.commit()

    if method == "yookassa" and payment_id:
        try:
            from data.config import SECRET_KEY, SHOP_ID
            from yookassa import Configuration, Payment

            Configuration.account_id = SHOP_ID
            Configuration.secret_key = SECRET_KEY
            Payment.cancel(payment_id)
        except Exception:
            logger.warning(
                "yookassa Payment.cancel failed for order %s (best-effort, ignoring)",
                order_id,
            )


# === Запросы для UI ===


def list_orders(user_id: int, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    items = user_orders_paginated(user_id, limit=page_size, offset=offset)
    total = user_orders_count(user_id)
    return items, total
