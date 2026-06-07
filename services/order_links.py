"""Владелец таблицы order_links.

Единственная точка мутации со встроенной валидацией переходов и пересчётом
orders.status (Спек §4.1). Все методы работают как через явный `con`
(участвуя в транзакции caller'а), так и через свой connect().
"""
from __future__ import annotations

import logging

from services.db import connect
from services.exceptions import InvalidLinkTransition, LinkNotFound
from utils.dates import now_iso

logger = logging.getLogger(__name__)


# === CRUD ===

def create_links(con, *, order_id: int, urls: list[str]) -> None:
    """Создать pending-ссылки заказа. Работает в переданной транзакции."""
    created = now_iso()
    for url in urls:
        con.execute(
            "INSERT INTO order_links(order_id, url, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (order_id, url, created),
        )


def list_links(order_id: int) -> list[dict]:
    """Все ссылки заказа, упорядочены по id (порядок создания)."""
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM order_links WHERE order_id=? ORDER BY id",
            (order_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_link(link_id: int) -> dict:
    """Прочитать одну ссылку. Raises LinkNotFound."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM order_links WHERE id=?", (link_id,)
        ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    return dict(row)


# === State transitions ===

# Допустимые переходы статусов ссылки. Спек §3.2.
_ALLOWED_TRANSITIONS = {
    ("pending", "in_work"),
    ("pending", "failed"),
    ("in_work", "done"),
    ("in_work", "failed"),
}


def _transition(
    con,
    *,
    link_id: int,
    to_status: str,
    delivery_mode: str | None = None,
    deadline_at: str | None = None,
    external_id: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Атомарно перевести ссылку в новый статус.

    Валидирует допустимость через `_ALLOWED_TRANSITIONS`. Повтор в текущий
    статус — no-op (идемпотентность). Проставляет соответствующий timestamp
    (started_at / done_at / failed_at).

    Не делает commit и не пересчитывает order.status — это ответственность
    публичных методов поверх (`mark_in_work` / `mark_done` / `mark_failed`).

    Caller MUST own an open transaction (BEGIN active). The status check
    is enforced at the SQL level via `WHERE status = ?` to be safe against
    races, but the function only commits when caller commits.
    """
    row = con.execute(
        "SELECT status FROM order_links WHERE id=?", (link_id,)
    ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    current = row["status"] if hasattr(row, "keys") else row[0]

    if current == to_status:
        return  # idempotent no-op

    if (current, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidLinkTransition(from_status=current, to_status=to_status)

    now = now_iso()
    fields = ["status = ?"]
    values: list = [to_status]

    if to_status == "in_work":
        fields.append("started_at = ?")
        values.append(now)
        if delivery_mode is not None:
            fields.append("delivery_mode = ?")
            values.append(delivery_mode)
        if deadline_at is not None:
            fields.append("deadline_at = ?")
            values.append(deadline_at)
        if external_id is not None:
            fields.append("external_id = ?")
            values.append(external_id)
    elif to_status == "done":
        fields.append("done_at = ?")
        values.append(now)
    elif to_status == "failed":
        fields.append("failed_at = ?")
        values.append(now)
        if failure_reason is not None:
            fields.append("failure_reason = ?")
            values.append(failure_reason)

    values.append(link_id)
    values.append(current)
    cur = con.execute(
        f"UPDATE order_links SET {', '.join(fields)} "
        f"WHERE id = ? AND status = ?",
        values,
    )
    if cur.rowcount == 0:
        # Race lost — link's status changed between our SELECT and UPDATE.
        # Raise InvalidLinkTransition to signal the caller to retry/abort.
        raise InvalidLinkTransition(
            from_status=current, to_status=to_status
        )


# === Aggregation ===

# Какие orders.status можно менять через агрегацию ссылок.
# Спец §4.1 guard: unpaid/payment_failed/cancelled не трогаем.
_AGGREGATABLE_ORDER_STATUSES = frozenset({"paid"})


def _recompute_order_status(con, order_id: int) -> tuple[str, str] | None:
    """Пересчитать orders.status по строкам order_links.

    Правило (Спец §4.1):
        pending + in_work > 0 → paid (без изменений)
        ≥1 failed → failed
        иначе → done

    Guard: если orders.status ∉ {paid} — не трогаем (защита от перехода
    в done из неоплаченного заказа).

    Не делает commit. Возвращает (old, new) если статус сменился,
    иначе None — caller должен сам шлёт notify_order_status_changed.
    """
    row = con.execute(
        "SELECT status FROM orders WHERE increment=?", (order_id,)
    ).fetchone()
    if row is None:
        return None
    old_status = row["status"] if hasattr(row, "keys") else row[0]
    if old_status not in _AGGREGATABLE_ORDER_STATUSES:
        return None

    counts_rows = con.execute(
        "SELECT status, COUNT(*) AS c FROM order_links "
        "WHERE order_id=? GROUP BY status",
        (order_id,),
    ).fetchall()
    counts = {r["status"] if hasattr(r, "keys") else r[0]:
              r["c"] if hasattr(r, "keys") else r[1]
              for r in counts_rows}

    if not counts:
        return None  # no links yet
    if counts.get("pending", 0) + counts.get("in_work", 0) > 0:
        return None  # still in flight
    if counts.get("failed", 0) > 0:
        new_status = "failed"
    else:
        new_status = "done"

    if new_status == old_status:
        return None

    con.execute(
        "UPDATE orders SET status=? WHERE increment=? AND status=?",
        (new_status, order_id, old_status),
    )
    return (old_status, new_status)


# === Public mutation API ===


def _get_order_id(con, link_id: int) -> int:
    row = con.execute(
        "SELECT order_id FROM order_links WHERE id=?", (link_id,)
    ).fetchone()
    if row is None:
        raise LinkNotFound(f"link_id={link_id}")
    return int(row["order_id"])


def mark_in_work(
    link_id: int,
    *,
    delivery_mode: str,
    deadline_at: str,
    external_id: str | None = None,
) -> tuple[str, str] | None:
    """pending → in_work. Пересчитывает order.status в той же транзакции.
    Возвращает (old, new) если статус заказа сменился, иначе None.
    Caller отвечает за дёрнуть notify_order_status_changed при не-None возврате."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(
            con, link_id=link_id, to_status="in_work",
            delivery_mode=delivery_mode, deadline_at=deadline_at,
            external_id=external_id,
        )
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result


def mark_done(link_id: int) -> tuple[str, str] | None:
    """in_work → done. Пересчитывает order.status в той же транзакции.
    Возвращает (old, new) если статус заказа сменился, иначе None.
    Caller отвечает за дёрнуть notify_order_status_changed при не-None возврате."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(con, link_id=link_id, to_status="done")
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result


def mark_failed(link_id: int, *, reason: str) -> tuple[str, str] | None:
    """pending | in_work → failed. Пересчитывает order.status в той же транзакции.
    Возвращает (old, new) если статус заказа сменился, иначе None.
    Caller отвечает за дёрнуть notify_order_status_changed при не-None возврате."""
    with connect() as con:
        order_id = _get_order_id(con, link_id)
        _transition(con, link_id=link_id, to_status="failed",
                    failure_reason=reason)
        result = _recompute_order_status(con, order_id)
        con.commit()
        return result
