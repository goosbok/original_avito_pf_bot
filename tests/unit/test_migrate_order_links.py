"""Backfill legacy orders.links → order_links."""
import sqlite3

from utils.dates import now_iso


def _seed_legacy_order(tmp_db, *, status, links_text):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT OR IGNORE INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date) "
            "VALUES (1, 100, '3/100', ?, ?, ?)",
            (status, links_text, now_iso()),
        )
        con.commit()
        return int(cur.lastrowid)


def test_parse_links_text_json_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text('["a", "b"]') == ["a", "b"]


def test_parse_links_text_repr_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("['a', 'b']") == ["a", "b"]


def test_parse_links_text_csv_format():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("a, b, c") == ["a", "b", "c"]


def test_parse_links_text_whitespace_split():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("a\nb\nc") == ["a", "b", "c"]


def test_parse_links_text_empty_returns_empty_list():
    from scripts.migrate_order_links import parse_links_text
    assert parse_links_text("") == []
    assert parse_links_text(None) == []


def test_backfill_done_order_creates_done_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="done", links_text='["a", "b"]')
    n = backfill()
    assert n == 1  # обработан 1 заказ
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, done_at FROM order_links WHERE order_id=? ORDER BY id",
            (order_id,)
        ))
    assert [r["url"] for r in rows] == ["a", "b"]
    assert all(r["status"] == "done" for r in rows)
    assert all(r["done_at"] for r in rows)


def test_backfill_paid_creates_pending(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="paid", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert s == "pending"


def test_backfill_failed_creates_failed_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="failed", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT status, failure_reason FROM order_links WHERE order_id=?",
            (order_id,)
        ).fetchone()
    assert row["status"] == "failed"
    assert "legacy" in row["failure_reason"].lower()


def test_backfill_cancelled_creates_failed_links(tmp_db):
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="cancelled", links_text='["a"]')
    backfill()
    with sqlite3.connect(tmp_db) as con:
        s = con.execute(
            "SELECT status FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert s == "failed"


def test_backfill_idempotent(tmp_db):
    """Повторный запуск не дублирует строки."""
    from scripts.migrate_order_links import backfill
    order_id = _seed_legacy_order(tmp_db, status="done", links_text='["a"]')
    backfill()
    backfill()
    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 1


def test_backfill_skips_orders_with_null_links(tmp_db):
    """Если orders.links NULL (новый flow) — пропускаем."""
    from scripts.migrate_order_links import backfill
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, links, date) "
            "VALUES (1, 100, '3/100', 'paid', NULL, ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    backfill()
    with sqlite3.connect(tmp_db) as con:
        cnt = con.execute(
            "SELECT COUNT(*) FROM order_links WHERE order_id=?", (order_id,)
        ).fetchone()[0]
    assert cnt == 0
