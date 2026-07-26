# Referral Balance Withdrawal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Referral bonuses stop landing directly in `users.balance` (spendable
immediately) and instead accumulate in a separate `users.referral_balance`
that can only be moved into the main balance via an explicit "withdraw all"
action in the web cabinet.

**Architecture:** New `users.referral_balance` column (mirrors the existing
`balance` column's atomic credit/debit style) + new `referral_withdrawals`
ledger table with a `destination` field that future payout channels (e.g.
card) can reuse without another migration. `services/refill.py`'s single
choke point (`finalize_with_referral_bonus`) is repointed to credit
`referral_balance` instead of `balance`. A new `POST /api/me/referral/withdraw`
endpoint moves the whole `referral_balance` into `balance` atomically.

**Tech Stack:** Python 3.11, FastAPI, aiogram 2.x, raw SQLite3 (no ORM),
pytest, React 18 + in-browser Babel (no build step) for the web cabinet.

Spec: `docs/superpowers/specs/2026-07-26-referral-balance-withdrawal-design.md`

---

### Task 1: Schema migration — `users.referral_balance` + `referral_withdrawals`

**Files:**
- Modify: `utils/sqlite3.py:1222-1225` (insert after the `idx_users_ref_link_id` index, before the `settings_exists` block)
- Test: `tests/unit/test_referral_balance_schema.py` (new file)

- [ ] **Step 1: Write the failing schema test**

Create `tests/unit/test_referral_balance_schema.py`:

```python
"""Схема реферального баланса: users.referral_balance, referral_withdrawals."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _columns(tmp_db: Path, table: str) -> set[str]:
    with sqlite3.connect(tmp_db) as con:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def test_users_has_referral_balance(tmp_db: Path) -> None:
    assert "referral_balance" in _columns(tmp_db, "users")


def test_referral_balance_defaults_to_zero(tmp_db: Path) -> None:
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO users(id, balance) VALUES (1, 0)")
        con.commit()
        row = con.execute(
            "SELECT referral_balance FROM users WHERE id = 1"
        ).fetchone()
    assert row[0] == 0


def test_referral_withdrawals_table_exists(tmp_db: Path) -> None:
    assert _columns(tmp_db, "referral_withdrawals") == {
        "id", "user_id", "amount", "destination", "created_at",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_balance_schema.py -v`
Expected: FAIL — `referral_balance` not in columns, `referral_withdrawals` has no columns (table doesn't exist).

- [ ] **Step 3: Add the migration**

In `utils/sqlite3.py`, inside `apply_phase2_migrations()`, insert immediately
after the existing block that ends with (around line 1225):

```python
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_ref_link_id "
            "ON users(ref_link_id)"
        )
```

add:

```python
        # === referral balance (withdraw-only) ===
        existing_users_2 = {row['name'] for row in con.execute("PRAGMA table_info(users)").fetchall()}
        if 'referral_balance' not in existing_users_2:
            con.execute("ALTER TABLE users ADD COLUMN referral_balance INTEGER NOT NULL DEFAULT 0")
            print("users.referral_balance added")
        con.execute(
            "CREATE TABLE IF NOT EXISTS referral_withdrawals("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER NOT NULL,"
            "amount INTEGER NOT NULL,"
            "destination TEXT NOT NULL,"
            "created_at TIMESTAMP NOT NULL,"
            "FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_referral_withdrawals_user "
            "ON referral_withdrawals(user_id, id DESC)"
        )
```

(Keep the existing `settings_exists` block right after this, unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_balance_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add utils/sqlite3.py tests/unit/test_referral_balance_schema.py
git commit -m "feat(referral): add users.referral_balance and referral_withdrawals schema"
```

---

### Task 2: New exceptions

**Files:**
- Modify: `services/exceptions.py` (append at end of file)

- [ ] **Step 1: Add the exceptions**

Append to `services/exceptions.py`:

```python


class NothingToWithdraw(ServiceError):
    """Попытка вывести реферальный баланс, когда он равен нулю."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"user_id={user_id}: referral_balance is 0, nothing to withdraw")
        self.user_id = user_id


class WithdrawConflict(ServiceError):
    """referral_balance изменился между чтением и записью (гонка с новым бонусом)."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"user_id={user_id}: referral_balance changed concurrently, retry")
        self.user_id = user_id
```

No test needed for this step in isolation — it's exercised by Task 3's tests.

- [ ] **Step 2: Commit**

```bash
git add services/exceptions.py
git commit -m "feat(referral): add NothingToWithdraw and WithdrawConflict exceptions"
```

---

### Task 3: Service functions — `credit_referral_balance` / `withdraw_to_main_balance`

**Files:**
- Modify: `services/referral.py` (add functions + update `get_summary`)
- Test: `tests/unit/test_referral_balance.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_referral_balance.py`:

```python
"""credit_referral_balance / withdraw_to_main_balance / get_summary.referral_balance."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.exceptions import NothingToWithdraw


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


def test_withdraw_to_main_balance_raises_when_zero(tmp_db: Path) -> None:
    from services.referral import withdraw_to_main_balance
    _mk_user(tmp_db, 1, balance=0, referral_balance=0)
    with pytest.raises(NothingToWithdraw):
        withdraw_to_main_balance(1)


def test_get_summary_includes_referral_balance(tmp_db: Path) -> None:
    from services.referral import get_summary
    _mk_user(tmp_db, 1, balance=0, referral_balance=42)
    assert get_summary(1)["referral_balance"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_balance.py -v`
Expected: FAIL — `credit_referral_balance`/`withdraw_to_main_balance` don't exist yet, `get_summary` has no `referral_balance` key.

- [ ] **Step 3: Implement the functions**

In `services/referral.py`, add near the top-level imports (the module already
imports `connect` and `get_date`):

```python
from services.exceptions import NothingToWithdraw, WithdrawConflict
```

Add these functions after `set_custom_percent` (end of the "проценты" section,
before "статистика"):

```python
# ---------------------------------------------------------------- баланс

def credit_referral_balance(user_id: int, amount: int) -> int:
    """Атомарно увеличить referral_balance. Возвращает новый остаток."""
    with connect() as con:
        cur = con.execute(
            "UPDATE users SET referral_balance = COALESCE(referral_balance, 0) + ? "
            "WHERE id = ? RETURNING referral_balance",
            (amount, user_id),
        )
        row = cur.fetchone()
        con.commit()
    return int(row["referral_balance"])


def withdraw_to_main_balance(user_id: int) -> tuple[int, int]:
    """Переносит весь referral_balance в balance. Возвращает (withdrawn, new_balance).

    Оптимистичная блокировка: WHERE referral_balance = <прочитанное значение>
    защищает от гонки с новым бонусом между SELECT и UPDATE — в этом случае
    UPDATE не найдёт строку и мы бросаем WithdrawConflict (retry на стороне
    вызывающего/фронта), а не тихо теряем часть суммы.
    """
    with connect() as con:
        row = con.execute(
            "SELECT referral_balance FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        amount = int(row["referral_balance"]) if row else 0
        if amount <= 0:
            raise NothingToWithdraw(user_id)
        cur = con.execute(
            "UPDATE users SET balance = balance + referral_balance, "
            "referral_balance = 0 "
            "WHERE id = ? AND referral_balance = ? "
            "RETURNING balance",
            (user_id, amount),
        )
        result = cur.fetchone()
        if result is None:
            raise WithdrawConflict(user_id)
        con.execute(
            "INSERT INTO referral_withdrawals(user_id, amount, destination, created_at) "
            "VALUES (?, ?, 'main_balance', ?)",
            (user_id, amount, get_date()),
        )
        con.commit()
    return amount, int(result["balance"])
```

In `get_summary`, add `referral_balance` to the returned dict:

```python
def get_summary(user_id: int) -> dict:
    """Сводка для GET /api/me/referral и админской карточки."""
    g = get_global_percent()
    links = list_links(user_id)
    for link in links:
        link["effective_percent"] = (
            link["custom_percent"] if link["custom_percent"] is not None else g
        )
    with connect() as con:
        earned = con.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM referral_bonuses "
            "WHERE referrer_id = ?",
            (user_id,),
        ).fetchone()["s"]
        referral_balance = con.execute(
            "SELECT COALESCE(referral_balance, 0) AS b FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()["b"]
    return {
        "percent": g,
        "links": links,
        "referrals_count": referrals_count(user_id),
        "total_earned": earned,
        "referral_balance": referral_balance,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_balance.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add services/referral.py tests/unit/test_referral_balance.py
git commit -m "feat(referral): add credit_referral_balance/withdraw_to_main_balance services"
```

---

### Task 4: Wire `finalize_with_referral_bonus` to the referral balance

**Files:**
- Modify: `services/refill.py:174-179,197-303` (RefillResult field, `_record_referral_bonus`, `finalize_with_referral_bonus`)
- Modify: `handlers/refill.py:177-178`
- Modify: `web/routers/refill.py:152-153`
- Modify: `services/payment_reconciler.py:84-85`
- Modify: `scripts/backfill_stuck_payments.py:112-113`
- Modify: `tests/unit/test_refill.py:93,96,157`
- Modify: `tests/unit/test_refill_state_machine.py:40,191`

- [ ] **Step 1: Update the existing tests first (red)**

In `tests/unit/test_refill.py`, change the three assertions:

Line 93: `assert r1.referrer_new_balance == 100` → `assert r1.referrer_new_referral_balance == 100`
Line 96: `assert r2.referrer_new_balance == 300` → `assert r2.referrer_new_referral_balance == 300`
Line 157: `assert result.referrer_new_balance is None` → `assert result.referrer_new_referral_balance is None`

Also add a new assertion right after line 93 to lock in the core behavior
change — insert this line immediately after `assert r1.referrer_new_referral_balance == 100`
(`get_balance` is already imported at the top of this file, line 7 —
`from services.balance import get_balance`, no new import needed):

```python
    assert get_balance(1) == 0  # бонус НЕ попал в основной баланс реферера
```

In `tests/unit/test_refill_state_machine.py`:

Line 40: `referrer_new_balance=None,` → `referrer_new_referral_balance=None,`
Line 191: `assert r1.referrer_new_balance == 100` → `assert r1.referrer_new_referral_balance == 100`

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_refill.py tests/unit/test_refill_state_machine.py -v`
Expected: FAIL — `RefillResult` has no field `referrer_new_referral_balance` yet.

- [ ] **Step 3: Rename the field and wire the credit call**

In `services/refill.py`:

Change the import line near the top:

```python
from services.balance import credit, get_balance
```

stays as-is (still needed for the payer's own balance and for
`withdraw_to_main_balance` internally, which lives in `services/referral.py`
and imports `credit` itself — no change needed here beyond what's below).

Change the dataclass:

```python
@dataclass(frozen=True)
class RefillResult:
    user_balance: int
    referrer_id: int | None
    referrer_bonus: int
    referrer_new_referral_balance: int | None
    was_newly_finalized: bool = False
```

Change `_record_referral_bonus`'s signature and body (parameter rename +
docstring update):

```python
def _record_referral_bonus(
    *,
    referrer_id: int,
    referred_user_id: int,
    payment_id: str | None,
    link_id: int | None,
    bonus: int,
    percent: int,
    referrer_new_referral_balance: int,
) -> None:
    """История начисления + durable web-уведомление реферу."""
    import re

    from utils.other import format_decimal, get_date
    from utils.sqlite3 import get_string

    with connect() as con:
        refill_row = None
        if payment_id is not None:
            refill_row = con.execute(
                "SELECT increment FROM refills WHERE payment_id = ?",
                (payment_id,),
            ).fetchone()
        con.execute(
            "INSERT INTO referral_bonuses(referrer_id, referred_user_id, refill_id, "
            "link_id, amount, percent, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                referrer_id, referred_user_id,
                refill_row["increment"] if refill_row else None,
                link_id, bonus, percent, get_date(),
            ),
        )
        text = get_string("str_ref_balance_refil").format(
            format_decimal(bonus), format_decimal(referrer_new_referral_balance)
        )
        # Строка — телеграмный HTML (<b>…</b>); веб-уведомления рендерятся
        # плоским текстом (React экранирует), поэтому теги вырезаем.
        text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
        con.execute(
            "INSERT INTO notifications(user_id, kind, text) VALUES (?, 'referral', ?)",
            (referrer_id, text),
        )
        con.commit()
```

Change `finalize_with_referral_bonus`'s body:

```python
def finalize_with_referral_bonus(
    user_id: int,
    amount: int,
    payment_id: str | None = None,
    *,
    source_type: str = "telegram",
    source_app_id: int | None = None,
) -> RefillResult:
    """Финализирует refill + начисляет реферу процент с КАЖДОГО пополнения.

    Процент: custom_percent ссылки, через которую атрибуцирован плательщик,
    иначе глобальный settings.ref_percent. Бонус идёт в users.referral_balance
    (services.referral.credit_referral_balance) — НЕ в основной баланс и НЕ
    через finalize(), чтобы у рефера не появлялась фиктивная запись в refills
    и деньги не были сразу доступны для трат (вывод — отдельным действием).
    was_newly_finalized пробрасывается из finalize() — защита от двойного
    начисления при гонках (web-status / крон / TG-handler).
    """
    user = _get_user_for_referral(user_id)

    new_balance, was_newly_finalized = finalize(
        user_id, amount, payment_id=payment_id,
        source_type=source_type, source_app_id=source_app_id,
    )

    referrer_id: int | None = user["ref_id"]
    bonus = 0
    referrer_new_referral_balance: int | None = None

    if was_newly_finalized and not user["is_vip"] and referrer_id is not None:
        from services.referral import credit_referral_balance, get_bonus_percent
        percent = get_bonus_percent(user["ref_link_id"])
        bonus = amount * percent // 100
        if bonus > 0:
            try:
                referrer_new_referral_balance = credit_referral_balance(int(referrer_id), bonus)
            except UserNotFound:
                referrer_new_referral_balance = None
                bonus = 0
            else:
                try:
                    _record_referral_bonus(
                        referrer_id=int(referrer_id),
                        referred_user_id=user_id,
                        payment_id=payment_id,
                        link_id=user["ref_link_id"],
                        bonus=bonus,
                        percent=percent,
                        referrer_new_referral_balance=referrer_new_referral_balance,
                    )
                except Exception:
                    # Баланс реферу уже начислен — сбой записи истории или
                    # уведомления НЕ должен превратить успешный платеж в ошибку
                    # для плательщика. Логируем для ручного backfill.
                    import logging
                    logging.getLogger(__name__).exception(
                        "referral bonus history write failed: referrer=%s "
                        "payer=%s bonus=%s payment_id=%s",
                        referrer_id, user_id, bonus, payment_id,
                    )

    return RefillResult(
        user_balance=new_balance,
        referrer_id=int(referrer_id) if referrer_id is not None else None,
        referrer_bonus=bonus,
        referrer_new_referral_balance=referrer_new_referral_balance,
        was_newly_finalized=was_newly_finalized,
    )
```

Note: `credit` (from `services.balance`) is no longer called directly in this
file for the referrer — leave the `from services.balance import credit,
get_balance` import line as-is since `finalize()` (unchanged, above this
section) still uses both.

- [ ] **Step 4: Update the four call sites**

In `handlers/refill.py` line 177-178, change:

```python
            await notify_referrer(result.referrer_id, result.referrer_bonus,
                                  result.referrer_new_balance or 0)
```

to:

```python
            await notify_referrer(result.referrer_id, result.referrer_bonus,
                                  result.referrer_new_referral_balance or 0)
```

In `web/routers/refill.py` line 152-153, change:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)
```

to:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_referral_balance or 0)
```

In `services/payment_reconciler.py` line 84-85, change:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)
```

to:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_referral_balance or 0)
```

In `scripts/backfill_stuck_payments.py` line 112-113, change:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_balance or 0)
```

to:

```python
                await notify_referrer(result.referrer_id, result.referrer_bonus,
                                      result.referrer_new_referral_balance or 0)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_refill.py tests/unit/test_refill_state_machine.py tests/unit/test_referral_balance.py -v`
Expected: PASS, all green.

- [ ] **Step 6: Run the full suite to catch anything else touching these names**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest -q`
Expected: PASS (0 failed). If anything else fails on `referrer_new_balance`,
rename it there too before moving on.

- [ ] **Step 7: Commit**

```bash
git add services/refill.py handlers/refill.py web/routers/refill.py \
        services/payment_reconciler.py scripts/backfill_stuck_payments.py \
        tests/unit/test_refill.py tests/unit/test_refill_state_machine.py
git commit -m "feat(referral): credit bonuses to referral_balance instead of main balance"
```

---

### Task 5: Notification copy

**Files:**
- Modify: `utils/sqlite3.py:122`

- [ ] **Step 1: Update the default string**

Change line 122 in `utils/sqlite3.py` from:

```python
    "str_ref_balance_refil": "🎁 Ваш реферал пополнил баланс! Вам начислено <b>{}</b> ₽. Баланс: <b>{}</b> ₽.",
```

to:

```python
    "str_ref_balance_refil": "🎁 Ваш реферал пополнил баланс! Вам начислено <b>{}</b> ₽ на реферальный баланс (доступно к выводу: <b>{}</b> ₽). Вывести — в личном кабинете → Партнёрка.",
```

This is a `_STRING_DEFAULTS` seed value (`ON CONFLICT DO NOTHING` on insert,
per the existing `add_string_to_base`/settings pattern) — it only affects
fresh databases. No test asserts the literal text (`test_payment_notifications.py`
mocks `get_string`), so no test changes needed here.

- [ ] **Step 2: Commit**

```bash
git add utils/sqlite3.py
git commit -m "fix(referral): clarify bonus notification now refers to referral balance"
```

---

### Task 6: API — `referral_balance` in summary + `POST /withdraw`

**Files:**
- Modify: `web/routers/referral.py`
- Modify: `tests/unit/test_referral_api.py` (append tests)

- [ ] **Step 1: Write the failing API tests**

Append to `tests/unit/test_referral_api.py`:

```python


# --------------------------------------------------- вывод реферального баланса

def test_withdraw_requires_auth(tmp_db: Path) -> None:
    assert _client().post("/api/me/referral/withdraw").status_code == 401


def test_withdraw_moves_referral_balance_to_main_balance(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE users SET referral_balance = 250 WHERE id = 1")
        con.commit()
    r = _client().post("/api/me/referral/withdraw", headers=_auth(1))
    assert r.status_code == 200
    body = r.json()
    assert body == {"withdrawn": 250, "referral_balance": 0, "balance": 250}
    summary = _client().get("/api/me/referral", headers=_auth(1)).json()
    assert summary["referral_balance"] == 0


def test_withdraw_with_zero_balance_is_400(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    r = _client().post("/api/me/referral/withdraw", headers=_auth(1))
    assert r.status_code == 400


def test_summary_includes_referral_balance(tmp_db: Path) -> None:
    _mk_user(tmp_db, 1)
    with sqlite3.connect(tmp_db) as con:
        con.execute("UPDATE users SET referral_balance = 77 WHERE id = 1")
        con.commit()
    summary = _client().get("/api/me/referral", headers=_auth(1)).json()
    assert summary["referral_balance"] == 77
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v -k withdraw_or_referral_balance`

(If that `-k` filter matches nothing due to naming, just run the whole file:)

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v`
Expected: the 4 new tests FAIL with 404 (no such route) for the withdraw ones;
`test_summary_includes_referral_balance` already passes once Task 3 landed
(it only depends on `get_summary`, not the new route) — that's fine, TDD is
about the route which doesn't exist yet.

- [ ] **Step 3: Add the endpoint**

In `web/routers/referral.py`, add the import:

```python
from services.exceptions import NothingToWithdraw
```

Add the endpoint after `my_bonuses` (right before `@router.post("/referral/click")`):

```python
@router.post("/me/referral/withdraw")
async def withdraw_referral_balance(user_id: int = Depends(require_user)) -> dict:
    try:
        withdrawn, new_balance = referral.withdraw_to_main_balance(user_id)
    except NothingToWithdraw as exc:
        raise HTTPException(status_code=400, detail="нечего выводить") from exc
    except referral.WithdrawConflict as exc:
        raise HTTPException(status_code=409, detail="попробуйте ещё раз") from exc
    return {"withdrawn": withdrawn, "referral_balance": 0, "balance": new_balance}
```

Note: `referral.WithdrawConflict` works because `services/referral.py`
imports `WithdrawConflict` from `services.exceptions` at module level (Task 3),
so it's accessible as `referral.WithdrawConflict`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest tests/unit/test_referral_api.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 5: Run the full suite**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest -q`
Expected: PASS (0 failed).

- [ ] **Step 6: Commit**

```bash
git add web/routers/referral.py tests/unit/test_referral_api.py
git commit -m "feat(referral): add POST /api/me/referral/withdraw endpoint"
```

---

### Task 7: UI — show referral balance and wire the withdraw button

**Files:**
- Modify: `web/static/components/Referral.jsx`
- Modify: `web/static/app.jsx:321` (pass `refreshBalance` prop)

- [ ] **Step 1: Pass `refreshBalance` into `ReferralPage`**

In `web/static/app.jsx`, change line 321 from:

```jsx
      case 'referral': return <ReferralPage user={user} botConfig={botConfig} onNavigate={handleNavigate} />;
```

to:

```jsx
      case 'referral': return <ReferralPage user={user} botConfig={botConfig} onNavigate={handleNavigate} refreshBalance={refreshBalance} />;
```

- [ ] **Step 2: Update copy and add the withdraw block**

In `web/static/components/Referral.jsx`, change the function signature (line 4):

```jsx
function ReferralPage({ user, botConfig, onNavigate, refreshBalance }) {
```

Change the "как это работает" copy (lines 88-89) from:

```jsx
          Делитесь ссылкой — получайте <strong>{data.percent}%</strong> с каждого
          пополнения приведенных пользователей на баланс сервиса. Пожизненно.
```

to:

```jsx
          Делитесь ссылкой — получайте <strong>{data.percent}%</strong> с каждого
          пополнения приведенных пользователей на реферальный баланс. Пожизненно.
          Вывести его на основной счёт можно здесь же.
```

Replace the stats row (lines 91-94):

```jsx
        <div style={{ display: 'flex', gap: 24, marginTop: 12, fontSize: '0.875rem' }}>
          <div>Рефералов: <strong>{data.referrals_count}</strong></div>
          <div>Заработано: <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap' }}>{data.total_earned.toLocaleString('ru-RU')} ₽</strong></div>
        </div>
```

with:

```jsx
        <div style={{ display: 'flex', gap: 24, marginTop: 12, fontSize: '0.875rem', flexWrap: 'wrap' }}>
          <div>Рефералов: <strong>{data.referrals_count}</strong></div>
          <div>Заработано: <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap' }}>{data.total_earned.toLocaleString('ru-RU')} ₽</strong></div>
          <div>Доступно к выводу: <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap' }}>{data.referral_balance.toLocaleString('ru-RU')} ₽</strong></div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn--primary btn--sm" onClick={withdraw}
                  disabled={busy || data.referral_balance === 0}>
            Вывести на баланс
          </button>
        </div>
```

Add the `withdraw` handler right after the `restore` function (after line 67,
before the `if (!data) return ...` guard):

```jsx
  const withdraw = async () => {
    setBusy(true); setError('');
    try {
      await api.post('/api/me/referral/withdraw', {});
      await load();
      if (refreshBalance) refreshBalance();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };
```

- [ ] **Step 3: Rebuild and manually verify in the browser**

Run: `docker compose up -d --build api`

Then, with a logged-in user that has `referral_balance > 0` (seed one via
`docker exec original_avito_pf_bot-api-1 python -c "from services.referral import credit_referral_balance; print(credit_referral_balance(<user_id>, 500))"`
against a real user id), open the cabinet → Партнёрка (dropdown menu) and
confirm:
- "Доступно к выводу: 500 ₽" shows next to "Заработано".
- "Вывести на баланс" is enabled, clicking it sets it to 0 and the header
  balance increases by 500 ₽.
- With `referral_balance === 0`, the button is disabled.
- Check both mobile (375px) and desktop viewports — no layout overflow.

There is no automated test for this step: this project's frontend is
in-browser-Babel JSX with no JS test harness (consistent with every prior
Referral.jsx change in this codebase, which were all verified manually).

- [ ] **Step 4: Commit**

```bash
git add web/static/components/Referral.jsx web/static/app.jsx
git commit -m "feat(referral): show referral balance and withdraw button in the cabinet"
```

---

### Task 8: Final full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest -q`
Expected: PASS, 0 failed (same count as before this plan started, plus the
~10 new tests added across Tasks 1, 3, and 6).

- [ ] **Step 2: Confirm no other reference to the old field name survived**

Run: `grep -rn "referrer_new_balance" --include="*.py" .`
Expected: no output (empty) — everything was renamed to
`referrer_new_referral_balance` in Task 4.
