import asyncio
import sqlite3
from unittest.mock import patch

from services.auto_rate_metric import compute_recent_auto_rate
from utils.dates import now_iso


def _seed(tmp_db, modes):
    """modes: список ('auto'|'manual'|None,) — каждая попадёт как pending link."""
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/10', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        for mode in modes:
            con.execute(
                "INSERT INTO order_links(order_id, url, status, "
                "delivery_mode, created_at) "
                "VALUES (?, 'u', 'pending', ?, ?)",
                (order_id, mode, now_iso())
            )
        con.commit()


def test_auto_rate_empty(tmp_db):
    out = compute_recent_auto_rate(hours=1)
    assert out == {"auto": 0, "total": 0, "rate": 0.0}


def test_auto_rate_mixed(tmp_db):
    _seed(tmp_db, modes=["auto", "auto", "manual", None])
    out = compute_recent_auto_rate(hours=1)
    # None не считаем — это ещё-не-классифицированные.
    assert out["auto"] == 2
    assert out["total"] == 3
    assert out["rate"] == 2 / 3


def test_run_metric_loop_skips_when_feature_off(tmp_db, caplog):
    """When PF_AUTO_DISPATCH_ENABLED=False, loop skips compute and logs feature_off.

    Без этого скипа метрика бы каждый час показывала rate=0.0 во время
    rollout — выглядело бы как поломанный classifier, хотя по дизайну
    всё уходит в manual.
    """
    import logging
    from services.auto_rate_metric import run_metric_loop

    caplog.set_level(logging.INFO)
    compute_calls = 0

    def fake_compute(hours=1):
        nonlocal compute_calls
        compute_calls += 1
        return {"auto": 0, "total": 0, "rate": 0.0}

    async def runner():
        with patch("services.auto_rate_metric.config.PF_AUTO_DISPATCH_ENABLED",
                   False), \
             patch("services.auto_rate_metric.compute_recent_auto_rate",
                   side_effect=fake_compute), \
             patch("services.auto_rate_metric.asyncio.sleep",
                   side_effect=[None, asyncio.CancelledError]):
            try:
                await run_metric_loop()
            except asyncio.CancelledError:
                pass

    asyncio.run(runner())
    assert compute_calls == 0, "compute_recent_auto_rate should not run when feature off"
    assert any("metric.auto_rate.skip" in r.message and "feature_off" in r.message
               for r in caplog.records)
