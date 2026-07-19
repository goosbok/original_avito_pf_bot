import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services.balance import get_balance
from services.exceptions import PaymentError, UserNotFound
from services.refill import create_invoice, finalize


def _make_user(tmp_db: Path, user_id: int = 1, balance: int = 0) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, "u", "U", balance, "2026-05-02"),
        )
        con.commit()


def test_create_invoice_delegates_to_yookassa(tmp_db: Path) -> None:
    _make_user(tmp_db, user_id=1)
    with patch(
        "services.refill._yookassa_create_invoice",
        return_value=("https://pay/xyz", "pay-id-1"),
    ) as mock:
        url, pid = create_invoice(user_id=1, amount=200)
    assert url == "https://pay/xyz"
    assert pid == "pay-id-1"
    mock.assert_called_once_with(1, 200)


def test_create_invoice_wraps_yookassa_errors(tmp_db: Path) -> None:
    with patch(
        "services.refill._yookassa_create_invoice",
        side_effect=RuntimeError("yookassa down"),
    ):
        with pytest.raises(PaymentError):
            create_invoice(user_id=1, amount=200)


def test_finalize_credits_balance_and_writes_refill(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=10)
    new_balance, _ = finalize(user_id=1, amount=200)
    assert new_balance == 210
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute(
            "SELECT user_id, amount FROM refills WHERE user_id = 1"
        ).fetchall()
    assert rows == [(1, 200)]


def test_finalize_unknown_user_raises(tmp_db: Path) -> None:
    with pytest.raises(UserNotFound):
        finalize(user_id=999, amount=100)


def test_finalize_amount_must_be_positive(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=-50)


from services.refill import finalize_with_referral_bonus


def _make_user_full(
    tmp_db: Path,
    user_id: int,
    balance: int = 0,
    ref_id: int | None = None,
    is_vip: bool = False,
) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date, ref_id, is_vip) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, f"u{user_id}", f"U{user_id}", balance, "2026-05-02",
             ref_id, 1 if is_vip else None),
        )
        con.commit()


def test_referral_bonus_every_refill_credits_referrer(tmp_db: Path) -> None:
    """10% с каждого пополнения, не только первого."""
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    r1 = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert r1.referrer_bonus == 100  # 10%
    assert r1.referrer_new_balance == 100
    r2 = finalize_with_referral_bonus(user_id=2, amount=2000)
    assert r2.referrer_bonus == 200
    assert r2.referrer_new_balance == 300


def test_referral_bonus_floor_and_zero(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    r = finalize_with_referral_bonus(user_id=2, amount=109)
    assert r.referrer_bonus == 10  # floor(10.9)
    r2 = finalize_with_referral_bonus(user_id=2, amount=9)
    assert r2.referrer_bonus == 0  # floor(0.9) → ничего не пишем
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM referral_bonuses WHERE amount = 0"
        ).fetchone()[0] == 0


def test_referral_bonus_uses_link_custom_percent(tmp_db: Path) -> None:
    from services.referral import create_link, set_custom_percent
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    link = create_link(1, "vip-deal")
    set_custom_percent(link["id"], 25)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE users SET ref_link_id = ? WHERE id = 2", (link["id"],))
    r = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert r.referrer_bonus == 250


def test_referral_bonus_recorded_in_history(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT referrer_id, referred_user_id, amount, percent "
            "FROM referral_bonuses"
        ).fetchone()
    assert row == (1, 2, 100, 10)


def test_referral_bonus_does_not_create_referrer_refill(tmp_db: Path) -> None:
    """Бонус идет через credit(), а не finalize() — у рефера НЕ появляется запись в refills."""
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1)
    finalize_with_referral_bonus(user_id=2, amount=1000)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM refills WHERE user_id = 1"
        ).fetchone()[0] == 0


def test_referral_bonus_skipped_for_vip(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=1, balance=0)
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=1, is_vip=True)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0
    assert result.referrer_new_balance is None


def test_referral_bonus_skipped_when_no_referrer(tmp_db: Path) -> None:
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=None)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_id is None
    assert result.referrer_bonus == 0


def test_referral_bonus_referrer_does_not_exist(tmp_db: Path) -> None:
    """ref_id на несуществующего — бонус молча пропущен, не падаем."""
    _make_user_full(tmp_db, user_id=2, balance=0, ref_id=999)
    result = finalize_with_referral_bonus(user_id=2, amount=1000)
    assert result.user_balance == 1000
    assert result.referrer_bonus == 0


def test_finalize_is_idempotent_with_payment_id(tmp_db: Path) -> None:
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, payment_id="pay-A")
    new_balance, _ = finalize(user_id=1, amount=100, payment_id="pay-A")
    assert new_balance == 100
    with sqlite3.connect(tmp_db) as con:
        rows = con.execute("SELECT amount FROM refills WHERE user_id = 1").fetchall()
    assert rows == [(100,)]


def test_finalize_no_payment_id_is_not_dedup(tmp_db: Path) -> None:
    """Без payment_id вызовы независимы — два пополнения = +amount × 2."""
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100)
    finalize(user_id=1, amount=100)
    assert get_balance(1) == 200


def test_finalize_writes_source_telegram_by_default(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("telegram", None)


def test_finalize_writes_source_web(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, source_type="web")
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("web", None)


def test_finalize_writes_source_api_with_app_id(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    finalize(user_id=1, amount=100, source_type="api", source_app_id=7)
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        row = con.execute("SELECT source_type, source_app_id FROM refills").fetchone()
    assert row == ("api", 7)


def test_finalize_api_without_app_id_raises(tmp_db: Path):
    _make_user(tmp_db, balance=0)
    with pytest.raises(ValueError):
        finalize(user_id=1, amount=100, source_type="api")
