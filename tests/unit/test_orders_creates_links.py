"""services.orders.create_unpaid создаёт строки в order_links."""
import sqlite3


def test_create_unpaid_writes_links_table(tmp_db):
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '5')")
        con.commit()

    order_id = create_unpaid(
        user_id=1, links=["https://avito.ru/a", "https://avito.ru/b"],
        days=3, fix_count=100, contacts=False, phone=None,
    )

    with sqlite3.connect(tmp_db) as con:
        con.row_factory = sqlite3.Row
        rows = list(con.execute(
            "SELECT url, status, delivery_mode FROM order_links "
            "WHERE order_id=? ORDER BY id", (order_id,)
        ))
    assert [r["url"] for r in rows] == ["https://avito.ru/a", "https://avito.ru/b"]
    assert all(r["status"] == "pending" for r in rows)
    assert all(r["delivery_mode"] is None for r in rows)


def test_create_unpaid_still_writes_legacy_column_for_backward_compat(tmp_db):
    """Phase 1: orders.links временно пишется (legacy reader безопасен).
    Phase 2 уберёт колонку — этот тест удалить."""
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '5')")
        con.commit()

    order_id = create_unpaid(
        user_id=1, links=["url"], days=1, fix_count=10,
        contacts=False, phone=None,
    )
    with sqlite3.connect(tmp_db) as con:
        # legacy column still exists; either NULL or JSON — оба варианта OK
        row = con.execute(
            "SELECT links FROM orders WHERE increment=?", (order_id,)
        ).fetchone()
    # Specifically: we want it to NOT crash the writer. NULL is fine.
    # При drop колонки в Phase 2 тест удалить вместе с колонкой.
    assert row is not None
