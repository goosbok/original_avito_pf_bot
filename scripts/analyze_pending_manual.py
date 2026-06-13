"""Diagnostic: classify pending+manual order_links by expected target status.

Read-only. Computes, per the business rule:
  nominal_start = order.start_date OR (order.date date + 1 day) if NULL
  start_at_msk  = nominal_start at 04:00 МСК
  end_at_msk    = start_at_msk + days * 24h    (days from position_name "d/f")

  target =
    'done'    if now_msk >= end_at_msk
    'in_work' if start_at_msk <= now_msk < end_at_msk
    'pending' if now_msk < start_at_msk

Prints bucket counts + 5 sample rows per bucket. No DB mutation.

Usage:
    docker compose exec api python -m scripts.analyze_pending_manual
"""
from __future__ import annotations

import logging
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from services.db import connect

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))
_START_HOUR = 4  # биза стартует день клика в 04:00 МСК


def _parse_days(position_name: str | None) -> int | None:
    """'3/10' -> 3. None если не распарсилось."""
    if not position_name:
        return None
    try:
        return int(str(position_name).split("/")[0])
    except (ValueError, IndexError):
        return None


def _parse_any_date(s: str | None) -> date | None:
    """Парсит дату в двух форматах:
      - ISO 'YYYY-MM-DD' (опционально с временем 'YYYY-MM-DDTHH:MM:SS...')
      - Legacy 'DD.MM.YYYY' (опционально с временем 'DD.MM.YYYY HH:MM:SS')
    """
    if not s:
        return None
    s = str(s).strip()
    # ISO: YYYY-MM-DD...
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    # Legacy DD.MM.YYYY...
    parts = s[:10].split(".")
    if len(parts) == 3:
        try:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, TypeError):
            pass
    return None


def _nominal_start(order: dict) -> date | None:
    """order.start_date если задано, иначе дата создания + 1.

    Возвращает None если ни одно не парсится — такую ссылку считаем 'unknown'.
    """
    parsed_start = _parse_any_date(order.get("start_date"))
    if parsed_start is not None:
        return parsed_start

    parsed_creation = _parse_any_date(order.get("date"))
    if parsed_creation is not None:
        return parsed_creation + timedelta(days=1)
    return None


def _target_status(order: dict, now_msk: datetime) -> tuple[str, dict]:
    """Возвращает (target, debug_info).

    target ∈ {'done', 'in_work', 'pending', 'unknown'}.
    """
    days = _parse_days(order.get("position_name"))
    if days is None or days <= 0:
        return "unknown", {"reason": "bad position_name",
                            "position_name": order.get("position_name")}

    nominal_start = _nominal_start(order)
    if nominal_start is None:
        return "unknown", {"reason": "no date / start_date"}

    start_at = datetime(
        nominal_start.year, nominal_start.month, nominal_start.day,
        _START_HOUR, 0, tzinfo=_MSK,
    )
    end_at = start_at + timedelta(days=days)

    if now_msk >= end_at:
        target = "done"
    elif now_msk >= start_at:
        target = "in_work"
    else:
        target = "pending"

    return target, {
        "nominal_start": nominal_start.isoformat(),
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "days": days,
    }


def analyze() -> dict:
    """Run the analysis. Returns summary dict."""
    now_msk = datetime.now(timezone.utc).astimezone(_MSK)

    with connect() as con:
        rows = con.execute(
            "SELECT ol.id AS link_id, ol.order_id, ol.url, ol.created_at, "
            "       o.position_name, o.start_date, o.date, o.status AS order_status "
            "FROM order_links ol "
            "JOIN orders o ON o.increment = ol.order_id "
            "WHERE ol.status = 'pending' AND ol.delivery_mode = 'manual'"
        ).fetchall()

    print(f"Now (МСК): {now_msk.isoformat()}")
    print(f"Total pending+manual links: {len(rows)}\n")

    buckets: Counter[str] = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)
    by_order_status: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for r in rows:
        order = {
            "position_name": r["position_name"],
            "start_date": r["start_date"],
            "date": r["date"],
        }
        target, info = _target_status(order, now_msk)
        buckets[target] += 1
        by_order_status[r["order_status"]][target] += 1

        if len(samples[target]) < 5:
            samples[target].append({
                "link_id": int(r["link_id"]),
                "order_id": int(r["order_id"]),
                "position_name": r["position_name"],
                "start_date": r["start_date"],
                "date_created": r["date"],
                "order_status": r["order_status"],
                **info,
            })

    # Print summary
    print("=== Bucket counts ===")
    for status in ("done", "in_work", "pending", "unknown"):
        n = buckets.get(status, 0)
        print(f"  {status:>8}: {n}")
    print()

    print("=== By parent order.status ===")
    for ostatus, sub in sorted(by_order_status.items()):
        print(f"  order.status={ostatus!r}:")
        for s in ("done", "in_work", "pending", "unknown"):
            n = sub.get(s, 0)
            if n:
                print(f"    {s:>8}: {n}")
    print()

    print("=== Samples (up to 5 per bucket) ===")
    for status in ("done", "in_work", "pending", "unknown"):
        if not samples[status]:
            continue
        print(f"\n--- {status} ---")
        for s in samples[status]:
            print(f"  link={s['link_id']} order={s['order_id']} "
                  f"pos={s['position_name']} start_date={s['start_date']} "
                  f"created={s['date_created']} order_status={s['order_status']}")
            if "start_at" in s:
                print(f"    nominal_start={s['nominal_start']} "
                      f"start_at={s['start_at']} end_at={s['end_at']} "
                      f"days={s['days']}")
            else:
                print(f"    reason={s.get('reason')}")

    return {"total": len(rows), "buckets": dict(buckets)}


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    summary = analyze()
    print(f"\nDone. Total={summary['total']} buckets={summary['buckets']}")


if __name__ == "__main__":
    sys.exit(main())
