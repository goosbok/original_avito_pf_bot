"""Web routes отдают ссылки заказа из order_links, не из NULL колонки orders.links."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.db import connect
from services.order_links import create_links
from utils.dates import now_iso


def _seed_paid_order_with_links(tmp_db: Path, urls: list[str]) -> int:
    """Insert a user + paid order (orders.links=NULL) then seed order_links rows."""
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id, balance, user_name) "
            "VALUES (1, 0, 'tester')"
        )
        cur = con.execute(
            "INSERT INTO orders(user_id, price, position_name, status, date, "
            "contacts, user_name) "
            "VALUES (1, 100, '3/100', 'paid', ?, 0, 'tester')",
            (now_iso(),),
        )
        order_id = int(cur.lastrowid)
        con.commit()

    # Insert links via the service (uses connect() which hits tmp_db).
    with connect() as con:
        create_links(con, order_id=order_id, urls=urls)
        con.commit()

    return order_id


def test_get_order_detail_returns_links_from_order_links(tmp_db: Path):
    """orders.links=NULL but order_links has rows → _render_links_str returns joined URLs."""
    from web.routers.orders import _render_links_str

    order_id = _seed_paid_order_with_links(
        tmp_db, ["https://avito.ru/a", "https://avito.ru/b"]
    )
    result = _render_links_str(order_id)
    assert "https://avito.ru/a" in result
    assert "https://avito.ru/b" in result


def test_order_with_no_links_returns_empty_string(tmp_db: Path):
    """Order exists in order_links with zero rows → empty string (not crash)."""
    from web.routers.orders import _render_links_str

    order_id = _seed_paid_order_with_links(tmp_db, [])
    assert _render_links_str(order_id) == ""


def test_admin_orders_renders_links_from_order_links(tmp_db: Path):
    """admin_orders._render_links_str reads from order_links, not orders.links."""
    from web.routers.admin_orders import _render_links_str

    order_id = _seed_paid_order_with_links(tmp_db, ["https://avito.ru/admin"])
    result = _render_links_str(order_id)
    assert "https://avito.ru/admin" in result


def test_admin_users_renders_links_from_order_links(tmp_db: Path):
    """admin_users._render_links_str reads from order_links, not orders.links."""
    from web.routers.admin_users import _render_links_str

    order_id = _seed_paid_order_with_links(tmp_db, ["https://avito.ru/users"])
    result = _render_links_str(order_id)
    assert "https://avito.ru/users" in result


def test_multiple_links_joined_by_newline(tmp_db: Path):
    """Multiple URLs in order_links are joined with newline."""
    from web.routers.orders import _render_links_str

    order_id = _seed_paid_order_with_links(
        tmp_db, ["https://avito.ru/x", "https://avito.ru/y", "https://avito.ru/z"]
    )
    result = _render_links_str(order_id)
    parts = result.split("\n")
    assert len(parts) == 3
    assert parts[0] == "https://avito.ru/x"
    assert parts[1] == "https://avito.ru/y"
    assert parts[2] == "https://avito.ru/z"
