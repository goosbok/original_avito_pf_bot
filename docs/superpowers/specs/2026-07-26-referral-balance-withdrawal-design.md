# Реферальный баланс: отдельный «карман» с выводом на основной счёт

**Дата:** 2026-07-26
**Статус:** утверждено

## Цель

Реферальные бонусы больше не сливаются с обычным балансом сразу при начислении.
Они копятся в отдельном реферальном балансе, который **нельзя тратить на
услуги** — только вывести на основной счёт явным действием пользователя.
Пока единственное направление вывода — основной баланс сервиса; архитектура
закладывает будущие направления (например, вывод на карту) без новой миграции
схемы.

Это отменяет одно из решений [2026-07-18-referral-program-design.md](2026-07-18-referral-program-design.md)
(«Куда начисляется: обычный баланс `users.balance`, вывода денег нет») — теперь
начисление и трата разделены.

## Контекст: что уже есть

- `services/refill.py:finalize_with_referral_bonus()` — единственная точка
  начисления бонуса, вызывается из 4 мест (`handlers/refill.py`,
  `web/routers/refill.py`, `services/payment_reconciler.py`,
  `scripts/backfill_stuck_payments.py`). Сейчас начисляет через
  `services/balance.py:credit()` прямо в `users.balance`.
- `services/balance.py` — атомарные `credit`/`debit` через
  `UPDATE ... RETURNING`, без read-modify-write.
- `referral_bonuses` — неизменяемый журнал каждого начисления (используется
  для «Заработано» в API и на странице партнёрки).
- `services/payment_notifications.py:notify_referrer()` +
  `services/refill.py:_record_referral_bonus()` — TG- и web-уведомления о
  бонусе, обе принимают «новый баланс реферера» параметром.
- Партнёрка целиком в веб-кабинете (`web/static/components/Referral.jsx`,
  `web/routers/referral.py`); в боте — только read-only ссылка в профиле.
- Фича ещё не в `main` — реальных пользователей с уже начисленными бонусами
  на `balance` нет, миграция старых данных не нужна.

## Решения (утверждены)

| Вопрос | Решение |
|---|---|
| Куда падает бонус | Новая колонка `users.referral_balance`, не пересекается с `users.balance` |
| Можно ли тратить реферальный баланс на услуги | Нет — списание с `balance` его не видит и не трогает |
| Сумма вывода | Только «вывести всё» одной кнопкой, без частичного вывода |
| Куда можно вывести (сейчас) | Только на основной баланс (`users.balance`) |
| Куда можно вывести (позже) | Карта и т.п. — не реализуется сейчас, но схема это закладывает (`destination`) |
| Где кнопка вывода | Только веб-кабинет (партнёрка уже целиком там; в бот не дублируем) |
| Влияет ли на «Заработано» / per-link earned | Нет — это лайфтайм-сумма по `referral_bonuses`, вывод её не уменьшает |
| Миграция старых данных | Не нужна (см. контекст) |
| Мердж аккаунтов (`services/identity.py`, `scripts/merge_duplicate_tg_users.py`) | `referral_withdrawals` имеет `FOREIGN KEY(user_id)` — оба скрипта уже переносят `balance`/`referral_links`/`referral_bonuses` перед `DELETE FROM users`; `referral_balance` и `referral_withdrawals` переносятся тем же способом (см. «Мердж аккаунтов» ниже). Без этого мердж пользователя, хоть раз выводившего баланс, падает `FOREIGN KEY constraint failed` |
| Аудит вывода в `refills`/GSheets-экспорте | Осознанно НЕ пишем строку в `refills` — это таблица внешних платежей (YooKassa), вывод им не является; GSheets-отчёт «Пополнения по юзеру» не будет отражать выводы. Задокументировано как известное ограничение, не багфикс в рамках этой фичи |

## Данные (SQLite, схема в `utils/sqlite3.py`)

```sql
-- users: новая колонка
ALTER TABLE users ADD COLUMN referral_balance INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS referral_withdrawals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,        -- кто вывел (users.id)
  amount INTEGER NOT NULL,         -- сколько выведено, руб
  destination TEXT NOT NULL,       -- 'main_balance' сейчас; позже 'card' и т.п.
  created_at TIMESTAMP NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_referral_withdrawals_user
  ON referral_withdrawals(user_id, id DESC);
```

Миграция — по образцу существующих guard-миграций (idempotent `ALTER TABLE` /
`CREATE TABLE IF NOT EXISTS`, `PRAGMA table_info` для проверки колонки).

`referral_bonuses` не меняется: как и раньше, это журнал начислений, по нему
считаются `total_earned` и per-link `earned`. `referral_withdrawals` — отдельный
журнал выводов, ни один из них не переписывает и не удаляет строки другого.

## Сервисный слой

Новые функции в `services/referral.py` (рядом с остальной реферальной
логикой), по образцу `services/balance.py`:

```python
def credit_referral_balance(user_id: int, amount: int) -> int:
    """Атомарно увеличить referral_balance. Возвращает новый остаток.
    Бросает UserNotFound, если user_id не существует — как credit()."""

def withdraw_to_main_balance(user_id: int) -> tuple[int, int]:
    """Обнулить referral_balance, зачислить всю сумму в users.balance,
    записать строку в referral_withdrawals(destination='main_balance').
    Возвращает (withdrawn_amount, new_main_balance).
    Бросает UserNotFound, если user_id не существует;
    NothingToWithdraw, если referral_balance == 0."""
```

`credit_referral_balance` — атомарный `UPDATE ... RETURNING`, как
`services/balance.py::credit()`, и обязана повторить его же проверку
`if row is None: raise UserNotFound(...)` — без неё `finalize_with_referral_bonus`
(которая ловит именно `UserNotFound` для реферера, чей аккаунт с тех пор
удалили/смёржили) упадёт с необработанным `TypeError` вместо мягкой
деградации.

`withdraw_to_main_balance` — одна транзакция с оптимистичной блокировкой
(SQLite `RETURNING` отдаёт значение *после* апдейта, поэтому «сколько было»
нужно зафиксировать отдельно и защитить от гонки условием в `WHERE`):

```python
with connect() as con:
    row = con.execute(
        "SELECT referral_balance FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise UserNotFound(user_id)
    amount = int(row["referral_balance"])
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
        raise WithdrawConflict(user_id)  # referral_balance изменился между SELECT и UPDATE
    con.execute(
        "INSERT INTO referral_withdrawals(user_id, amount, destination, created_at) "
        "VALUES (?, ?, 'main_balance', ?)",
        (user_id, amount, get_date()),
    )
    con.commit()
```

`WithdrawConflict` — редкий краевой случай (новый бонус начислился в
промежутке между чтением и записью); API отдаёт 409, фронт может просто
повторить запрос.

`services/refill.py:finalize_with_referral_bonus()` меняется в одну строку:
`credit(referrer_id, bonus)` → `credit_referral_balance(referrer_id, bonus)`.
Поле `RefillResult.referrer_new_balance` переименовывается в
`referrer_new_referral_balance` — семантика меняется на «новый реферальный
баланс», и это протаскивается во все 4 вызывающих места (bot-handler,
web-router, payment_reconciler, backfill-скрипт), включая передачу в
`notify_referrer`.

## Мердж аккаунтов

`services/identity.py::_merge_phone_only_into` уже переносит `balance`,
`ref_id`/`ref_link_id`, `referral_links` и `referral_bonuses` с
удаляемого source-юзера на target перед `DELETE FROM users`.
`scripts/merge_duplicate_tg_users.py` делает то же для `balance` через
универсальный список `_OWNED_TABLES_USER_ID` (`[(table, column), ...]` →
`UPDATE {table} SET {col} = ? WHERE {col} = ?` на каждую пару).

Обе точки должны так же перенести:
- **Значение** `referral_balance` — суммируется в target, как `balance`
  (в `_merge_phone_only_into`; `merge_duplicate_tg_users.py` уже суммирует
  `balance` тем же паттерном — `referral_balance` добавляется рядом).
- **Строки** `referral_withdrawals` — репривязка `user_id` на target
  (в `_merge_phone_only_into` — рядом с `referral_links`/`referral_bonuses`,
  внутри того же `try/except sqlite3.OperationalError`; в
  `merge_duplicate_tg_users.py` — добавлением `("referral_withdrawals",
  "user_id")` в `_OWNED_TABLES_USER_ID`).

Без этого `DELETE FROM users WHERE id=?` (обе точки открывают соединение с
`PRAGMA foreign_keys=ON`) падает `FOREIGN KEY constraint failed` для любого
source-юзера, у которого есть хоть одна строка в `referral_withdrawals`.

## API (`web/routers/referral.py`)

| Endpoint | Auth | Назначение |
|---|---|---|
| `GET /api/me/referral` | JWT | Как сейчас + новое поле `referral_balance` (текущий выводимый остаток); деградирует в 0, не падает, если `user_id` не существует (важно для админского `/admin/users/{id}/referral` — несуществующий `target_user_id` не должен давать 500) |
| `POST /api/me/referral/withdraw` | JWT | Без тела — выводит весь `referral_balance`. 200 → `{"withdrawn": N, "referral_balance": 0, "balance": <новый основной баланс>}`. 404, если пользователь не найден (аккаунт удалён/смёржен, JWT ещё жив — как `create_link`); 400, если выводить нечего; 409 при гонке (см. ниже) — фронт может повторить запрос |

## UI (`web/static/components/Referral.jsx`)

В карточке «Как это работает» рядом с «Рефералов» / «Заработано» — третья
величина «Доступно к выводу: `referral_balance` ₽» и кнопка «Вывести на
баланс» (disabled при `referral_balance === 0`). По клику —
`POST /withdraw`, при успехе обновляем локальный `referral_balance` → 0 и
баланс в шапке кабинета (через существующий колбэк обновления профиля),
показываем короткое подтверждение.

Текст блока «Как это работает» уточняется: было «...получайте 10% с каждого
пополнения... на баланс сервиса. Пожизненно.» → «...на реферальный баланс.
Пожизненно. Вывести его на основной счёт можно здесь же».

## Уведомления

`str_ref_balance_refil` (сейчас: «🎁 Ваш реферал пополнил баланс! Вам
начислено X ₽. Баланс: Y ₽.») переписывается, чтобы не создавать впечатление,
что деньги сразу доступны для трат — например: «🎁 Ваш реферал пополнил
баланс! Вам начислено X ₽ на реферальный баланс (доступно к выводу: Y ₽).
Вывести — в личном кабинете → Партнёрка.» Правки в две точки, которые уже
принимают это значение параметром: `services/payment_notifications.py:notify_referrer`
и `services/refill.py:_record_referral_bonus` (web-уведомление).

## Тесты

- Обновить существующие тесты `finalize_with_referral_bonus` — бонус теперь
  должен попадать в `referral_balance`, а `users.balance` — не меняться.
- Новые unit-тесты `credit_referral_balance` / `withdraw_to_main_balance`:
  обычный путь, вывод при нулевом остатке (ошибка), вывод/начисление для
  несуществующего user_id (`UserNotFound`), что `users.balance` затронут
  только выводом, а не начислением.
- Тест API `POST /api/me/referral/withdraw`: happy path, 400 при пустом
  остатке, 404 для несуществующего юзера, что `GET /api/me/referral`
  отражает `referral_balance` до и после.
- Тест на мердж: пользователь с ненулевым `referral_balance` и/или строкой в
  `referral_withdrawals` мержится без `IntegrityError`, оба значения
  корректно переносятся на target.

## Явно вне скоупа

- Вывод на карту / другие внешние направления — только зарезервированное
  поле `destination` в схеме, без реализации.
- Частичный вывод произвольной суммы.
- Отображение `referral_balance` в боте или в общем балансе кабинета
  (`GET /api/me`) — остаётся только на странице партнёрки.
- Отдельная лента «история выводов» в UI — при необходимости добавляется
  позже поверх уже существующей таблицы `referral_withdrawals`.
