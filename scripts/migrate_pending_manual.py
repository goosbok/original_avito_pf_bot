"""One-shot migration: legacy pending+manual order_links → правильный статус.

Алгоритм (тот же что в analyze_pending_manual.py):
  nominal_start = order.start_date OR (order.date date) + 1 day
  start_at_msk  = nominal_start @ 04:00 МСК
  end_at_msk    = start_at_msk + days * 24h    (days из position_name)

  target_status:
    now_msk >= end_at_msk          → 'done'    (UPDATE: done_at=now, started_at=COALESCE(started_at, start_at))
    start_at_msk <= now_msk < end_at_msk → 'in_work' (UPDATE: started_at=start_at, deadline_at=end_at)
    now_msk < start_at_msk         → не трогаем (новые сегодняшние заказы)

Минует state-machine (`_ALLOWED_TRANSITIONS` не пускает pending→done напрямую).
После всех link-апдейтов вручную пересчитывает orders.status тем же
алгоритмом что `services.order_links._recompute_order_status` — БЕЗ
`notify_order_status_changed` (по требованию: юзеры не узнают).

Usage:
    # Dry-run — печатает что БЫЛО БЫ сделано:
    docker compose exec api python -m scripts.migrate_pending_manual

    # Реальная миграция (backup создаётся автоматически):
    docker compose exec api python -m scripts.migrate_pending_manual --commit
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from data import config
from services.db import connect

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_START_HOUR = 4

# Сколько ссылок в одной транзакции при UPDATE. Баланс между скоростью и
# атомарностью (если упадём по сети — потеряем максимум этот батч).
_BATCH_SIZE = 500


# === Date parsing (same as analyze_pending_manual.py) ===

def _parse_any_date(s: str | None) -> date | None:
    """Парсит ISO 'YYYY-MM-DD...' или legacy 'DD.MM.YYYY...'."""
    if not s:
        return None
    s = str(s).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    parts = s[:10].split(".")
    if len(parts) == 3:
        try:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, TypeError):
            pass
    return None


def _parse_days(position_name: str | None) -> int | None:
    if not position_name:
        return None
    try:
        return int(str(position_name).split("/")[0])
    except (ValueError, IndexError):
        return None


def _nominal_start(order: dict) -> date | None:
    parsed = _parse_any_date(order.get("start_date"))
    if parsed is not None:
        return parsed
    parsed = _parse_any_date(order.get("date"))
    if parsed is not None:
        return parsed + timedelta(days=1)
    return None


def _classify(
    order: dict, now_msk: datetime
) -> tuple[str | None, datetime | None, datetime | None]:
    """Возвращает (target_status, start_at, end_at).

    target_status in {'done', 'in_work', 'pending', None}.
    None — bad data (нечем классифицировать, пропускаем).
    """
    days = _parse_days(order.get("position_name"))
    if days is None or days <= 0:
        return None, None, None
    nominal_start = _nominal_start(order)
    if nominal_start is None:
        return None, None, None
    start_at = datetime(
        nominal_start.year, nominal_start.month, nominal_start.day,
        _START_HOUR, 0, tzinfo=_MSK,
    )
    end_at = start_at + timedelta(days=days)
    if now_msk >= end_at:
        return "done", start_at, end_at
    if now_msk >= start_at:
        return "in_work", start_at, end_at
    return "pending", start_at, end_at


# === DB ops ===

def _backup_db() -> Path:
    src = Path(config.path_database)
    if not src.exists():
        raise FileNotFoundError(f"DB not found: {src}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(f"{src.name}.bak-{ts}")
    shutil.copy2(src, dst)
    logger.info("DB backup: %s → %s", src, dst)
    return dst


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_link_updates(
    plan_by_status: dict[str, list[tuple]],
    commit: bool,
) -> dict[str, int]:
    """plan_by_status: {'done': [(link_id, start_at_iso, end_at_iso, now_iso)],
                        'in_work': [(link_id, start_at_iso, end_at_iso)]}

    Применяет апдейты батчами. commit=False → ничего не делает,
    только считает rowcount'ы (для dry-run возвращаем len(plan)).
    """
    if not commit:
        return {k: len(v) for k, v in plan_by_status.items()}

    affected = {"done": 0, "in_work": 0}

    done_items = plan_by_status.get("done", [])
    for i in range(0, len(done_items), _BATCH_SIZE):
        chunk = done_items[i:i + _BATCH_SIZE]
        with connect() as con:
            for link_id, start_at, _end_at, now_iso in chunk:
                cur = con.execute(
                    "UPDATE order_links "
                    "SET status='done', done_at=?, "
                    "    started_at=COALESCE(started_at, ?) "
                    "WHERE id=? AND status='pending' AND delivery_mode='manual'",
                    (now_iso, start_at, link_id),
                )
                affected["done"] += cur.rowcount
            con.commit()
        logger.info("done: batch %d-%d / %d done",
                     i + 1, min(i + _BATCH_SIZE, len(done_items)),
                     len(done_items))

    in_work_items = plan_by_status.get("in_work", [])
    for i in range(0, len(in_work_items), _BATCH_SIZE):
        chunk = in_work_items[i:i + _BATCH_SIZE]
        with connect() as con:
            for link_id, start_at, end_at, _now in chunk:
                cur = con.execute(
                    "UPDATE order_links "
                    "SET status='in_work', "
                    "    started_at=?, deadline_at=? "
                    "WHERE id=? AND status='pending' AND delivery_mode='manual'",
                    (start_at, end_at, link_id),
                )
                affected["in_work"] += cur.rowcount
            con.commit()
        logger.info("in_work: batch %d-%d / %d done",
                     i + 1, min(i + _BATCH_SIZE, len(in_work_items)),
                     len(in_work_items))
    return affected


_AGGREGATABLE = frozenset({"paid"})


def _recompute_orders(
    order_ids: list[int],
    commit: bool,
    overrides: dict[int, str] | None = None,
) -> dict[str, int]:
    """Пересчитать orders.status для каждого order_id согласно правилу
    `services.order_links._recompute_order_status`. БЕЗ notify.

    Логика:
      counts(link.status):
        pending + in_work > 0  → status остаётся 'paid'
        failed > 0             → 'failed'
        иначе                  → 'done'
      Guard: orders.status ∉ {'paid'} — не трогаем.

    `overrides` (опц.): {link_id: new_status} — для dry-run симуляции
    post-update состояния. Если задан и commit=False, считаем counts
    применяя overrides к текущим link.status (in-memory).

    Возвращает счётчик transitions {'paid->done': N, 'paid->failed': N, ...}.
    """
    transitions: Counter[str] = Counter()
    overrides = overrides or {}
    for order_id in order_ids:
        with connect() as con:
            row = con.execute(
                "SELECT status FROM orders WHERE increment=?",
                (order_id,),
            ).fetchone()
            if row is None:
                transitions["order_not_found"] += 1
                continue
            old = row["status"]
            if old not in _AGGREGATABLE:
                transitions["guard"] += 1
                continue

            link_rows = con.execute(
                "SELECT id, status FROM order_links WHERE order_id=?",
                (order_id,),
            ).fetchall()
            counts: Counter[str] = Counter()
            for lr in link_rows:
                lid = int(lr["id"])
                status = overrides.get(lid, lr["status"])
                counts[status] += 1

            if not counts:
                transitions["no_links"] += 1
                continue
            if counts.get("pending", 0) + counts.get("in_work", 0) > 0:
                transitions["noop_still_in_flight"] += 1
                continue
            if counts.get("failed", 0) > 0:
                new = "failed"
            else:
                new = "done"
            if new == old:
                transitions["noop_same"] += 1
                continue
            if commit:
                con.execute(
                    "UPDATE orders SET status=? "
                    "WHERE increment=? AND status=?",
                    (new, order_id, old),
                )
                con.commit()
            transitions[f"{old}->{new}"] += 1
    return dict(transitions)


# === Main ===

def run(commit: bool) -> None:
    now_msk = datetime.now(timezone.utc).astimezone(_MSK)
    now_iso_str = _now_iso()
    print(f"Now (МСК): {now_msk.isoformat()}")
    print(f"Mode: {'COMMIT (real update)' if commit else 'DRY-RUN (no writes)'}\n")

    with connect() as con:
        rows = con.execute(
            "SELECT ol.id AS link_id, ol.order_id, ol.url, "
            "       o.position_name, o.start_date, o.date "
            "FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.status = 'pending' AND ol.delivery_mode = 'manual'"
        ).fetchall()

    print(f"Total pending+manual links: {len(rows)}\n")

    plan_by_status: dict[str, list[tuple]] = defaultdict(list)
    affected_order_ids: set[int] = set()
    skipped: Counter[str] = Counter()

    for r in rows:
        order_dict = {
            "position_name": r["position_name"],
            "start_date": r["start_date"],
            "date": r["date"],
        }
        target, start_at, end_at = _classify(order_dict, now_msk)
        if target is None:
            skipped["bad_data"] += 1
            continue
        if target == "pending":
            skipped["already_pending_correct"] += 1
            continue
        plan_by_status[target].append((
            int(r["link_id"]),
            start_at.isoformat() if start_at else None,
            end_at.isoformat() if end_at else None,
            now_iso_str,
        ))
        affected_order_ids.add(int(r["order_id"]))

    print("=== Plan ===")
    print(f"  → done    : {len(plan_by_status.get('done', []))}")
    print(f"  → in_work : {len(plan_by_status.get('in_work', []))}")
    print(f"  skipped (pending — оставляем): "
           f"{skipped.get('already_pending_correct', 0)}")
    print(f"  skipped (bad data): {skipped.get('bad_data', 0)}")
    print(f"  Unique orders to recompute: {len(affected_order_ids)}")
    print()

    if commit:
        backup = _backup_db()
        print(f"Backup created: {backup}\n")

    print("=== Applying link updates ===")
    applied = _apply_link_updates(plan_by_status, commit=commit)
    print(f"  done     UPDATEs applied : {applied.get('done', 0)}")
    print(f"  in_work  UPDATEs applied : {applied.get('in_work', 0)}")
    print()

    # Для dry-run строим карту link_id → new_status (симулируем post-update
    # state), чтобы recompute показал реальный прогноз.
    overrides: dict[int, str] = {}
    if not commit:
        for status_key, items in plan_by_status.items():
            for link_id, *_ in items:
                overrides[link_id] = status_key

    print("=== Recomputing orders.status (no notify) ===")
    transitions = _recompute_orders(
        list(affected_order_ids), commit=commit, overrides=overrides,
    )
    for k, v in sorted(transitions.items()):
        print(f"  {k}: {v}")
    print()

    if not commit:
        print("Dry-run complete. Re-run with --commit to actually apply.")
    else:
        print("✅ Migration complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually apply UPDATEs. Without this — dry-run (default).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    run(commit=args.commit)


if __name__ == "__main__":
    sys.exit(main())
