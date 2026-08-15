"""После оплаты заказа dispatcher отрабатывает на его ссылках."""
import sqlite3
from unittest.mock import patch


def _seed_unpaid_order_with_links(tmp_db, n=2):
    """Создать unpaid-заказ + N ссылок через services.orders.create_unpaid."""
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 10000)")
        con.execute("INSERT INTO settings(parametr, value) "
                    "VALUES ('price_avito_pf', '1')")
        con.commit()
    order_id = create_unpaid(
        user_id=1, links=[f"url{i}" for i in range(n)],
        days=3, fix_count=10, contacts=False, phone=None,
    )
    return order_id


def test_mark_paid_runs_dispatcher(tmp_db):
    """mark_paid должен дёрнуть dispatch_pending_links."""
    from services.orders import mark_paid

    order_id = _seed_unpaid_order_with_links(tmp_db, n=2)
    with patch("services.orders.dispatch_pending_links") as mock:
        mark_paid(order_id)
    mock.assert_called_once_with(order_id)


def test_pay_with_balance_runs_dispatcher(tmp_db):
    from services.orders import pay_with_balance
    order_id = _seed_unpaid_order_with_links(tmp_db, n=1)
    with patch("services.orders.dispatch_pending_links") as mock:
        pay_with_balance(order_id=order_id, user_id=1)
    mock.assert_called_once_with(order_id)


def test_mark_paid_idempotent_no_double_dispatch_on_already_paid(tmp_db):
    """Второй mark_paid (на уже paid) не должен вызывать dispatcher повторно."""
    from services.orders import mark_paid
    order_id = _seed_unpaid_order_with_links(tmp_db, n=1)
    mark_paid(order_id)  # 1: unpaid → paid
    with patch("services.orders.dispatch_pending_links") as mock:
        mark_paid(order_id)  # 2: no-op
    mock.assert_not_called()
