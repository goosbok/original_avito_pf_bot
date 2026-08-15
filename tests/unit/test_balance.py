import sqlite3
import threading
from pathlib import Path

import pytest

from services.balance import credit, debit, get_balance
from services.exceptions import InsufficientBalance, UserNotFound


def _make_user(tmp_db: Path, user_id: int = 1, balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, "u", "U", balance, "2026-05-02"),
        )
        con.commit()


def test_get_balance_returns_balance(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=100)
    assert get_balance(1) == 100


def test_get_balance_unknown_user_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        get_balance(999)


def test_credit_increments_and_returns_new_balance(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    new_balance = credit(1, 50)
    assert new_balance == 60
    assert get_balance(1) == 60


def test_credit_negative_amount_raises(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    with pytest.raises(ValueError):
        credit(1, -5)


def test_credit_zero_is_noop(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    assert credit(1, 0) == 10


def test_debit_decrements(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=100)
    new_balance = debit(1, 30)
    assert new_balance == 70


def test_debit_below_zero_raises(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    with pytest.raises(InsufficientBalance) as exc_info:
        debit(1, 50)
    assert exc_info.value.available == 10
    assert exc_info.value.required == 50
    assert get_balance(1) == 10


def test_credit_concurrent_threads_sum_correctly(tmp_db: Path) -> None:
    """50 потоков по +1 руб должны дать +50, а не меньше из-за гонок."""
    _make_user(tmp_db, balance=0)

    def _credit_one() -> None:
        credit(1, 1)

    threads = [threading.Thread(target=_credit_one) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert get_balance(1) == 50
