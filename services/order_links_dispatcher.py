"""Dispatcher: классифицирует pending-ссылки, пробует auto через API,
fallback'ит в manual.

Идемпотентно: повторный вызов не трогает уже не-pending ссылки.

Каждая ссылка обрабатывается независимо — ошибка на одной не валит
остальные. Только pending-ссылки, у которых delivery_mode=NULL ИЛИ auto
(retry-кейс), участвуют в dispatch'е; manual-ссылки уже ждут админа.
"""
from __future__ import annotations

import logging

from services.db import connect
from services.exceptions import ExecutorAPIError, ExecutorAPIRejected
from services.order_links import compute_deadline
from services.order_links_classifier import classify
from services.pf_executor_api import submit_link

logger = logging.getLogger(__name__)


def dispatch_pending_links(order_id: int) -> None:
    """Прогнать все pending-ссылки заказа через классификатор+API.

    Не возвращает результата — состояние ссылок видно через list_links.
    Ошибки на одной ссылке логируются, остальные продолжают обрабатываться.
    """
    with connect() as con:
        order = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order is None:
            logger.warning("dispatch_pending_links: order %s not found", order_id)
            return
        order_d = dict(order)
        rows = con.execute(
            "SELECT id, delivery_mode FROM order_links "
            "WHERE order_id=? AND status='pending'",
            (order_id,),
        ).fetchall()
        candidates = [(r["id"], r["delivery_mode"]) for r in rows]

    for link_id, current_mode in candidates:
        try:
            _dispatch_one(link_id, current_mode, order_d)
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "dispatch_pending_links: link %s failed", link_id
            )


def _dispatch_one(link_id: int, current_mode: str | None, order: dict) -> None:
    """Обработать одну pending-ссылку."""
    # Re-fetch url под текущее соединение (отдельная транзакция)
    with connect() as con:
        row = con.execute(
            "SELECT url FROM order_links WHERE id=? AND status='pending'",
            (link_id,),
        ).fetchone()
        if row is None:
            return  # already not pending — race, skip
        url = row["url"]

    # Если delivery_mode ещё не назначен — классифицируем.
    mode = current_mode or classify(url, order)

    if mode == "manual":
        # просто проставить delivery_mode и оставить pending
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='manual' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return

    # mode == 'auto' — пробуем API
    try:
        external_id = submit_link(url, order)
    except ExecutorAPIRejected:
        # Не возьмут — fallback в manual
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='manual' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return
    except ExecutorAPIError:
        # Временный сбой — оставляем pending+auto для retry
        with connect() as con:
            con.execute(
                "UPDATE order_links SET delivery_mode='auto' "
                "WHERE id=? AND status='pending'",
                (link_id,),
            )
            con.commit()
        return

    # API принял — в work
    from services.order_links import mark_in_work
    deadline = compute_deadline(order)
    mark_in_work(link_id, delivery_mode="auto",
                 deadline_at=deadline, external_id=external_id)
