"""Dispatcher: классифицирует pending-ссылки, пробует auto через API,
fallback'ит в manual.

Идемпотентно: повторный вызов не трогает уже не-pending ссылки.

Каждая ссылка обрабатывается независимо — ошибка на одной не валит
остальные. Только pending-ссылки, у которых delivery_mode=NULL ИЛИ auto
(retry-кейс), участвуют в dispatch'е; manual-ссылки уже ждут админа.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from data import config
from services.avito_phrase_cache import lookup as cache_lookup
from services.avito_url import extract_ad_id
from services.circuit_breaker import CircuitBreaker
from services.db import connect
from services.exceptions import (
    ExecutorAPIError,
    ExecutorAPIRejected,
    InvalidLinkTransition,
    OrderNotFound,
)
from services.order_links import compute_deadline
from services.order_links_classifier import classify
from services.pf_executor_api import submit_link

logger = logging.getLogger(__name__)

_breaker = CircuitBreaker(
    config.BIZA_BREAKER_ERRORS, config.BIZA_COOLDOWN_MIN * 60
)


def _bump_attempts_or_manual(link_id: int) -> None:
    """+1 к dispatch_attempts; при достижении BIZA_MAX_ATTEMPTS → manual."""
    with connect() as con:
        row = con.execute(
            "SELECT dispatch_attempts FROM order_links "
            "WHERE id=? AND status='pending'",
            (link_id,),
        ).fetchone()
        if row is None:
            return  # уже не pending — гонка
        attempts = (row["dispatch_attempts"] or 0) + 1
        mode = "manual" if attempts >= config.BIZA_MAX_ATTEMPTS else "auto"
        con.execute(
            "UPDATE order_links SET dispatch_attempts=?, delivery_mode=? "
            "WHERE id=? AND status='pending'",
            (attempts, mode, link_id),
        )
        con.commit()


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
            "SELECT id FROM order_links "
            "WHERE order_id=? AND status='pending' "
            "AND (delivery_mode IS NULL OR delivery_mode='auto')",
            (order_id,),
        ).fetchall()
        candidates = [r["id"] for r in rows]

    for link_id in candidates:
        try:
            _dispatch_one(link_id, order_d)
        except Exception:  # noqa: BLE001 — best-effort на партию
            logger.exception(
                "dispatch_pending_links: link %s failed", link_id
            )


def _dispatch_one(link_id: int, order: dict) -> None:
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

    # Классифицируем ссылку. Даже если delivery_mode уже 'auto' (retry-кейс
    # после ExecutorAPIError), переклассификация идемпотентна — фразу
    # cache_lookup вернёт ту же.
    mode, phrase = classify(url, order, link_id=link_id)

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
    # Contract: classifier гарантирует phrase != None когда mode='auto'.
    # Если контракт нарушится — лучше упасть здесь, чем POST'ить None в
    # search_link.
    if not phrase:
        raise RuntimeError(
            f"classifier returned mode='auto' without phrase "
            f"(link_id={link_id})"
        )
    try:
        external_id = submit_link(url, order, search_phrase=phrase)
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
        # Временный сбой biza (429/500/сеть). Считаем попытку: после
        # BIZA_MAX_ATTEMPTS уводим ссылку в manual, иначе оставляем pending+auto.
        _breaker.record_error()
        _bump_attempts_or_manual(link_id)
        return

    # API принял — в work
    _breaker.record_success()
    from services.order_links import mark_in_work
    deadline = compute_deadline(order)
    mark_in_work(link_id, delivery_mode="auto",
                 deadline_at=deadline, external_id=external_id)


DISPATCHER_LOOP_INTERVAL_SECONDS = 5 * 60  # 5 минут


def dispatch_for_paid_orders() -> int:
    """Найти все paid-заказы с pending-ссылками и прогнать dispatcher.

    Используется cron'ом — добивает заказы, чей dispatch при оплате упал
    или прошёл частично (например, API временно не доступен).
    Возвращает количество обработанных заказов.
    """
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT o.increment "
            "FROM orders o JOIN order_links ol ON ol.order_id = o.increment "
            "WHERE o.status='paid' AND ol.status='pending'"
        ).fetchall()
    order_ids = [int(r["increment"]) for r in rows]
    for order_id in order_ids:
        try:
            dispatch_pending_links(order_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "dispatch_for_paid_orders: order %s failed", order_id
            )
    return len(order_ids)


async def run_dispatcher_loop() -> None:
    logger.info(
        "dispatcher loop started (interval=%ss)",
        DISPATCHER_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            count = dispatch_for_paid_orders()
            if count:
                logger.info("dispatcher: handled %d orders", count)
        except Exception:  # noqa: BLE001
            logger.exception("dispatcher loop iteration failed")
        await asyncio.sleep(DISPATCHER_LOOP_INTERVAL_SECONDS)


@dataclass
class LinkPreview:
    """Per-link классификация для admin Test auto preview."""
    link_id: int
    url: str
    ad_id: str | None
    decision: str       # 'auto' | 'manual'
    reason: str         # 'cache_hit' | 'cache_miss' | 'no_ad_id'
    phrase: str | None
    deadline_at: str | None


def classify_for_preview(order_id: int) -> list[LinkPreview]:
    """Dry-run классификация всех pending-ссылок заказа.

    Не трогает БД, не шлёт HTTP. Игнорирует PF_AUTO_DISPATCH_ENABLED
    (всегда смотрит в кэш). Используется admin Test auto handler'ом
    для preview перед confirm.

    Note: дублирует ad_id/cache lookup из classify() осознанно — нам
    нужно surface'ить reason code и ad_id наружу, что текущий
    classify(url, order) -> (mode, phrase) контракт не даёт. Refactor
    classify() под (mode, phrase, reason) тут не делаем — затронет
    штатный dispatcher и набор тестов. Сделаем отдельной задачей.

    Raises OrderNotFound если order_id не существует.
    """
    with connect() as con:
        order_row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order_row is None:
            raise OrderNotFound(f"order_id={order_id}")
        order = dict(order_row)

        rows = con.execute(
            "SELECT id, url FROM order_links "
            "WHERE order_id=? AND status='pending' ORDER BY id",
            (order_id,),
        ).fetchall()
        link_rows = [(int(r["id"]), r["url"]) for r in rows]

    # Deadline тот же для всех auto-ссылок заказа — считаем один раз lazily.
    deadline_cached: str | None = None
    previews: list[LinkPreview] = []
    for link_id, url in link_rows:
        ad_id = extract_ad_id(url)
        if ad_id is None:
            previews.append(LinkPreview(
                link_id=link_id, url=url, ad_id=None,
                decision="manual", reason="no_ad_id",
                phrase=None, deadline_at=None,
            ))
            logger.info(
                "classifier.preview link=%s ad=%s decision=manual reason=no_ad_id",
                link_id, "none",
            )
            continue

        phrase = cache_lookup(ad_id)
        if not phrase:
            previews.append(LinkPreview(
                link_id=link_id, url=url, ad_id=ad_id,
                decision="manual", reason="cache_miss",
                phrase=None, deadline_at=None,
            ))
            logger.info(
                "classifier.preview link=%s ad=%s decision=manual reason=cache_miss",
                link_id, ad_id,
            )
            continue

        if deadline_cached is None:
            deadline_cached = compute_deadline(order)
        deadline = deadline_cached
        previews.append(LinkPreview(
            link_id=link_id, url=url, ad_id=ad_id,
            decision="auto", reason="cache_hit",
            phrase=phrase, deadline_at=deadline,
        ))
        logger.info(
            "classifier.preview link=%s ad=%s decision=auto reason=cache_hit",
            link_id, ad_id,
        )

    return previews


@dataclass
class DispatchResult:
    """Per-link результат admin Test auto-dispatch."""
    link_id: int
    success: bool
    external_id: str | None
    error: str | None   # human-readable, для admin message


def force_dispatch(
    order_id: int, link_ids: list[int]
) -> list[DispatchResult]:
    """Реальный dispatch выбранного subset'а pending-ссылок заказа.

    Использует штатные classify(force=True) → submit_link → mark_in_work.
    Игнорирует PF_AUTO_DISPATCH_ENABLED только в classifier-gate;
    submit_link и transaction guarantees — без изменений.

    Ошибки на отдельных ссылках не валят остальные. На Rejected/Error
    ссылка остаётся pending (не flip'аем в manual — Test auto это
    диагностика, не штатный flow).

    Raises OrderNotFound если order_id не существует.
    """
    if not link_ids:
        return []

    with connect() as con:
        order_row = con.execute(
            "SELECT * FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
        if order_row is None:
            raise OrderNotFound(f"order_id={order_id}")
        order = dict(order_row)

        placeholders = ",".join("?" for _ in link_ids)
        rows = con.execute(
            f"SELECT id, url, status FROM order_links "
            f"WHERE order_id=? AND id IN ({placeholders})",
            (order_id, *link_ids),
        ).fetchall()
        link_rows = [(int(r["id"]), r["url"], r["status"]) for r in rows]

    # Deadline тот же для всех auto-ссылок заказа — считаем один раз lazily.
    deadline_cached: str | None = None
    results: list[DispatchResult] = []

    for link_id, url, status in link_rows:
        if status != "pending":
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"уже не pending (текущий статус: {status})",
            ))
            continue

        mode, phrase = classify(url, order, link_id=link_id, force=True)
        if mode != "auto" or phrase is None:
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error="classifier теперь manual (кэш изменился)",
            ))
            continue

        try:
            external_id = submit_link(url, order, search_phrase=phrase)
        except ExecutorAPIRejected as exc:
            logger.warning("force_dispatch.rejected link=%s err=%s",
                           link_id, exc)
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"API отказал: {exc}",
            ))
            continue
        except ExecutorAPIError as exc:
            logger.warning("force_dispatch.api_error link=%s err=%s",
                           link_id, exc)
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=None,
                error=f"API временная ошибка: {exc}",
            ))
            continue

        if deadline_cached is None:
            deadline_cached = compute_deadline(order)
        from services.order_links import mark_in_work
        try:
            mark_in_work(link_id, delivery_mode="auto",
                         deadline_at=deadline_cached, external_id=external_id)
        except InvalidLinkTransition as exc:
            # Race: штатный dispatcher успел забрать ссылку между нашими
            # SELECT и UPDATE. submit_link уже создал задачу в API — у
            # исполнителя получится дубль. Логируем warning (это
            # ожидаемый race, не баг), результат — success=False с явной
            # причиной.
            logger.warning(
                "force_dispatch.race link=%s external_id=%s err=%s",
                link_id, external_id, exc,
            )
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=external_id,
                error=(
                    f"гонка с штатным dispatcher'ом: ссылка уже не "
                    f"pending (external_id={external_id} создан у "
                    f"исполнителя, дубликат у них)"
                ),
            ))
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "force_dispatch.mark_in_work_failed link=%s", link_id,
            )
            results.append(DispatchResult(
                link_id=link_id, success=False, external_id=external_id,
                error=f"submit прошёл, но mark_in_work упал: {exc}",
            ))
            continue

        results.append(DispatchResult(
            link_id=link_id, success=True, external_id=external_id,
            error=None,
        ))

    return results
