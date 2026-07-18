# Welcome-бонус — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новым пользователям (бот `/start`, email-регистрация, вход по SMS) автоматически начисляется приветственный бонус, сумма — env `WELCOME_BONUS_RUB` в рублях, `0` = выключено.

**Architecture:** Новый модуль `services/welcome_bonus.py` кредитует баланс и пишет строку в `refills` (`source_type='welcome_bonus'`, `status='succeeded'`, `payment_id=NULL`). Вызывается из трёх веток создания нового юзера в `services/identity.py`. `_is_first_refill()` в `services/refill.py` исключает welcome-строки, чтобы не ломать реф-бонус 30%. Уведомление в боте — через флаг `is_new_user` из middleware.

**Tech Stack:** Python 3, aiogram 2, SQLite (raw SQL), pytest + pytest-asyncio (`asyncio_mode=auto`).

Спека: `docs/superpowers/specs/2026-07-18-welcome-bonus-design.md`.

**Как гонять тесты.** Из корня worktree (`.claude/worktrees/welcome-bonus`):

```bash
docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v
```

`--build` обязателен: образ пересобирается из кода worktree (слои кэшируются, пересборка быстрая). Запускать локальным `python3` нельзя — окружение отличается от контейнера. Полный прогон: `docker compose --profile test run --build --rm test` (дефолтная команда `pytest -v`).

**Известный компромисс (осознанный):** welcome-строки попадут в `all_refills()` / `get_user_all_refills()` (админ-статистика, Google Sheets) — точно так же, как уже попадают реф-бонусы. Не чиним в этой фиче.

---

### Task 1: Конфигурация `WELCOME_BONUS_RUB`

**Files:**
- Modify: `data/config.py` (после блока `BIZA_*`, ~line 81+)
- Modify: `.env.example` (после блока PF-флагов, ~line 78)
- Modify: `tests/conftest.py` (config-stub, после `stub.BIZA_MAX_ATTEMPTS = 2`, line 82)

- [ ] **Step 1: Добавить переменную в `data/config.py`**

После блока `BIZA_*` (найти последнюю строку с `BIZA_`, добавить ниже):

```python
# ── Welcome bonus ────────────────────────────────────────────────────────────
# Приветственный бонус новым пользователям, в рублях. 0 = выключено.
WELCOME_BONUS_RUB: int = int(os.getenv("WELCOME_BONUS_RUB", "0"))
```

- [ ] **Step 2: Добавить в `.env.example`**

```bash
# Приветственный бонус новым пользователям, рублей (0 = выключено)
WELCOME_BONUS_RUB=0
```

- [ ] **Step 3: Добавить в config-stub тестов**

В `tests/conftest.py`, в `_make_config_stub()` после `stub.BIZA_MAX_ATTEMPTS = 2`:

```python
    stub.WELCOME_BONUS_RUB = 0
```

- [ ] **Step 4: Commit**

```bash
git add data/config.py .env.example tests/conftest.py
git commit -m "feat(config): add WELCOME_BONUS_RUB env variable"
```

---

### Task 2: Сервис `services/welcome_bonus.py` (TDD)

**Files:**
- Create: `services/welcome_bonus.py`
- Create: `tests/unit/test_welcome_bonus.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_welcome_bonus.py`:

```python
"""Тесты welcome-бонуса: services/welcome_bonus.py + интеграция с identity/refill."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services import balance, identity


def _welcome_rows(db_path: Path, user_id: int) -> list:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT * FROM refills WHERE user_id=? AND source_type='welcome_bonus'",
            (user_id,),
        ).fetchall()


# ── grant_welcome_bonus (unit) ───────────────────────────────────────────────

def test_grant_credits_balance_and_writes_refill(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    granted = grant_welcome_bonus(user_id)

    assert granted == 100  # рубли, без конвертации
    assert balance.get_balance(user_id) == 100
    rows = _welcome_rows(tmp_db, user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == 100
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["payment_id"] is None


def test_grant_is_idempotent(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    grant_welcome_bonus(user_id)
    second = grant_welcome_bonus(user_id)

    assert second == 0
    assert balance.get_balance(user_id) == 100
    assert len(_welcome_rows(tmp_db, user_id)) == 1


def test_grant_disabled_when_zero(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 0, raising=False)
    from services.welcome_bonus import grant_welcome_bonus

    user_id = identity._create_user(first_name="test")
    assert grant_welcome_bonus(user_id) == 0
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v`
Expected: 3× FAIL/ERROR с `ModuleNotFoundError: No module named 'services.welcome_bonus'`

- [ ] **Step 3: Реализация**

Создать `services/welcome_bonus.py`:

```python
"""Welcome-бонус новым пользователям.

Начисляется один раз при регистрации (telegram / email / phone-verified) —
вызовы в services/identity.py. Сумма — env WELCOME_BONUS_RUB (рубли),
0 = выключено. Операция пишется в refills строкой source_type='welcome_bonus',
status='succeeded', payment_id=NULL.

Сознательно НЕ через services.refill.finalize(): normalize() пускает только
source ∈ {telegram, web, api}, а welcome-бонус — внутренняя операция, не платёж.
_is_first_refill() исключает 'welcome_bonus', чтобы реф-бонус 30% по-прежнему
срабатывал на первом реальном депозите.
"""
from __future__ import annotations

from data import config
from services.balance import credit
from services.db import connect
from utils.other import get_date

SOURCE_TYPE = "welcome_bonus"


def grant_welcome_bonus(user_id: int) -> int:
    """Начислить welcome-бонус, если включён и ещё не начислялся.

    Возвращает начисленную сумму в рублях (0 — выключено или уже был).
    Порядок INSERT→credit как в refill.finalize(): строка в refills — гард
    от повторного начисления, поэтому создаётся первой.
    """
    rub = int(getattr(config, "WELCOME_BONUS_RUB", 0) or 0)
    if rub <= 0:
        return 0
    amount = rub  # users.balance и refills.amount хранятся в целых рублях

    with connect() as con:
        already = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? AND source_type = ? LIMIT 1",
            (user_id, SOURCE_TYPE),
        ).fetchone()
        if already is not None:
            return 0
        con.execute(
            "INSERT INTO refills(amount, date, user_id, payment_id, source_type, source_app_id, status) "
            "VALUES (?, ?, ?, NULL, ?, NULL, 'succeeded')",
            (amount, get_date(), user_id, SOURCE_TYPE),
        )
        con.commit()

    credit(user_id, amount)
    return amount
```

- [ ] **Step 4: Тесты зелёные**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/welcome_bonus.py tests/unit/test_welcome_bonus.py
git commit -m "feat(bonus): add welcome bonus grant service"
```

---

### Task 3: Вызовы из `services/identity.py` (TDD)

**Files:**
- Modify: `services/identity.py` (ветки нового юзера: telegram ~line 179, email ~line 347, phone ~line 201)
- Test: `tests/unit/test_welcome_bonus.py` (дописать)

- [ ] **Step 1: Дописать падающие тесты**

Добавить в конец `tests/unit/test_welcome_bonus.py`:

```python
# ── интеграция с identity (кто получает бонус) ──────────────────────────────

def test_new_telegram_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.get_or_create_user_by_telegram(tg_id=901, user_name="u1")
    assert balance.get_balance(user_id) == 100
    assert len(_welcome_rows(tmp_db, user_id)) == 1


def test_existing_telegram_user_no_second_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    first = identity.get_or_create_user_by_telegram(tg_id=902, user_name="u2")
    second = identity.get_or_create_user_by_telegram(tg_id=902, user_name="u2")
    assert first == second
    assert balance.get_balance(first) == 100
    assert len(_welcome_rows(tmp_db, first)) == 1


def test_new_email_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.get_or_create_user_by_email(
        "user@example.com", credential_hash="x" * 32
    )
    assert balance.get_balance(user_id) == 100


def test_new_verified_phone_user_gets_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.find_or_create_user_by_phone("+79990000001", verified=True)
    assert balance.get_balance(user_id) == 100


def test_guest_phone_user_no_bonus(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity.find_or_create_user_by_phone("+79990000002")  # verified=False
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []


def test_raw_create_user_no_bonus(tmp_db, monkeypatch):
    """_create_user сам по себе не начисляет — этим покрыт и партнёрский API
    (services/auth_api.py вызывает _create_user напрямую)."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    user_id = identity._create_user(first_name="api-end-user")
    assert balance.get_balance(user_id) == 0
    assert _welcome_rows(tmp_db, user_id) == []


def test_merge_guest_into_registered_no_double_bonus(tmp_db, monkeypatch):
    """Гость (verified=False, без бонуса) мерджится в полноценный аккаунт —
    бонус не задваивается."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    identity.find_or_create_user_by_phone("+79990000003")  # guest, без бонуса
    target_id = identity.get_or_create_user_by_telegram(tg_id=903, user_name="u3")
    identity.link_phone_provider(target_id, "+79990000003", set_verified=True)
    assert balance.get_balance(target_id) == 100
    assert len(_welcome_rows(tmp_db, target_id)) == 1
```

- [ ] **Step 2: Убедиться, что новые тесты падают**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v`
Expected: `test_new_telegram_user_gets_bonus`, `test_new_email_user_gets_bonus`, `test_new_verified_phone_user_gets_bonus` — FAIL (баланс 0); остальные новые — PASS (негативные); тесты Task 2 — PASS

- [ ] **Step 3: Реализация в `services/identity.py`**

3a. Добавить в начало файла (после существующих импортов, перед `@dataclass`):

```python
import logging

logger = logging.getLogger(__name__)


def _grant_welcome_bonus_safe(user_id: int) -> None:
    """Начислить welcome-бонус, не ломая регистрацию при любой ошибке."""
    try:
        from services.welcome_bonus import grant_welcome_bonus
        grant_welcome_bonus(user_id)
    except Exception:
        logger.warning("welcome bonus grant failed for user_id=%s", user_id, exc_info=True)
```

3b. `get_or_create_user_by_telegram` — ветка «Genuinely new user» (сейчас lines 178-181):

```python
    # Genuinely new user
    new_id = _create_user(user_name=user_name, first_name=first_name, ref_id=ref_id)
    link_provider(new_id, "telegram", str(tg_id))
    _grant_welcome_bonus_safe(new_id)
    return new_id
```

3c. `get_or_create_user_by_email` — конец функции (сейчас lines 347-349):

```python
    new_id = _create_user(first_name=first_name)
    link_provider(new_id, "email", email_normalized, credential_hash=credential_hash)
    _grant_welcome_bonus_safe(new_id)
    return new_id
```

3d. `find_or_create_user_by_phone` — бонус только при `verified=True`, вызов после
commit (вне `with connect()`; сейчас функция целиком возвращает изнутри `with`):

```python
def find_or_create_user_by_phone(phone: str, *, verified: bool = False) -> int:
    """Вернуть user_id, к которому привязан phone-provider.

    Если phone-провайдер не привязан — создать нового user'а и привязать phone
    (verified=0 по умолчанию: значит "введён в форме, ещё не подтверждён"; передавайте
    verified=True после успешной SMS-OTP-верификации).

    Не используется для merge-сценариев — для них есть `link_phone_provider`.
    """
    with connect() as con:
        row = con.execute(
            "SELECT user_id FROM auth_providers "
            "WHERE provider='phone' AND identifier=?",
            (phone,),
        ).fetchone()
        if row:
            return int(row["user_id"])
        cur = con.execute(
            "INSERT INTO users(user_name, first_name, balance, reg_date) "
            "VALUES (NULL, NULL, 0, ?)",
            (_now_iso(),),
        )
        new_user_id = int(cur.lastrowid)
        con.execute(
            "INSERT INTO auth_providers(user_id, provider, identifier, created_at, verified) "
            "VALUES (?, 'phone', ?, ?, ?)",
            (new_user_id, phone, _now_iso(), 1 if verified else 0),
        )
        con.commit()
    # Гость (verified=False) бонус не получает: его аккаунт может смерджиться
    # в полноценный (link_phone_provider), и бонус бы задвоился.
    if verified:
        _grant_welcome_bonus_safe(new_user_id)
    return new_user_id
```

Legacy-ветка `get_or_create_user_by_telegram` (claim по старому `users.id == tg_id`)
и `auth_api` (`_create_user` напрямую) — НЕ трогать, бонуса там нет by design.

- [ ] **Step 4: Тесты зелёные**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v`
Expected: 10 passed

- [ ] **Step 5: Смежные тесты identity/auth не сломаны**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_identity*.py tests/unit/test_auth_*.py -v`
Expected: all passed (welcome-бонус в них выключен: stub `WELCOME_BONUS_RUB = 0`)

- [ ] **Step 6: Commit**

```bash
git add services/identity.py tests/unit/test_welcome_bonus.py
git commit -m "feat(bonus): grant welcome bonus on real registrations"
```

---

### Task 4: Совместимость с реф-бонусом (TDD)

**Files:**
- Modify: `services/refill.py:182-188` (`_is_first_refill`)
- Test: `tests/unit/test_welcome_bonus.py` (дописать)

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_welcome_bonus.py`:

```python
# ── совместимость с реф-бонусом ─────────────────────────────────────────────

def test_referral_bonus_survives_welcome_bonus(tmp_db, monkeypatch):
    """Welcome-строка не должна занимать слот «первого пополнения»: реферер
    обязан получить 30% с первого РЕАЛЬНОГО депозита приглашённого."""
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from services import refill
    from utils.sqlite3 import update_user

    referrer_id = identity.get_or_create_user_by_telegram(tg_id=910, user_name="ref")
    user_id = identity.get_or_create_user_by_telegram(tg_id=911, user_name="newbie")
    update_user(id=user_id, ref_id=referrer_id)

    res = refill.finalize_with_referral_bonus(user_id, 1_000)  # первый реальный депозит

    assert res.was_newly_finalized
    assert res.referrer_id == referrer_id
    assert res.referrer_bonus == 300  # 30% от 1 000 ₽
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py::test_referral_bonus_survives_welcome_bonus -v`
Expected: FAIL — `res.referrer_bonus == 0` (welcome-строка сделала `_is_first_refill` False)

- [ ] **Step 3: Исправить `_is_first_refill`**

В `services/refill.py` (lines 182-188) заменить запрос:

```python
def _is_first_refill(user_id: int) -> bool:
    # welcome_bonus не считается пополнением: иначе реферер не получил бы
    # 30% с первого реального депозита приглашённого (см. services/welcome_bonus.py)
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM refills WHERE user_id = ? AND status = 'succeeded' "
            "AND source_type != 'welcome_bonus' LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is None
```

- [ ] **Step 4: Тесты зелёные (включая существующую реф-машину)**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py tests/unit/test_refill_state_machine.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add services/refill.py tests/unit/test_welcome_bonus.py
git commit -m "fix(refill): exclude welcome bonus rows from first-refill check"
```

---

### Task 5: Уведомление в боте (TDD)

**Files:**
- Modify: `middlewares/exists_user.py:42` (`data["is_new_user"]`)
- Modify: `design.py` (константа текста)
- Modify: `handlers/main_start.py:42-112` (параметр + строка бонуса)
- Test: `tests/unit/test_welcome_bonus.py` (дописать)

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_welcome_bonus.py`:

```python
# ── уведомление в /start ────────────────────────────────────────────────────

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _start_message(tg_id: int) -> MagicMock:
    msg = MagicMock()
    msg.get_args = MagicMock(return_value="")
    msg.answer = AsyncMock()
    msg.from_user = SimpleNamespace(first_name="Вася", username="vasya", id=tg_id)
    return msg


async def test_start_shows_bonus_line_for_new_user(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from handlers.main_start import main_start

    user_id = identity.get_or_create_user_by_telegram(tg_id=920, user_name="vasya")
    msg = _start_message(920)
    await main_start(msg, AsyncMock(), user_id=user_id, is_new_user=True)

    text = msg.answer.call_args.args[0]
    assert "приветственный бонус 100 ₽" in text


async def test_start_no_bonus_line_for_returning_user(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 100, raising=False)
    from handlers.main_start import main_start

    user_id = identity.get_or_create_user_by_telegram(tg_id=921, user_name="vasya")
    msg = _start_message(921)
    await main_start(msg, AsyncMock(), user_id=user_id, is_new_user=False)

    text = msg.answer.call_args.args[0]
    assert "приветственный бонус" not in text


async def test_start_no_bonus_line_when_disabled(tmp_db, monkeypatch):
    monkeypatch.setattr("data.config.WELCOME_BONUS_RUB", 0, raising=False)
    from handlers.main_start import main_start

    user_id = identity.get_or_create_user_by_telegram(tg_id=922, user_name="vasya")
    msg = _start_message(922)
    await main_start(msg, AsyncMock(), user_id=user_id, is_new_user=True)

    text = msg.answer.call_args.args[0]
    assert "приветственный бонус" not in text
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -k start -v`
Expected: `test_start_shows_bonus_line_for_new_user` FAIL (нет строки бонуса); два негативных PASS

- [ ] **Step 3: Реализация**

3a. `middlewares/exists_user.py` — в `_ensure_user`, после `data["user_id"] = internal_user_id` (line 42):

```python
        data["user_id"] = internal_user_id
        data["is_new_user"] = is_new
```

3b. `design.py` — рядом со `start_text` (line 5):

```python
welcome_bonus_line = "\n\n🎁 Вам начислен приветственный бонус {} ₽"
```

3c. `handlers/main_start.py`:

Импорты (line 6-10) — добавить `welcome_bonus_line` и `config` (сейчас `config`
в модуле НЕ импортирован):

```python
from data import config
from design import (
    yes_refer, refer_not_in_base, invite_yourself,
    start_text, start_text_ref, welcome_bonus_line,
)
```

Сигнатура и строка бонуса (line 42-48):

```python
@dp.message_handler(commands=['start'], state="*")
async def main_start(message: Message, state: FSMContext, user_id: int, is_new_user: bool = False):
    await state.finish()
    user = get_user(id=user_id)
    usr = message.from_user
    args = message.get_args()
    name = await get_user_name(usr)
    bonus_line = ""
    if is_new_user and config.WELCOME_BONUS_RUB > 0:
        bonus_line = welcome_bonus_line.format(config.WELCOME_BONUS_RUB)
```

Три точки ответа с приветствием — добавить `bonus_line`:

line 82: `await message.answer(start_text_ref(ref_first_name=ref_name) + bonus_line, reply_markup=get_menu_kb())`

line 107: `await message.answer(start_text_ref(ref_first_name) + bonus_line, reply_markup=get_menu_kb())`

line 112: `await message.answer(f"{start_text.format(name)}{bonus_line}", reply_markup=get_menu_kb())`

- [ ] **Step 4: Тесты зелёные**

Run: `docker compose --profile test run --build --rm test pytest tests/unit/test_welcome_bonus.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add middlewares/exists_user.py design.py handlers/main_start.py tests/unit/test_welcome_bonus.py
git commit -m "feat(bonus): show welcome bonus line in /start greeting"
```

---

### Task 6: Полный прогон и сверка со спекой

- [ ] **Step 1: Полный тест-сьют**

Run: `docker compose --profile test run --build --rm test`
Expected: all passed (никаких новых падений вне welcome-бонуса)

- [ ] **Step 2: Сверка чек-листа спеки**

Пройти раздел «Тестирование» спеки (9 пунктов) — каждый пункт должен быть покрыт
тестом из `tests/unit/test_welcome_bonus.py`. Пункт 5 (API-юзер) покрыт
`test_raw_create_user_no_bonus`.

- [ ] **Step 3: Финальный коммит (если были правки)**

```bash
git status  # если чисто — готово
```
