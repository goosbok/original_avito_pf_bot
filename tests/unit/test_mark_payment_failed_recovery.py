"""Сверка в точке отказа: mark_payment_failed не должен валить заказ,
который YooKassa подтвердила как succeeded.

Корень бага: yookassa-платёж создаётся с capture=True. Если юзер оплатил,
но не вернулся на сайт (return-url / status-poll не сработали), деньги
списываются (succeeded), но заказ остаётся unpaid и через 10 мин expiry-loop
зовёт mark_payment_failed. Раньше это молча помечало оплаченный заказ как
payment_failed (а Payment.cancel на succeeded не срабатывал → деньги у нас,
услуга не оказана). Теперь mark_payment_failed сверяется с YooKassa и
восстанавливает такой заказ в paid.
"""
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch


def _yk(status: str):
    return SimpleNamespace(id="pid-1", status=status)


def _seed_unpaid_yookassa_order(tmp_db, n_links: int = 2, payment_id: str = "pid-1"):
    """unpaid-заказ с выбранным yookassa и payment_id (как после pay_with_yookassa)."""
    from services.orders import create_unpaid
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) VALUES ('price_avito_pf', '1')")
        con.commit()
    order_id = create_unpaid(
        user_id=1, links=[f"u{i}" for i in range(n_links)],
        days=3, fix_count=10, contacts=False, phone=None,
    )
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "UPDATE orders SET payment_method='yookassa', payment_id=? WHERE increment=?",
            (payment_id, order_id),
        )
        con.commit()
    return order_id


def _status(tmp_db, order_id):
    with sqlite3.connect(tmp_db) as con:
        return con.execute(
            "SELECT status FROM orders WHERE increment=?", (order_id,)
        ).fetchone()[0]


def test_recovers_to_paid_when_yk_succeeded(tmp_db):
    """YK=succeeded → заказ paid (не payment_failed) + ссылки диспатчатся."""
    from services.orders import mark_payment_failed
    order_id = _seed_unpaid_yookassa_order(tmp_db)
    with patch("yookassa.Payment.find_one", return_value=_yk("succeeded")), \
         patch("yookassa.Payment.cancel") as cancel, \
         patch("services.orders.dispatch_pending_links") as dispatch:
        mark_payment_failed(order_id)
    assert _status(tmp_db, order_id) == "paid"
    dispatch.assert_called_once_with(order_id)
    cancel.assert_not_called()  # succeeded платёж не отменяем


def test_marks_failed_and_cancels_when_yk_canceled(tmp_db):
    """YK=canceled → заказ payment_failed + best-effort Payment.cancel."""
    from services.orders import mark_payment_failed
    order_id = _seed_unpaid_yookassa_order(tmp_db)
    with patch("yookassa.Payment.find_one", return_value=_yk("canceled")), \
         patch("yookassa.Payment.cancel") as cancel, \
         patch("services.orders.dispatch_pending_links") as dispatch:
        mark_payment_failed(order_id)
    assert _status(tmp_db, order_id) == "payment_failed"
    dispatch.assert_not_called()
    cancel.assert_called_once()


def test_marks_failed_when_probe_errors(tmp_db):
    """YK API недоступна → безопасный дефолт: помечаем payment_failed."""
    from services.orders import mark_payment_failed
    order_id = _seed_unpaid_yookassa_order(tmp_db)
    with patch("yookassa.Payment.find_one", side_effect=RuntimeError("YK down")), \
         patch("yookassa.Payment.cancel"):
        mark_payment_failed(order_id)
    assert _status(tmp_db, order_id) == "payment_failed"


def test_balance_order_does_not_probe_yookassa(tmp_db):
    """Заказ без payment_id (balance) валим без обращения к YooKassa."""
    from services.orders import create_unpaid, mark_payment_failed
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.execute("INSERT INTO settings(parametr, value) VALUES ('price_avito_pf', '1')")
        con.commit()
    order_id = create_unpaid(user_id=1, links=["u0"], days=1, fix_count=1,
                             contacts=False, phone=None)
    with patch("yookassa.Payment.find_one") as find_one:
        mark_payment_failed(order_id)
    assert _status(tmp_db, order_id) == "payment_failed"
    find_one.assert_not_called()
