"""credit_referral_balance / withdraw_to_main_balance / get_summary.referral_balance."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from services.exceptions import NothingToWithdraw, UserNotFound, WithdrawConflict


def _mk_user(tmp_db: Path, user_id: int, balance: int = 0, referral_balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, balance, referral_balance) VALUES (?, ?, ?)",
            (user_id, balance, referral_balance),
        )
        con.commit()


def test_credit_referral_balance_increments_and_returns_new_value(tmp_db: Path) -> None:
    from services.referral import credit_referral_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=0)
    assert credit_referral_balance(1, 100) == 100
    assert credit_referral_balance(1, 50) == 150
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT balance FROM users WHERE id = 1").fetchone()
    assert row[0] == 0  # основной баланс не тронут


def test_credit_referral_balance_raises_for_unknown_user(tmp_db: Path) -> None:
    """Реферер удалён/смёржен — credit_referral_balance должна деградировать так же,
    как services.balance.credit(), а не падать с TypeError."""
    from services.referral import credit_referral_balance
    with pytest.raises(UserNotFound):
        credit_referral_balance(999, 100)


def test_credit_referral_balance_rejects_negative_amount(tmp_db: Path) -> None:
    """Мёртвая копия услуги services.balance.credit(): amount < 0 — программная
    ошибка вызывающего, ValueError, а не тихая порча referral_balance."""
    from services.referral import credit_referral_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=10)
    with pytest.raises(ValueError):
        credit_referral_balance(1, -1)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT referral_balance FROM users WHERE id = 1"
        ).fetchone()
    assert row[0] == 10  # ничего не поменялось


def test_credit_referral_balance_zero_amount_is_noop(tmp_db: Path) -> None:
    """amount == 0 — короткое замыкание без записи в БД (как credit()), но
    UserNotFound для несуществующего юзера всё равно должен срабатывать."""
    from services.referral import credit_referral_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=10)
    assert credit_referral_balance(1, 0) == 10
    with pytest.raises(UserNotFound):
        credit_referral_balance(999, 0)


def test_withdraw_to_main_balance_moves_full_amount(tmp_db: Path) -> None:
    from services.referral import withdraw_to_main_balance
    _mk_user(tmp_db, 1, balance=500, referral_balance=250)
    withdrawn, new_main_balance = withdraw_to_main_balance(1)
    assert withdrawn == 250
    assert new_main_balance == 750
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT referral_balance, balance FROM users WHERE id = 1"
        ).fetchone()
    assert row == (0, 750)


def test_withdraw_to_main_balance_records_ledger_row(tmp_db: Path) -> None:
    from services.referral import withdraw_to_main_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=100)
    withdraw_to_main_balance(1)
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT user_id, amount, destination FROM referral_withdrawals"
        ).fetchone()
    assert row == (1, 100, "main_balance")


def test_withdraw_to_main_balance_raises_on_concurrent_change(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Гонка: referral_balance меняется (например второй бонус зачислился)
    между внутренним SELECT и guarded UPDATE withdraw_to_main_balance.

    Не полагаемся на реальный тайминг потоков (флаки) — детерминированно
    подсовываем гонку через обёртку над соединением: как только код внутри
    withdraw_to_main_balance выполняет SELECT referral_balance, отдельное
    sqlite3-соединение (эмулирующее конкурентного писателя) тут же меняет
    referral_balance в БД и коммитит. Оптимистическая блокировка
    (WHERE referral_balance = <прочитанное>) в guarded UPDATE не найдёт
    строку и должна бросить WithdrawConflict, а не тихо потерять сумму.
    """
    import services.referral as referral_module

    _mk_user(tmp_db, 1, balance=0, referral_balance=100)
    real_connect = referral_module.connect

    class _RacyConn:
        """Прозрачная обёртка над реальным sqlite3.Connection: перехватывает
        только конкретный SELECT, всё остальное форвардит без изменений."""

        def __init__(self, real_con: sqlite3.Connection) -> None:
            self._con = real_con

        def execute(self, sql: str, params: tuple = ()):
            cur = self._con.execute(sql, params)
            if "SELECT referral_balance FROM users" in sql:
                # Конкурентный писатель меняет referral_balance ПОСЛЕ нашего
                # SELECT, но ДО нашего guarded UPDATE — отдельное соединение,
                # чтобы не мешать транзакции withdraw_to_main_balance.
                with sqlite3.connect(tmp_db) as race_con:
                    race_con.execute(
                        "UPDATE users SET referral_balance = 999 WHERE id = ?",
                        params,
                    )
                    race_con.commit()
            return cur

        def commit(self) -> None:
            self._con.commit()

    @contextmanager
    def patched_connect():
        with real_connect() as con:
            yield _RacyConn(con)

    monkeypatch.setattr(referral_module, "connect", patched_connect)

    with pytest.raises(WithdrawConflict):
        referral_module.withdraw_to_main_balance(1)

    # Инвариант: конфликт должен остановить перенос — деньги не задвоились
    # и не потерялись, ledger-строка не создана.
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT referral_balance, balance FROM users WHERE id = 1"
        ).fetchone()
        ledger_count = con.execute(
            "SELECT COUNT(*) FROM referral_withdrawals"
        ).fetchone()[0]
    assert row == (999, 0)
    assert ledger_count == 0


def test_withdraw_to_main_balance_raises_when_zero(tmp_db: Path) -> None:
    from services.referral import withdraw_to_main_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=0)
    with pytest.raises(NothingToWithdraw):
        withdraw_to_main_balance(1)


def test_withdraw_to_main_balance_raises_for_unknown_user(tmp_db: Path) -> None:
    """Аккаунт удалён/смёржен, JWT ещё жив — UserNotFound, не 'нечего выводить'."""
    from services.referral import withdraw_to_main_balance
    with pytest.raises(UserNotFound):
        withdraw_to_main_balance(999)


def test_get_summary_includes_referral_balance(tmp_db: Path) -> None:
    from services.referral import get_summary
    _mk_user(tmp_db, 1, balance=0, referral_balance=42)
    assert get_summary(1)["referral_balance"] == 42


def test_get_summary_referral_balance_zero_for_unknown_user(tmp_db: Path) -> None:
    """Админ-эндпоинт GET /api/admin/users/{id}/referral не должен падать
    на несуществующем/удалённом target_user_id — как остальные поля summary."""
    from services.referral import get_summary
    summary = get_summary(999)
    assert summary["referral_balance"] == 0
    assert summary["total_earned"] == 0
