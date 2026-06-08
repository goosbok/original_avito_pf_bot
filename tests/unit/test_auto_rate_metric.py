import sqlite3

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
