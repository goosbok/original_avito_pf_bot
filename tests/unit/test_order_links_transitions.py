"""Матрица переходов состояний order_links."""
import sqlite3
import pytest

from services.db import connect
from services.exceptions import InvalidLinkTransition, LinkNotFound
from services.order_links import create_links, list_links
from utils.dates import now_iso


def _seed_link(tmp_db, status="pending"):
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date) "
            "VALUES (1, 100, '3/100', 'paid', ?)", (now_iso(),)
        )
        order_id = int(cur.lastrowid)
        con.commit()
    with connect() as con:
        create_links(con, order_id=order_id, urls=["u"])
        con.commit()
    link_id = list_links(order_id)[0]["id"]
    if status != "pending":
        with sqlite3.connect(tmp_db) as con:
            con.execute("UPDATE order_links SET status=? WHERE id=?",
                        (status, link_id))
            con.commit()
    return order_id, link_id


@pytest.mark.parametrize("from_status,to_status", [
    ("pending", "in_work"),
    ("pending", "failed"),
    ("in_work", "done"),
    ("in_work", "failed"),
])
def test_allowed_transitions(tmp_db, from_status, to_status):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=from_status)
    with connect() as con:
        _transition(con, link_id=link_id, to_status=to_status)
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        new_status = con.execute(
            "SELECT status FROM order_links WHERE id=?", (link_id,)
        ).fetchone()[0]
    assert new_status == to_status


@pytest.mark.parametrize("from_status,to_status", [
    ("pending", "done"),         # должен пройти через in_work
    ("in_work", "pending"),       # обратно нельзя
    ("done", "in_work"),          # terminal
    ("done", "failed"),
    ("failed", "in_work"),
    ("failed", "done"),
])
def test_forbidden_transitions(tmp_db, from_status, to_status):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=from_status)
    with connect() as con, pytest.raises(InvalidLinkTransition):
        _transition(con, link_id=link_id, to_status=to_status)


@pytest.mark.parametrize("status", ["pending", "in_work", "done", "failed"])
def test_noop_transition_to_same_status(tmp_db, status):
    """Повторный вызов в текущий статус — no-op, не падает."""
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status=status)
    with connect() as con:
        _transition(con, link_id=link_id, to_status=status)  # no exception
        con.commit()


def test_transition_writes_timestamp(tmp_db):
    """started_at заполняется при pending→in_work."""
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="pending")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="in_work",
                    delivery_mode="auto", deadline_at="2026-06-30T00:00:00+00:00")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row["started_at"] is not None
    assert row["delivery_mode"] == "auto"
    assert row["deadline_at"] == "2026-06-30T00:00:00+00:00"


def test_transition_done_writes_done_at(tmp_db):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="in_work")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="done")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        done_at = con.execute(
            "SELECT done_at FROM order_links WHERE id=?", (link_id,)
        ).fetchone()[0]
    assert done_at is not None


def test_transition_failed_writes_reason(tmp_db):
    from services.order_links import _transition
    _, link_id = _seed_link(tmp_db, status="in_work")
    with connect() as con:
        _transition(con, link_id=link_id, to_status="failed",
                    failure_reason="API timeout")
        con.commit()
    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM order_links WHERE id=?",
                          (link_id,)).fetchone()
    assert row["failed_at"] is not None
    assert row["failure_reason"] == "API timeout"


def test_transition_unknown_link_raises(tmp_db):
    from services.order_links import _transition
    with connect() as con, pytest.raises(LinkNotFound):
        _transition(con, link_id=99999, to_status="in_work")
